"""Exam setup and lifecycle (P7.4, P7.5): schema guarantees, setup rules, opening marks entry."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.examinations.models import PaperAssignment, PaperSubmission
from app.modules.grading.service import GradingService
from app.modules.grading.templates import BY_KEY
from tests.helpers import Client, client_as, make_structure, make_student, make_tenant, make_user

pytestmark = pytest.mark.integration

BASE = "/api/v1/admin/exams"
THEORY = [
    {"code": "INT", "label": "Internal", "max": "40"},
    {"code": "EXT", "label": "External", "max": "60", "min_pass": "21"},
]


async def _scheme(infra, t) -> uuid.UUID:
    async with infra.db.uow(t.id) as uow:
        s = await GradingService(infra).create(
            uow,
            None,
            name=f"Scheme {uuid.uuid4().hex[:4]}",
            description=None,
            config=BY_KEY["credit_10_point"].config,
        )
        return s.id


async def test_exam_setup_and_opening_marks_entry(app, infra) -> None:
    t = await make_tenant(infra, plan="enterprise")
    s = await make_structure(infra, t)
    other = await make_structure(infra, t, current=False)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        no_scheme = await c.post(BASE, json={"name": "Mid-term", "term_id": str(s.term_id)})
        assert no_scheme.status_code == 422 and no_scheme.json()["field"] == "grading_scheme_id"
        scheme_id = await _scheme(infra, t)  # the first scheme becomes the default

        wrong = await c.post(
            BASE, json={"name": "Mid-term", "term_id": str(s.term_id), "cohort_ids": [str(other.cohort_id)]}
        )
        assert wrong.status_code == 422 and "another session" in wrong.json()["detail"]
        r = await c.post(
            BASE,
            json={
                "name": "Mid-term",
                "kind": "term",
                "term_id": str(s.term_id),
                "cohort_ids": [str(s.cohort_id)],
            },
        )
        assert r.status_code == 201, r.text
        exam = r.json()
        assert exam["status"] == "draft" and exam["grading_scheme_id"] == str(scheme_id)
        assert [x["code"] for x in exam["cohorts"]] == [s.cohort_code]
        assert exam["term"]["session_code"] == s.session_code
        assert [a["action"] for a in exam["actions"]] == ["open_entry"]
        assert {k["key"]: k["ok"] for k in exam["checks"]} == {
            "cohorts": True,
            "students": False,
            "papers": False,
            "grading": True,
        }
        dup = await c.post(BASE, json={"name": " mid-TERM ", "term_id": str(s.term_id)})
        assert dup.status_code == 409 and dup.json()["field"] == "name"

        url = f"{BASE}/{exam['id']}"
        too_high = await c.post(
            f"{url}/papers", json={"course_id": str(s.course_id), "components": THEORY, "pass_total": "101"}
        )
        assert too_high.status_code == 422 and too_high.json()["field"] == "pass_total"
        bad = await c.post(
            f"{url}/papers",
            json={"course_id": str(s.course_id), "components": [{**THEORY[1], "min_pass": "61"}]},
        )
        assert bad.status_code == 422 and bad.json()["field"] == "components.0"
        r = await c.post(
            f"{url}/papers", json={"course_id": str(s.course_id), "components": THEORY, "pass_total": "40"}
        )
        assert r.status_code == 201, r.text
        paper = r.json()["papers"][0]
        assert paper["max_total"] == "100.00" and paper["pass_total"] == "40.00"
        assert [x["code"] for x in paper["components"]] == ["INT", "EXT"]
        again = await c.post(f"{url}/papers", json={"course_id": str(s.course_id), "components": THEORY})
        assert again.status_code == 409 and again.json()["field"] == "course_id"

        blocked = await c.post(f"{url}/transitions", json={"action": "open_entry"})
        assert blocked.status_code == 409 and "No students yet" in blocked.json()["detail"]
        await make_student(infra, t, cohort_id=s.cohort_id)
        await make_student(infra, t, cohort_id=s.cohort_id)
        opened = await c.post(f"{url}/transitions", json={"action": "open_entry"})
        assert opened.status_code == 200, opened.text
        body = opened.json()
        assert body["status"] == "marks_entry_open" and body["cohorts"][0]["students"] == 2
        assert body["papers"][0]["submissions"] == [
            {"cohort_id": str(s.cohort_id), "status": "open", "submitted_at": None}
        ]

        # a cohort added after opening gets its submission rows; removing one is no longer allowed
        r = await c.put(f"{url}/cohorts", json={"cohort_ids": [str(s.cohort_id), str(s.sibling_cohort_id)]})
        assert len(r.json()["papers"][0]["submissions"]) == 2
        r = await c.put(f"{url}/cohorts", json={"cohort_ids": [str(s.cohort_id)]})
        assert r.status_code == 409
        assert (await c.delete(f"{url}/papers/{paper['id']}")).status_code == 409
        assert (await c.delete(url)).status_code == 409

        closed = await c.post(f"{url}/transitions", json={"action": "close_entry"})
        assert closed.json()["status"] == "marks_entry_closed"
        no_reason = await c.post(f"{url}/transitions", json={"action": "reopen_entry"})
        assert no_reason.status_code == 422 and no_reason.json()["field"] == "reason"
        reopened = await c.post(
            f"{url}/transitions", json={"action": "reopen_entry", "reason": "Late re-test"}
        )
        assert reopened.json()["status"] == "marks_entry_open"
        assert (await c.post(f"{url}/transitions", json={"action": "open_entry"})).status_code == 409
        audit = (await c.get("/api/v1/admin/audit-logs", params={"entity_id": exam["id"]})).json()["items"]
        actions = {e["action"] for e in audit}
        assert {
            "exam.created",
            "exam.paper_added",
            "exam.open_entry",
            "exam.close_entry",
            "exam.reopen_entry",
        } <= actions
        assert next(e for e in audit if e["action"] == "exam.reopen_entry")["reason"] == "Late re-test"

        listed = (await c.get(BASE)).json()
        assert [(x["name"], x["papers"], x["cohorts"]) for x in listed] == [("Mid-term", 1, 2)]
        assert (await c.get(BASE, params={"status": "draft"})).json() == []


async def test_update_versioning_and_delete_draft(app, infra) -> None:
    t = await make_tenant(infra)
    s = await make_structure(infra, t)
    first = await _scheme(infra, t)
    second = await _scheme(infra, t)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        exam = (
            await c.post(BASE, json={"name": "Unit test 1", "kind": "unit_test", "term_id": str(s.term_id)})
        ).json()
        url = f"{BASE}/{exam['id']}"
        body = {"version": 1, "name": "Unit test 1", "kind": "unit_test", "grading_scheme_id": str(second)}
        r = await c.put(url, json=body)
        assert r.json()["grading_scheme_id"] == str(second) and r.json()["version"] == 2
        stale = await c.put(url, json={**body, "grading_scheme_id": str(first)})
        assert stale.status_code == 409 and stale.json()["current_version"] == 2
        assert (await c.delete(url)).status_code == 204
        assert (await c.get(url)).status_code == 404


async def test_faculty_assignments(app, infra) -> None:
    t = await make_tenant(infra, plan="enterprise")
    s = await make_structure(infra, t)
    await _scheme(infra, t)
    teacher, _ = await make_user(infra, t, "faculty")
    admin, _ = await make_user(infra, t, "institution_admin")
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        exam = (
            await c.post(
                BASE, json={"name": "Finals", "term_id": str(s.term_id), "cohort_ids": [str(s.cohort_id)]}
            )
        ).json()
        url = f"{BASE}/{exam['id']}"
        paper = (
            await c.post(f"{url}/papers", json={"course_id": str(s.course_id), "components": THEORY})
        ).json()["papers"][0]
        assign = f"{url}/papers/{paper['id']}/assignments"
        r = await c.put(assign, json={"cohort_id": str(s.cohort_id), "user_ids": [str(teacher)]})
        assert [(a["user_id"], a["full_name"]) for a in r.json()["papers"][0]["assignments"]] == [
            (str(teacher), "Faculty Person")
        ]
        not_faculty = await c.put(assign, json={"cohort_id": str(s.cohort_id), "user_ids": [str(admin)]})
        assert not_faculty.status_code == 422 and not_faculty.json()["field"] == "user_ids"
        not_sitting = await c.put(
            assign, json={"cohort_id": str(s.sibling_cohort_id), "user_ids": [str(teacher)]}
        )
        assert not_sitting.status_code == 422 and not_sitting.json()["field"] == "cohort_id"
        cleared = await c.put(assign, json={"cohort_id": str(s.cohort_id), "user_ids": []})
        assert cleared.json()["papers"][0]["assignments"] == []

    # The database itself refuses an assignment or submission for a cohort that doesn't sit the exam.
    for row in (
        PaperAssignment(
            tenant_id=t.id,
            exam_id=uuid.UUID(exam["id"]),
            exam_paper_id=uuid.UUID(paper["id"]),
            cohort_id=s.sibling_cohort_id,
            user_id=teacher,
        ),
        PaperSubmission(
            tenant_id=t.id,
            exam_id=uuid.UUID(exam["id"]),
            exam_paper_id=uuid.UUID(paper["id"]),
            cohort_id=s.sibling_cohort_id,
            status="open",
        ),
    ):
        with pytest.raises(IntegrityError, match="exam_cohort"):
            async with infra.db.uow(t.id) as uow:
                uow.session.add(row)
    # …and removing the cohort from a draft exam takes its assignments with it.
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        await c.put(
            f"{BASE}/{exam['id']}/papers/{paper['id']}/assignments",
            json={"cohort_id": str(s.cohort_id), "user_ids": [str(teacher)]},
        )
        await c.put(f"{BASE}/{exam['id']}/cohorts", json={"cohort_ids": []})
    async with infra.db.uow(t.id) as uow:
        assert (await uow.session.scalars(select(PaperAssignment))).all() == []


async def test_faculty_cannot_manage_exams(app, infra) -> None:
    t = await make_tenant(infra)
    faculty = await client_as(app, infra, t, "faculty")
    async with faculty:
        assert (await faculty.get(BASE)).status_code == 403
        assert (await faculty.post(BASE, json={"name": "X", "term_id": str(uuid.uuid4())})).status_code == 403
