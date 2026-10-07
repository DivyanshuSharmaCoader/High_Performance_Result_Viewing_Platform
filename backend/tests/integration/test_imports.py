"""Student import end to end (P6.4–P6.6): upload → background check → review → fix → commit."""

from __future__ import annotations

import io
import subprocess
import sys
import uuid

import pytest
from openpyxl import load_workbook
from sqlalchemy import select, text

from app.modules.directory.models import CohortMembership, Student
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.models import TenantFeatureOverride
from app.modules.entitlements.service import EntitlementService
from tests.helpers import Client, client_as, drain_jobs, make_structure, make_student, make_tenant

pytestmark = pytest.mark.integration

BASE = "/api/v1/admin/imports"


def _csv(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode()


async def _upload(c: Client, data: bytes, name: str = "students.csv", **form: str):
    return await c.post(BASE, files={"file": (name, data, "text/csv")}, data={"kind": "students", **form})


async def _checked(c: Client, infra, import_id: str) -> dict:
    await drain_jobs(infra, ["imports"])
    return (await c.get(f"{BASE}/{import_id}")).json()


async def _students(infra, tenant_id) -> dict[str, Student]:
    async with infra.db.uow(tenant_id) as uow:
        return {s.enrollment_no: s for s in (await uow.session.scalars(select(Student))).all()}


def test_api_process_knows_every_job_kind() -> None:
    """Regression: the API enqueues import jobs, so it must register handlers without the worker."""
    code = (
        "from app.main import create_app; from app.core.jobs import registry; create_app(); "
        "assert {'imports.analyse', 'imports.commit', 'notifications.send_email'} <= set(registry.kinds())"
    )
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, timeout=60)  # noqa: S603 (fixed argv)


async def test_upload_check_fix_and_commit(app, infra) -> None:
    t = await make_tenant(infra)
    s = await make_structure(infra, t)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        broken = _csv(
            "Enrollment No.,Name,Email,Cohort",
            f"A001,Asha Rao,asha@example.com,{s.cohort_code}",
            f"A002,Bilal Khan,not-an-email,{s.cohort_code}",
            "A001,Asha Again,,",
        )
        r = await _upload(c, broken, session_id=str(s.session_id))
        assert r.status_code == 202, r.text
        first = r.json()
        assert first["status"] == "uploaded" and first["resumed"] is False

        job = await _checked(c, infra, first["id"])
        assert job["status"] == "validated"
        assert (job["rows_total"], job["rows_valid"], job["rows_error"]) == (3, 1, 2)
        assert job["mapping"] == {"enrollment_no": 0, "full_name": 1, "email": 2, "cohort": 3}
        assert job["summary"]["session_code"] == s.session_code

        problems = (await c.get(f"{BASE}/{first['id']}/rows", params={"status": "problems"})).json()
        assert [(r["row_no"], [i["code"] for i in r["issues"]]) for r in problems["items"]] == [
            (3, ["INVALID_EMAIL"]),
            (4, ["DUPLICATE_IN_FILE"]),
        ]

        report = await c.get(f"{BASE}/{first['id']}/report.xlsx")
        assert report.status_code == 200
        assert report.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "attachment" in report.headers["content-disposition"]
        sheet = load_workbook(io.BytesIO(report.content))["Checked rows"]
        assert sheet["F3"].value.startswith("Error: ") and "email" in sheet["F3"].value

        blocked = await c.post(f"{BASE}/{first['id']}/commit", json={})
        assert blocked.status_code == 409 and "2 row(s) have errors" in blocked.json()["detail"]
        assert await _students(infra, t.id) == {}  # nothing touched live data

        fixed = _csv(
            "Enrollment No.,Name,Email,Cohort",
            f"A001,Asha Rao,asha@example.com,{s.cohort_code}",
            f"A002,Bilal Khan,bilal@example.com,{s.sibling_cohort_code}",
        )
        r = await _upload(
            c, fixed, "students-fixed.csv", session_id=str(s.session_id), supersedes_id=first["id"]
        )
        second = r.json()
        assert second["supersedes_id"] == first["id"]
        assert (await c.get(f"{BASE}/{first['id']}")).json()["status"] == "cancelled"
        job = await _checked(c, infra, second["id"])
        assert job["status"] == "validated" and job["rows_error"] == 0 and job["summary"]["create"] == 2

        committing = await c.post(f"{BASE}/{second['id']}/commit", json={})
        assert committing.status_code == 202 and committing.json()["status"] == "committing"
        again = await c.post(f"{BASE}/{second['id']}/commit", json={})  # double click
        assert again.status_code == 202 and again.json()["status"] == "committing"
        done = await _checked(c, infra, second["id"])
        assert done["status"] == "committed" and done["committed_by_name"] == "Owner Person"
        assert done["summary"]["result"]["created"] == 2

        students = await _students(infra, t.id)
        assert set(students) == {"A001", "A002"} and students["A002"].email == "bilal@example.com"
        async with infra.db.uow(t.id) as uow:
            members = {
                (m.student_id, m.cohort_id)
                for m in (await uow.session.scalars(select(CohortMembership))).all()
            }
            usage = (await EntitlementService(infra).usage(uow))["active_students"]
        assert members == {(students["A001"].id, s.cohort_id), (students["A002"].id, s.sibling_cohort_id)}
        assert usage == 2
        audit = (await c.get("/api/v1/admin/audit-logs", params={"entity_id": second["id"]})).json()["items"]
        assert {"import.uploaded", "import.committed"} <= {e["action"] for e in audit}

        listing = (await c.get(BASE, params={"kind": "students"})).json()
        assert [i["status"] for i in listing] == ["committed", "cancelled"]


