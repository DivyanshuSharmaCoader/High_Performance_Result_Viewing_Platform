"""Marks import end to end (P8.5, P8.6): file → check → commit into mark_entries, conflicts with the grid,
faculty scope, and the pre-filled template."""

from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.modules.marks.models import MarkEntry
from tests.helpers import Client, drain_jobs
from tests.integration.test_marks import _setup, change

pytestmark = pytest.mark.integration

IMPORTS = "/api/v1/admin/imports"


async def _upload(c: Client, data: bytes, name: str = "marks.csv", **form: str):
    r = await c.post(IMPORTS, files={"file": (name, data, "text/csv")}, data={"kind": "marks", **form})
    assert r.status_code == 202, r.text
    return r.json()


async def _checked(c: Client, infra, import_id: str) -> dict:
    await drain_jobs(infra, ["imports"])
    return (await c.get(f"{IMPORTS}/{import_id}")).json()


async def test_admin_imports_marks_and_the_grid_sees_them(app, infra) -> None:
    x = await _setup(app, infra)
    course = x.s.course_code
    csv = (
        f"Roll No,Name,Course,INT,EXT\n"
        f"A001,Student Person,{course},32,45\n"
        f"A002,Student Person,{course},20,\n"
        f"A003,Student Person,{course},AB,\n"
        f"B001,Student Person,{course},10,10\n"  # sits the exam in the sibling cohort: fine for admins
        f"Z999,Nobody,{course},1,1\n"
    ).encode()
    async with Client(app, x.t.host) as c:
        await c.login(x.t.owner_email)
        job = await _upload(c, csv, exam_id=x.exam_id)
        job = await _checked(c, infra, job["id"])
        assert job["status"] == "validated" and job["params"]["exam_id"] == x.exam_id
        assert (job["rows_valid"], job["rows_warning"], job["rows_error"]) == (3, 1, 1)
        assert job["summary"]["shape"] == "long" and job["summary"]["create"] == 4
        assert {f["key"] for f in job["fields"]} >= {"enrollment_no", "course", "c:INT", "c:EXT"}
        await c.post(f"{IMPORTS}/{job['id']}/commit", json={"skip_errors": True})
        done = await _checked(c, infra, job["id"])
        assert done["status"] == "committed", done
        assert done["summary"]["result"]["created"] == 4

        sheet = (await c.get(x.sheet())).json()
        by_enrollment = {s["enrollment_no"]: s["entry"] for s in sheet["students"]}
        assert by_enrollment["A001"]["total"] == "77.00"
        assert (
            by_enrollment["A002"]["components"] == {"INT": "20"}
            and by_enrollment["A002"]["complete"] is False
        )
        assert by_enrollment["A003"]["attendance"] == "absent"
        audit = (await c.get("/api/v1/admin/audit-logs", params={"action": "marks.imported"})).json()["items"]
        assert audit[0]["after"]["created"] == 4 and audit[0]["after"]["import_id"] == job["id"]
    async with infra.db.uow(x.t.id) as uow:
        sources = {e.source for e in (await uow.session.scalars(select(MarkEntry))).all()}
    assert sources == {f"import:{job['id']}"}


async def test_a_mark_changed_in_the_grid_after_checking_refuses_the_commit(app, infra) -> None:
    x = await _setup(app, infra)
    a1 = x.students[0]
    async with Client(app, x.t.host) as c:
        await c.login(x.t.owner_email)
        await c.put(x.sheet(), json={"changes": [change(a1, INT="10", EXT="10")]})
        job = await _upload(
            c, b"Roll No,INT,EXT\nA001,35,50\n", paper_id=x.paper_id, exam_id=x.exam_id, name="ucs.csv"
        )
        job = await _checked(c, infra, job["id"])
        assert job["summary"]["shape"] == "single" and job["summary"]["update"] == 1
        await c.put(x.sheet(), json={"changes": [change(a1, 1, INT="11")]})  # a colleague, meanwhile
        await c.post(f"{IMPORTS}/{job['id']}/commit", json={})
        refused = await _checked(c, infra, job["id"])
        assert (
            refused["status"] == "validated"
            and "changed after the file was checked" in refused["error_detail"]
        )
        sheet = (await c.get(x.sheet())).json()
        assert sheet["students"][0]["entry"]["components"] == {
            "INT": "11",
            "EXT": "10",
        }  # nothing overwritten
        await c.post(f"{IMPORTS}/{job['id']}/revalidate", json={})
        await _checked(c, infra, job["id"])
        await c.post(f"{IMPORTS}/{job['id']}/commit", json={})
        assert (await _checked(c, infra, job["id"]))["status"] == "committed"
        sheet = (await c.get(x.sheet())).json()
        assert sheet["students"][0]["entry"]["components"] == {"INT": "35", "EXT": "50"}


