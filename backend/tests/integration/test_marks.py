"""Marks entry (P8.1, P8.2, P8.4): validated, optimistic, audited saves; faculty scope; submit/return."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.modules.examinations.models import ExamPaper
from app.modules.grading.service import GradingService
from app.modules.grading.templates import BY_KEY
from tests.helpers import (
    Client,
    Structure,
    TenantFixture,
    make_structure,
    make_student,
    make_tenant,
    make_user,
)

pytestmark = pytest.mark.integration

THEORY = [
    {"code": "INT", "label": "Internal", "max": "40"},
    {"code": "EXT", "label": "External", "max": "60", "min_pass": "21"},
]


@dataclass
class Setup:
    t: TenantFixture
    s: Structure
    exam_id: str
    paper_id: str
    students: list[uuid.UUID]  # in cohort A
    other_student: uuid.UUID  # in cohort B
    faculty_login: str
    stranger_login: str

    def sheet(self, cohort_id: uuid.UUID | None = None) -> str:
        return f"/api/v1/exams/{self.exam_id}/papers/{self.paper_id}/cohorts/{cohort_id or self.s.cohort_id}/marks"


async def _setup(app, infra, *, open_entry: bool = True) -> Setup:
    t = await make_tenant(infra, plan="enterprise")
    s = await make_structure(infra, t)
    async with infra.db.uow(t.id) as uow:
        await GradingService(infra).create(
            uow, None, name="Scale", description=None, config=BY_KEY["credit_10_point"].config
        )
    students = [
        await make_student(infra, t, enrollment_no=f"A00{i}", cohort_id=s.cohort_id) for i in range(1, 4)
    ]
    other = await make_student(infra, t, enrollment_no="B001", cohort_id=s.sibling_cohort_id)
    faculty_id, faculty_login = await make_user(infra, t, "faculty")
    _, stranger_login = await make_user(infra, t, "faculty")
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        exam = (
            await c.post(
                "/api/v1/admin/exams",
                json={
                    "name": "Finals",
                    "term_id": str(s.term_id),
                    "cohort_ids": [str(s.cohort_id), str(s.sibling_cohort_id)],
                },
            )
        ).json()
        paper = (
            await c.post(
                f"/api/v1/admin/exams/{exam['id']}/papers",
                json={"course_id": str(s.course_id), "components": THEORY},
            )
        ).json()["papers"][0]
        await c.put(
            f"/api/v1/admin/exams/{exam['id']}/papers/{paper['id']}/assignments",
            json={"cohort_id": str(s.cohort_id), "user_ids": [str(faculty_id)]},
        )
        if open_entry:
            r = await c.post(f"/api/v1/admin/exams/{exam['id']}/transitions", json={"action": "open_entry"})
            assert r.status_code == 200, r.text
    return Setup(t, s, exam["id"], paper["id"], students, other, faculty_login, stranger_login)


def change(
    student: uuid.UUID, version: int | None = None, attendance: str = "present", **components: str | None
):
    return {
        "student_id": str(student),
        "attendance": attendance,
        "components": components,
        "version": version,
    }


async def test_saving_marks_is_validated_canonical_and_audited(app, infra) -> None:
    x = await _setup(app, infra)
    a1, a2, a3 = x.students
    async with Client(app, x.t.host) as c:
        await c.login(x.t.owner_email)
        sheet = (await c.get(x.sheet())).json()
        assert [s["enrollment_no"] for s in sheet["students"]] == ["A001", "A002", "A003"]
        assert sheet["can_edit"] and sheet["submission_status"] == "open" and sheet["complete"] == 0

        r = await c.put(
            x.sheet(), json={"changes": [change(a1, INT="35.50", EXT="50"), change(a2, INT="20")]}
        )
        assert r.status_code == 200, r.text
        saved = {e["student_id"]: e["entry"] for e in r.json()}
        assert (
            saved[str(a1)]["components"] == {"INT": "35.5", "EXT": "50"}
            and saved[str(a1)]["total"] == "85.50"
        )
        assert saved[str(a1)]["complete"] is True and saved[str(a1)]["version"] == 1
        assert saved[str(a2)]["total"] is None and saved[str(a2)]["complete"] is False  # EXT still missing

        same = await c.put(x.sheet(), json={"changes": [change(a1, 1, INT="35.5", EXT="50.00")]})
        assert same.json()[0]["entry"]["version"] == 1  # unchanged → no new version
        r = await c.put(x.sheet(), json={"changes": [change(a1, 1, INT="36")]})
        assert r.json()[0]["entry"]["version"] == 2 and r.json()[0]["entry"]["components"]["EXT"] == "50"

        stale = await c.put(
            x.sheet(), json={"changes": [change(a1, 1, INT="10"), change(a3, None, INT="12")]}
        )
        assert stale.status_code == 409
        assert stale.json()["conflicts"] == [{"student_id": str(a1), "current_version": 2}]
        assert (await c.get(x.sheet())).json()["students"][2]["entry"] is None  # nothing saved, not even a3

        for bad, field in (
            (change(a3, INT="41"), "INT"),
            (change(a3, EXT="20.125"), "EXT"),
            (change(a3, INT="ten"), "INT"),
            (change(a3, INT="-1"), "INT"),
        ):
            r = await c.put(x.sheet(), json={"changes": [bad]})
            assert r.status_code == 422 and r.json()["field"] == field, (bad, r.text)
        unknown = await c.put(x.sheet(), json={"changes": [change(a3, LAB="5")]})
        assert unknown.status_code == 422
        outsider = await c.put(x.sheet(), json={"changes": [change(x.other_student, INT="5")]})
        assert outsider.status_code == 422 and "isn't in the cohort" in outsider.json()["detail"]

        absent = await c.put(x.sheet(), json={"changes": [change(a2, 1, "absent")]})
        entry = absent.json()[0]["entry"]
        assert entry["attendance"] == "absent" and entry["components"] == {} and entry["total"] is None
        assert entry["complete"] is True

        audit = (await c.get("/api/v1/admin/audit-logs", params={"action": "marks.entered"})).json()["items"]
        first = audit[-1]["after"]
        assert first["paper"] == x.s.course_code and first["cohort"] == x.s.cohort_code
        assert {"student": "A001", "from": None, "to": "EXT 50, INT 35.5"} in first["changes"]
        latest = audit[0]["after"]["changes"]
        assert latest == [{"student": "A002", "from": "INT 20", "to": "absent"}]


async def test_faculty_see_and_edit_only_their_papers(app, infra) -> None:
    x = await _setup(app, infra)
    async with Client(app, x.t.host) as c:
        await c.login(x.faculty_login)
        work = (await c.get("/api/v1/marking")).json()
        assert [(w["course_code"], w["cohort_code"], w["students"]) for w in work] == [
            (x.s.course_code, x.s.cohort_code, 3)
        ]
        ok = await c.put(x.sheet(), json={"changes": [change(x.students[0], INT="30", EXT="40")]})
        assert ok.status_code == 200
        assert (await c.get(x.sheet(x.s.sibling_cohort_id))).status_code == 404  # not assigned there
        assert (
            await c.put(x.sheet(x.s.sibling_cohort_id), json={"changes": [change(x.other_student, INT="1")]})
        ).status_code == 404
        assert (await c.get(f"/api/v1/admin/exams/{x.exam_id}")).status_code == 403  # no admin views
    async with Client(app, x.t.host) as c:
        await c.login(x.stranger_login)
        assert (await c.get("/api/v1/marking")).json() == []
        assert (await c.get(x.sheet())).status_code == 404
    async with Client(app, x.t.host) as c:
        await c.login(x.t.owner_email)
        assert len((await c.get("/api/v1/marking")).json()) == 2  # admins see every paper × cohort


async def test_closed_entry_locks_faculty_but_not_admins(app, infra) -> None:
    x = await _setup(app, infra)
    async with Client(app, x.t.host) as admin:
        await admin.login(x.t.owner_email)
        await admin.post(f"/api/v1/admin/exams/{x.exam_id}/transitions", json={"action": "close_entry"})
        async with Client(app, x.t.host) as fac:
            await fac.login(x.faculty_login)
            sheet = (await fac.get(x.sheet())).json()
            assert sheet["can_edit"] is False
            r = await fac.put(x.sheet(), json={"changes": [change(x.students[0], INT="1")]})
            assert r.status_code == 409 and "closed" in r.json()["detail"]
        assert (
            await admin.put(x.sheet(), json={"changes": [change(x.students[0], INT="1")]})
        ).status_code == 200


async def test_draft_exams_take_no_marks(app, infra) -> None:
    x = await _setup(app, infra, open_entry=False)
    async with Client(app, x.t.host) as c:
        await c.login(x.t.owner_email)
        r = await c.put(x.sheet(), json={"changes": [change(x.students[0], INT="1")]})
        assert r.status_code == 409 and "hasn't opened" in r.json()["detail"]


async def test_submit_return_and_resubmit(app, infra) -> None:
    x = await _setup(app, infra)
    a1, a2, a3 = x.students
    async with Client(app, x.t.host) as fac, Client(app, x.t.host) as admin:
        await fac.login(x.faculty_login)
        await admin.login(x.t.owner_email)
        await fac.put(x.sheet(), json={"changes": [change(a1, INT="30", EXT="40"), change(a2, INT="25")]})
        early = await fac.post(x.sheet() + "/submit")
        assert early.status_code == 409 and "2 student(s) still need marks" in early.json()["detail"]
        await fac.put(x.sheet(), json={"changes": [change(a2, 1, EXT="45"), change(a3, None, "exempt")]})
        submitted = await fac.post(x.sheet() + "/submit")
        assert submitted.status_code == 200, submitted.text
        body = submitted.json()
        assert (
            body["submission_status"] == "submitted" and body["can_edit"] is False and body["complete"] == 3
        )
        assert body["submitted_by_name"] == "Faculty Person"
        locked = await fac.put(x.sheet(), json={"changes": [change(a1, 1, INT="31")]})
        assert locked.status_code == 409 and "submitted" in locked.json()["detail"]
        assert (await fac.post(x.sheet() + "/return", json={"reason": "Fix A002"})).status_code == 403

        returned = await admin.post(x.sheet() + "/return", json={"reason": "A002's external looks swapped"})
        assert returned.json()["submission_status"] == "returned"
        sheet = (await fac.get(x.sheet())).json()
        assert sheet["can_edit"] and sheet["return_reason"] == "A002's external looks swapped"
        await fac.put(x.sheet(), json={"changes": [change(a2, 2, EXT="54")]})
        assert (await fac.post(x.sheet() + "/submit")).json()["submission_status"] == "submitted"
        audit = (await admin.get("/api/v1/admin/audit-logs", params={"entity_id": x.exam_id})).json()["items"]
        actions = [e["action"] for e in audit]
        assert actions.count("paper.submitted") == 2 and "paper.returned" in actions


async def test_a_paper_with_marks_cannot_be_deleted(app, infra) -> None:
    x = await _setup(app, infra)
    async with Client(app, x.t.host) as c:
        await c.login(x.t.owner_email)
        await c.put(x.sheet(), json={"changes": [change(x.students[0], INT="1")]})
    with pytest.raises(IntegrityError, match="fk_mark_entries__paper"):
        async with infra.db.uow(x.t.id) as uow:
            await uow.session.execute(delete(ExamPaper).where(ExamPaper.id == uuid.UUID(x.paper_id)))