async def test_same_file_resumes_and_a_committed_file_is_reported(app, infra) -> None:
    t = await make_tenant(infra)
    data = _csv("Enrollment,Name", "B001,Bea", "B002,Ben")
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        first = (await _upload(c, data)).json()
        again = (await _upload(c, data)).json()
        assert again["id"] == first["id"] and again["resumed"] is True
        await _checked(c, infra, first["id"])
        await c.post(f"{BASE}/{first['id']}/commit", json={})
        await drain_jobs(infra, ["imports"])
        dup = await _upload(c, data)
        assert dup.status_code == 409 and dup.json()["import_id"] == first["id"]
        assert "already imported" in dup.json()["detail"]


async def test_unrecognised_headers_need_mapping(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        r = await _upload(c, _csv("ID Code,Pupil,Notes", "C001,Chitra,x", "C002,Chetan,y"))
        job = await _checked(c, infra, r.json()["id"])
        assert job["status"] == "needs_mapping"
        assert {i["code"] for i in job["file_issues"]} == {"MISSING_COLUMN"}
        assert job["columns"] == ["ID Code", "Pupil", "Notes"]
        bad = await c.put(
            f"{BASE}/{job['id']}/mapping", json={"mapping": {"enrollment_no": 0, "full_name": 0}}
        )
        assert bad.status_code == 422
        r = await c.put(f"{BASE}/{job['id']}/mapping", json={"mapping": {"enrollment_no": 0, "full_name": 1}})
        assert r.status_code == 202 and r.json()["status"] == "validating"
        job = await _checked(c, infra, job["id"])
        assert job["status"] == "validated" and job["rows_valid"] == 2
        assert job["mapping"] == {"enrollment_no": 0, "full_name": 1}


async def test_upsert_updates_and_moves_while_create_only_skips(app, infra) -> None:
    t = await make_tenant(infra)
    s = await make_structure(infra, t)
    sid = await make_student(infra, t, enrollment_no="D001", full_name="Dev Old", cohort_id=s.cohort_id)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        data = _csv("Enrollment,Name,Cohort", f"D001,Dev New,{s.sibling_cohort_code}", "D002,Dia,")
        skip = (await _upload(c, data, mode="create_only")).json()
        job = await _checked(c, infra, skip["id"])
        assert job["summary"]["skip"] == 1 and job["summary"]["create"] == 1 and job["rows_warning"] == 1
        await c.post(f"{BASE}/{skip['id']}/cancel", json={})
        assert (await c.get(f"{BASE}/{skip['id']}")).json()["status"] == "cancelled"

        up = (await _upload(c, data)).json()  # same bytes, but the earlier job was cancelled
        assert up["id"] != skip["id"]
        job = await _checked(c, infra, up["id"])
        assert job["summary"]["update"] == 1 and job["summary"]["create"] == 1
        await c.post(f"{BASE}/{up['id']}/commit", json={})
        done = await _checked(c, infra, up["id"])
        assert done["summary"]["result"] == {
            "created": 1,
            "updated": 1,
            "unchanged": 0,
            "skipped": 0,
            "placed_in_cohorts": 1,
            "moved_between_cohorts": 1,
        }
    students = await _students(infra, t.id)
    assert students["D001"].full_name == "Dev New" and students["D001"].version == 2
    async with infra.db.uow(t.id) as uow:
        cohort = (
            await uow.session.scalars(
                select(CohortMembership.cohort_id).where(CohortMembership.student_id == sid)
            )
        ).all()
    assert cohort == [s.sibling_cohort_id]


async def test_commit_refused_by_the_seat_limit_writes_nothing_and_can_be_retried(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        r = await _upload(c, _csv("Enrollment,Name", "E001,Ena", "E002,Eli", "E003,Esa"))
        job = await _checked(c, infra, r.json()["id"])
        assert job["status"] == "validated" and job["summary"]["seats_remaining"] == 150
        async with infra.db.platform_uow() as uow:  # the plan shrinks between check and commit
            uow.session.add(
                TenantFeatureOverride(tenant_id=t.id, feature_key=F.MAX_STUDENTS, value=2, reason="test")
            )
        await EntitlementService(infra).invalidate(t.id)
        await c.post(f"{BASE}/{job['id']}/commit", json={})
        job = await _checked(c, infra, job["id"])
        assert job["status"] == "validated" and job["error_code"] == "limit-exceeded"
        assert await _students(infra, t.id) == {}

        recheck = await c.post(f"{BASE}/{job['id']}/revalidate", json={})
        assert recheck.status_code == 202
        job = await _checked(c, infra, job["id"])
        assert [i["code"] for i in job["file_issues"]] == ["LIMIT_EXCEEDED"]
        refused = await c.post(f"{BASE}/{job['id']}/commit", json={})
        assert refused.status_code == 409 and "room for 2 more" in refused.json()["detail"]


async def test_skip_errors_commits_only_valid_rows(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        r = await _upload(c, _csv("Enrollment,Name,Email", "F001,Farah,", "F002,Faiz,bad-email"))
        job = await _checked(c, infra, r.json()["id"])
        await c.post(f"{BASE}/{job['id']}/commit", json={"skip_errors": True})
        await drain_jobs(infra, ["imports"])
    assert set(await _students(infra, t.id)) == {"F001"}


async def test_hostile_and_wrong_files(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        png = await c.post(
            BASE,
            files={"file": ("students.csv", b"\x89PNG\r\n\x1a\n" + b"0" * 40, "text/csv")},
            data={"kind": "students"},
        )
        assert png.status_code == 415
        corrupt = await c.post(
            BASE,
            files={"file": ("students.xlsx", b"PK\x03\x04not really a workbook", "application/octet-stream")},
            data={"kind": "students"},
        )
        assert corrupt.status_code == 202
        job = await _checked(c, infra, corrupt.json()["id"])
        assert job["status"] == "failed" and job["error_code"] == "not-xlsx" and job["error_detail"]
        # a failed import doesn't block uploading the same bytes again later
        assert (await c.post(f"{BASE}/{job['id']}/commit", json={})).status_code == 409


async def test_template_download_and_permissions(app, infra) -> None:
    t = await make_tenant(infra)
    s = await make_structure(infra, t)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        r = await c.get(f"{BASE}/template.xlsx")
        assert r.status_code == 200 and "students-import-template.xlsx" in r.headers["content-disposition"]
        wb = load_workbook(io.BytesIO(r.content))
        formulas = [dv.formula1 for dv in wb["Data"].data_validations.dataValidation]
        assert any(s.cohort_code in (f or "") for f in formulas)
    faculty = await client_as(app, infra, t, "faculty")
    async with faculty:
        assert (await _upload(faculty, _csv("Enrollment,Name", "G1,G"))).status_code == 403
        assert (await faculty.get(BASE)).json() == []  # faculty list only their own (marks) imports
        assert (await faculty.get(f"{BASE}/template.xlsx")).status_code == 403  # students template: admins only


async def test_storage_usage_counts_uploaded_files(app, infra) -> None:
    t = await make_tenant(infra)
    data = _csv("Enrollment,Name", *(f"H{i:03},Name {i}" for i in range(50)))
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        r = await _upload(c, data)
    async with infra.db.uow(t.id) as uow:
        usage = (await EntitlementService(infra).usage(uow))["storage_bytes"]
        key = (
            await uow.session.execute(
                text(
                    "SELECT object_key FROM files WHERE id = (SELECT file_id FROM import_jobs WHERE id = :i)"
                ),
                {"i": uuid.UUID(r.json()["id"])},
            )
        ).scalar_one()
    assert usage == len(data)
    assert key.startswith(f"tenants/{t.id}/import/")
    assert await infra.storage.get(key) == data
