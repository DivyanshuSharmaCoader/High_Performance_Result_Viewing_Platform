"""Corrections after publication (P18.3), end to end.

The exam from test_results: A001 35+50 = 85%, A002 20+30 = 50%, A003 absent, B001 fails. A correction
changes A002's internal mark from 20 to 25 (55%), so A002 is the one student whose result changes.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import Client, drain_jobs
from tests.integration.test_marks import change
from tests.integration.test_publishing import _approved, _as_student, _logins, _publish, _pubs
from tests.integration.test_results import Exam, _process, _reauth

pytestmark = pytest.mark.integration


def _corr(e: Exam) -> str:
    return f"/api/v1/admin/exams/{e.x.exam_id}/correction"


async def _version(c: Client, e: Exam, enrollment: str) -> int:
    sheet = (await c.get(e.x.sheet())).json()
    row = next(s for s in sheet["students"] if s["enrollment_no"] == enrollment)
    return int(row["entry"]["version"])


async def _set_a002(c: Client, e: Exam, internal: str) -> Any:
    a2 = e.x.students[1]
    return await c.put(
        e.x.sheet(), json={"changes": [change(a2, await _version(c, e, "A002"), INT=internal)]}
    )


async def _status(c: Client, e: Exam) -> str:
    return str((await c.get(f"/api/v1/admin/exams/{e.x.exam_id}")).json()["status"])


async def _process_and_approve(c: Client, e: Exam, infra) -> None:
    assert (await _process(c, e)).status_code == 202
    await drain_jobs(infra, ["processing"])
    o = (await c.get(e.base)).json()
    assert o["exam_status"] == "processed" and o["run"]["status"] == "completed", o["run"]
    r = await c.post(f"{e.base}/approve", json={"run_id": o["run"]["id"]})
    assert r.status_code == 200, r.text


async def _inbox_kinds(app, e: Exam, enrollment: str) -> list[str]:
    async with await _as_student(app, e, enrollment) as s:
        return [n["kind"] for n in (await s.get("/api/v1/me/notifications")).json()["items"]]


async def test_a_correction_keeps_the_live_version_then_replaces_it_and_tells_only_changed_students(
    app, infra
) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001", "A002")
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        v1 = (await _publish(c, e)).json()
        assert (await _set_a002(c, e, "25")).status_code == 409  # published: marks are locked

        assert (await c.post(_corr(e), json={"reason": "x"})).status_code == 422  # a reason is required
        r = await c.post(_corr(e), json={"reason": "A002's internal mark was entered as 20, it is 25"})
        assert r.status_code == 201, r.text
        assert r.json()["in_progress"] and r.json()["exam_status"] == "correction_draft"
        assert (await c.post(_corr(e), json={"reason": "twice"})).status_code == 409
        exam = (await c.get(f"/api/v1/admin/exams/{e.x.exam_id}")).json()
        assert exam["correction_reason"].startswith("A002's internal mark")
        listed = (await c.get("/api/v1/admin/exams")).json()
        assert next(x for x in listed if x["id"] == str(e.x.exam_id))["correcting"] is True

        preview = (await c.get(f"{_corr(e)}/preview")).json()
        assert (preview["live_version"], preview["revision"], preview["changed"]) == (1, None, 0)
        r = await _set_a002(c, e, "25")
        assert r.status_code == 200, r.text

    # Students still see version 1 while the correction is prepared.
    async with await _as_student(app, e, "A002") as a2:
        latest = (await a2.get("/api/v1/me/results/latest")).json()
        assert latest["publication_id"] == v1["id"] and latest["payload"]["result"]["percentage"] == "50"

    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await _process(c, e)).status_code == 202
        await drain_jobs(infra, ["processing"])
        preview = (await c.get(f"{_corr(e)}/preview")).json()
        assert preview["changed"] == 1 and preview["students"] == 4
        (only,) = preview["changes"]
        assert only["enrollment_no"] == "A002"
        assert (only["before"]["percentage"], only["after"]["percentage"]) == ("50", "55")
        o = (await c.get(e.base)).json()
        r = await c.post(f"{e.base}/approve", json={"run_id": o["run"]["id"]})
        assert r.status_code == 200, r.text
        await _reauth(c)
        v2 = await _publish(c, e)
        assert v2.status_code == 201, v2.text
        assert v2.json()["version"] == 2
        listed = (await c.get(_pubs(e))).json()
        assert [(p["version"], p["status"]) for p in listed] == [(2, "published"), (1, "superseded")]
        assert await _status(c, e) == "published"
        exam = (await c.get(f"/api/v1/admin/exams/{e.x.exam_id}")).json()
        assert exam["correction_started_at"] is None and exam["correction_reason"] is None
        audit = (await c.get("/api/v1/admin/audit-logs", params={"entity_id": e.x.exam_id})).json()["items"]
        published = next(
            a for a in audit if a["action"] == "publication.published" and a["after"]["version"] == 2
        )
        assert published["after"]["students_changed"] == 1 and published["after"]["supersedes_version"] == 1
        assert published["reason"].startswith("A002's internal mark")
        assert any(a["action"] == "exam.correction_started" for a in audit)

    await drain_jobs(infra, ["notifications"])
    # Version 1 told everyone; version 2 only the student whose result changed.
    assert await _inbox_kinds(app, e, "A002") == ["result_revised", "result_published"]
    assert await _inbox_kinds(app, e, "A001") == ["result_published"]
    async with await _as_student(app, e, "A002") as a2:
        latest = (await a2.get("/api/v1/me/results/latest")).json()
        assert latest["publication_id"] == v2.json()["id"] and latest["revised"] is True
        assert latest["payload"]["result"]["percentage"] == "55"
        assert (await a2.get(f"/api/v1/me/results/{v1['id']}")).status_code == 404  # superseded


async def test_a_correction_can_be_cancelled_only_while_no_mark_changed(app, infra) -> None:
    e = await _approved(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        await _publish(c, e)
        assert (await c.delete(_corr(e))).status_code == 409  # nothing to cancel
        assert (await c.post(_corr(e), json={"reason": "check a mark"})).status_code == 201
        r = await c.delete(_corr(e))
        assert r.status_code == 200 and r.json() == {
            "in_progress": False,
            "started_at": None,
            "reason": None,
            "exam_status": "published",
        }
        assert (await _set_a002(c, e, "25")).status_code == 409  # locked again

        assert (await c.post(_corr(e), json={"reason": "check a mark again"})).status_code == 201
        assert (await _set_a002(c, e, "25")).status_code == 200
        r = await c.delete(_corr(e))
        assert r.status_code == 409 and "changed during this correction" in r.json()["detail"]
        # Processed and approved, then put back: the results equal the live ones again.
        await _process_and_approve(c, e, infra)
        assert (await c.delete(_corr(e))).status_code == 409
        r = await c.post(f"{e.base}/revoke", json={"reason": "put the mark back"})
        assert r.status_code == 200, r.text
        assert (await c.post(f"{e.base}/discard", json={"reason": "put the mark back"})).status_code == 200
        assert (await _set_a002(c, e, "20")).status_code == 200
        r = await c.delete(_corr(e))
        assert r.status_code == 200, r.text
        assert await _status(c, e) == "published"
        audit = (await c.get("/api/v1/admin/audit-logs", params={"entity_id": e.x.exam_id})).json()["items"]
        assert [a["action"] for a in audit].count("exam.correction_cancelled") == 2


async def test_republishing_the_same_results_is_refused(app, infra) -> None:
    e = await _approved(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        await _publish(c, e)
        assert (await c.post(_corr(e), json={"reason": "a false alarm"})).status_code == 201
        await _process_and_approve(c, e, infra)
        await _reauth(c)
        r = await _publish(c, e)
        assert r.status_code == 409 and "already live" in r.json()["detail"]


async def test_withdrawing_during_a_correction_hides_the_live_version_and_keeps_the_correction(
    app, infra
) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001")
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        v1 = (await _publish(c, e)).json()
        assert (await c.post(_corr(e), json={"reason": "a wrong mark"})).status_code == 201
        assert (await _set_a002(c, e, "25")).status_code == 200
        r = await c.post(f"{_pubs(e)}/{v1['id']}/withdraw", json={"reason": "a wrong mark is live"})
        assert r.status_code == 200 and r.json()["status"] == "withdrawn"
        assert await _status(c, e) == "correction_draft"
    async with await _as_student(app, e, "A001") as a1:
        assert (await a1.get("/api/v1/me/results")).json() == []
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        await _process_and_approve(c, e, infra)
        await _reauth(c)
        v2 = await _publish(c, e)
        assert v2.status_code == 201 and v2.json()["version"] == 2
    await drain_jobs(infra, ["notifications"])
    # Nothing was live to compare with, so everyone hears about the new version.
    assert "result_revised" in await _inbox_kinds(app, e, "A001")


async def test_only_published_results_can_be_corrected(app, infra) -> None:
    e = await _approved(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        r = await c.post(_corr(e), json={"reason": "too early"})
        assert r.status_code == 409
        assert (await c.get(f"{_corr(e)}/preview")).status_code == 409