async def test_faculty_import_only_their_own_papers_and_imports(app, infra) -> None:
    x = await _setup(app, infra)
    async with Client(app, x.t.host) as admin:
        await admin.login(x.t.owner_email)
        admins_job = await _upload(admin, b"Roll No,INT\nA001,1\n", exam_id=x.exam_id, paper_id=x.paper_id)
    async with Client(app, x.t.host) as fac:
        await fac.login(x.faculty_login)
        job = await _upload(
            fac,
            b"Roll No,Internal,External\nA001,30,40\nB001,30,40\n",
            exam_id=x.exam_id,
            paper_id=x.paper_id,
        )
        job = await _checked(fac, infra, job["id"])
        assert job["params"]["scope"] == "assigned"
        rows = (await fac.get(f"{IMPORTS}/{job['id']}/rows", params={"status": "error"})).json()["items"]
        assert [(r["row_no"], [i["code"] for i in r["issues"]]) for r in rows] == [(3, ["NOT_ASSIGNED"])]
        assert [i["id"] for i in (await fac.get(IMPORTS)).json()] == [job["id"]]
        assert (await fac.get(f"{IMPORTS}/{admins_job['id']}")).status_code == 404
        students = await fac.post(
            IMPORTS,
            files={"file": ("s.csv", b"Enrollment,Name\nX1,X\n", "text/csv")},
            data={"kind": "students"},
        )
        assert students.status_code == 403
        await fac.post(f"{IMPORTS}/{job['id']}/commit", json={"skip_errors": True})
        assert (await _checked(fac, infra, job["id"]))["status"] == "committed"


async def test_prefilled_template_round_trips(app, infra) -> None:
    x = await _setup(app, infra)
    async with Client(app, x.t.host) as c:
        await c.login(x.t.owner_email)
        r = await c.get(
            f"{IMPORTS}/template.xlsx",
            params={
                "kind": "marks",
                "exam_id": x.exam_id,
                "paper_id": x.paper_id,
                "cohort_id": str(x.s.cohort_id),
            },
        )
        assert r.status_code == 200, r.text
        wb = load_workbook(io.BytesIO(r.content))
        ws = wb["Marks"]
        assert [c.value for c in ws[1]] == ["Enrollment no.", "Name", "Internal", "External"]
        assert [ws.cell(row=i, column=1).value for i in range(2, 5)] == ["A001", "A002", "A003"]
        rules = {str(dv.sqref): dv.formula1 for dv in ws.data_validations.dataValidation}
        assert rules["C2:C4"] == 'OR(AND(ISNUMBER(C2),C2>=0,C2<=40),C2="AB",C2="EX",C2="MP",C2="WH")'
        assert "D2<=60" in rules["D2:D4"]

        ws["C2"], ws["D2"], ws["C3"], ws["D3"], ws["C4"] = 30, 45, 25, 50, "AB"
        buf = io.BytesIO()
        wb.save(buf)
        filled = await c.post(
            IMPORTS,
            files={"file": ("filled.xlsx", buf.getvalue(), "application/octet-stream")},
            data={"kind": "marks", "exam_id": x.exam_id, "paper_id": x.paper_id},
        )
        job = await _checked(c, infra, filled.json()["id"])
        assert job["mapping"] == {"enrollment_no": 0, "full_name": 1, "c:INT": 2, "c:EXT": 3}
        assert (job["rows_valid"], job["rows_error"]) == (3, 0)

        whole = await c.get(f"{IMPORTS}/template.xlsx", params={"kind": "marks", "exam_id": x.exam_id})
        head = [cell.value for cell in load_workbook(io.BytesIO(whole.content))["Marks"][1]]
        assert head == [
            "Enrollment no.",
            "Name",
            "Cohort",
            f"{x.s.course_code}_INT",
            f"{x.s.course_code}_EXT",
        ]
    async with Client(app, x.t.host) as fac:
        await fac.login(x.stranger_login)  # a faculty member assigned to nothing
        r = await fac.get(f"{IMPORTS}/template.xlsx", params={"kind": "marks", "exam_id": x.exam_id})
        assert r.status_code == 404


async def test_an_exam_with_one_paper_needs_no_course_column(app, infra) -> None:
    x = await _setup(app, infra)  # one paper
    async with Client(app, x.t.host) as c:
        await c.login(x.t.owner_email)
        job = await _upload(c, b"Roll No,Internal,External\nA001,30,40\nA002,AB,\n", exam_id=x.exam_id)
        job = await _checked(c, infra, job["id"])
        assert job["status"] == "validated", job["file_issues"]
        assert (job["rows_valid"], job["rows_error"]) == (2, 0)
        assert job["summary"]["create"] == 2 and job["summary"]["papers"] == [x.s.course_code]
        named = await _upload(c, b"Roll No,Course,INT\nA003,NOPE,5\n", exam_id=x.exam_id, name="named.csv")
        named = await _checked(c, infra, named["id"])
        rows = (await c.get(f"{IMPORTS}/{named['id']}/rows", params={"status": "error"})).json()["items"]
        assert [i["code"] for i in rows[0]["issues"]] == [
            "PAPER_NOT_IN_EXAM"
        ]  # a named course is still checked
