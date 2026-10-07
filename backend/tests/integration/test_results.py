"""Result processing, preview and approval end to end (P9.1–P9.4).

Hand-worked expectations (credit_10_point, paper 40% to pass, External needs 21 of 60, 4 credits):
A001 35+50 = 85% → A+ (9), A002 20+30 = 50% → B (6), A003 absent, B001 10+15 → External below its
minimum → F (0), so the exam outcomes are 2 pass, 1 fail, 1 absent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import text

from tests.helpers import DEFAULT_PASSWORD, Client, drain_jobs, make_user
from tests.integration.test_marks import Setup, _setup, change

pytestmark = pytest.mark.integration


@dataclass
class Exam:
    x: Setup

    @property
    def base(self) -> str:
        return f"/api/v1/admin/exams/{self.x.exam_id}/results"

    @property
    def exam(self) -> str:
        return f"/api/v1/admin/exams/{self.x.exam_id}"


async def _entered(app, infra, *, close: bool = True) -> Exam:
    x = await _setup(app, infra)
    a1, a2, a3 = x.students
    async with infra.db.uow(x.t.id) as uow:
        await uow.session.execute(text("UPDATE exam_papers SET credits = 4"))
    async with Client(app, x.t.host) as c:
        await c.login(x.t.owner_email)
        r = await c.put(
            x.sheet(),
            json={
                "changes": [
                    change(a1, INT="35", EXT="50"),
                    change(a2, INT="20", EXT="30"),
                    change(a3, attendance="absent"),
                ]
            },
        )
        assert r.status_code == 200, r.text
        r = await c.put(
            x.sheet(x.s.sibling_cohort_id), json={"changes": [change(x.other_student, INT="10", EXT="15")]}
        )
        assert r.status_code == 200, r.text
        if close:
            r = await c.post(f"/api/v1/admin/exams/{x.exam_id}/transitions", json={"action": "close_entry"})
            assert r.status_code == 200, r.text
    return Exam(x)


async def _process(
    c: Client, e: Exam, *, key: str | None = None, reason: str | None = "Marks checked"
) -> Any:
    return await c.post(
        f"{e.base}/process",
        json={"override_reason": reason},
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
    )


async def _reauth(c: Client) -> None:
    assert (await c.post("/api/v1/auth/reauth", json={"password": DEFAULT_PASSWORD})).status_code == 200


async def _processed(app, infra) -> tuple[Exam, dict[str, Any]]:
    e = await _entered(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await _process(c, e)).status_code == 202
    await drain_jobs(infra, ["processing"])
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        overview = (await c.get(e.base)).json()
    assert overview["run"]["status"] == "completed", overview["run"]
    return e, overview


async def test_processing_needs_closed_entry_and_submitted_papers_or_a_reason(app, infra) -> None:
    e = await _entered(app, infra, close=False)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        r = await _process(c, e)
        assert r.status_code == 409 and "Close marks entry" in r.json()["detail"]
        await c.post(f"{e.exam}/transitions", json={"action": "close_entry"})

        r = await c.post(f"{e.base}/process", json={})
        assert r.status_code == 422 and "Idempotency-Key" in r.json()["detail"]
        r = await _process(c, e, reason=None)
        assert r.status_code == 409
        assert [u["status"] for u in r.json()["unsubmitted"]] == ["open", "open"]
        assert "aren't submitted yet" in r.json()["detail"]

        key = uuid.uuid4().hex
        first = await _process(c, e, key=key, reason="Faculty confirmed by phone")
        assert first.status_code == 202, first.text
        assert first.json()["run"]["status"] == "running" and first.json()["run"]["revision"] == 1
        assert first.json()["actions"]["can_process"] is False
        replay = await _process(c, e, key=key, reason="Faculty confirmed by phone")
        assert replay.status_code == 202 and replay.headers.get("idempotent-replayed") == "true"
        busy = await _process(c, e)
        assert busy.status_code == 409 and "already being processed" in busy.json()["detail"]

    assert await drain_jobs(infra, ["processing"]) == 1
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        o = (await c.get(e.base)).json()
        run = o["run"]
        assert o["exam_status"] == "processed" and [r["revision"] for r in o["runs"]] == [1]
        assert run["status"] == "completed" and run["students"] == 4
        assert run["override_reason"] == "Faculty confirmed by phone"
        assert run["scheme"] == {"name": "Scale", "version": 1}
        assert run["stats"]["outcomes"] == {"pass": 2, "fail": 1, "absent": 1, "withheld": 0, "incomplete": 0}
        assert run["stats"]["pass_percentage"] == "66.7"
        assert len(run["input_hash"]) == len(run["content_hash"]) == 64
        unsubmitted = next(a for a in run["anomalies"] if a["code"] == "UNSUBMITTED")
        assert unsubmitted["count"] == 2
        assert o["actions"] == {
            "can_process": True,
            "can_discard": True,
            "can_approve": True,
            "can_reject": True,
            "can_revoke": False,
            "approve_blocked_reason": None,
        }
        audit = (await c.get("/api/v1/admin/audit-logs", params={"entity_id": e.x.exam_id})).json()["items"]
        actions = [a["action"] for a in audit]
        assert "results.processing_started" in actions and "results.processed" in actions
        started = next(a for a in audit if a["action"] == "results.processing_started")
        assert started["reason"] == "Faculty confirmed by phone"


async def test_the_preview_lists_every_student_with_their_papers(app, infra) -> None:
    e, o = await _processed(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        page = (await c.get(f"{e.base}/students")).json()
        assert page["run_id"] == o["run"]["id"]
        rows = {s["enrollment_no"]: s for s in page["items"]}
        assert list(rows) == ["A001", "A002", "A003", "B001"]
        a1 = rows["A001"]
        assert (a1["outcome"], a1["total"], a1["percentage"], a1["sgpa"], a1["credits_earned"]) == (
            "pass",
            "85.000",
            "85.000",
            "9.000",
            "4.00",
        )
        assert a1["papers"][0]["grade"] == "A+" and a1["papers"][0]["components"] == {
            "INT": "35",
            "EXT": "50",
        }
        assert (rows["A002"]["papers"][0]["grade"], rows["A002"]["sgpa"]) == ("B", "6.000")
        assert rows["A003"]["outcome"] == "absent" and rows["A003"]["papers"][0]["attendance"] == "absent"
        b1 = rows["B001"]
        assert b1["outcome"] == "fail" and b1["papers"][0]["failed_components"] == ["EXT"]
        assert b1["cohort_code"] != a1["cohort_code"]

        failed = (await c.get(f"{e.base}/students", params={"outcome": "fail"})).json()["items"]
        assert [s["enrollment_no"] for s in failed] == ["B001"]
        found = (await c.get(f"{e.base}/students", params={"q": "a00"})).json()["items"]
        assert [s["enrollment_no"] for s in found] == ["A001", "A002", "A003"]
        first = (await c.get(f"{e.base}/students", params={"limit": 2})).json()
        assert [s["enrollment_no"] for s in first["items"]] == ["A001", "A002"] and first[
            "next_after"
        ] == "A002"
        rest = (await c.get(f"{e.base}/students", params={"limit": 2, "after": "A002"})).json()
        assert [s["enrollment_no"] for s in rest["items"]] == ["A003", "B001"] and rest["next_after"] is None
        one = (await c.get(f"{e.base}/students/{e.x.students[1]}")).json()
        assert one["enrollment_no"] == "A002" and one["papers"][0]["total"] == "50.000"


async def test_processing_twice_gives_identical_results(app, infra) -> None:
    e, first = await _processed(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await _process(c, e)).status_code == 202
    await drain_jobs(infra, ["processing"])
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        second = (await c.get(e.base)).json()
        assert second["run"]["revision"] == 2 and second["exam_status"] == "processed"
        assert [(r["revision"], r["status"]) for r in second["runs"]] == [(2, "completed"), (1, "stale")]
        assert second["run"]["input_hash"] == first["run"]["input_hash"]
        assert second["run"]["content_hash"] == first["run"]["content_hash"]
        assert second["run"]["stats"] == first["run"]["stats"]
        rows = [
            (await c.get(f"{e.base}/students", params={"run_id": run_id})).json()["items"]
            for run_id in (first["run"]["id"], second["run"]["id"])
        ]
        assert rows[0] == rows[1]
        assert not any(a["code"] == "CHANGED" for a in second["run"]["anomalies"])


async def test_a_mark_change_after_processing_makes_results_stale_and_blocks_approval(app, infra) -> None:
    e, o = await _processed(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        sheet = (await c.get(e.x.sheet())).json()
        assert sheet["can_edit"] is True  # administrators may still correct marks
        version = sheet["students"][1]["entry"]["version"]
        r = await c.put(e.x.sheet(), json={"changes": [change(e.x.students[1], version, INT="25")]})
        assert r.status_code == 200, r.text
        now = (await c.get(e.base)).json()
        assert now["exam_status"] == "marks_entry_closed" and now["run"]["status"] == "stale"
        assert now["actions"]["can_approve"] is False and now["actions"]["can_process"] is True
        await _reauth(c)
        r = await c.post(f"{e.base}/approve", json={"run_id": o["run"]["id"]})
        assert r.status_code == 409 and "Process the results again" in r.json()["detail"]

        assert (await _process(c, e)).status_code == 202
    await drain_jobs(infra, ["processing"])
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        changed = next(a for a in (await c.get(e.base)).json()["run"]["anomalies"] if a["code"] == "CHANGED")
        assert changed["items"][0]["enrollment_no"] == "A002"
        assert changed["items"][0]["detail"] == "Total 50 → 55"  # still a B, so only the total moved


async def test_approval_needs_reauth_and_the_latest_run_then_locks_marks(app, infra) -> None:
    e, o = await _processed(app, infra)
    run_id = o["run"]["id"]
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        async with infra.db.uow(e.x.t.id) as uow:
            await uow.session.execute(
                text("UPDATE sessions SET reauthenticated_at = now() - interval '1 hour'")
            )
        r = await c.post(f"{e.base}/approve", json={"run_id": run_id})
        assert r.status_code == 401 and r.json()["code"] == "reauth-required"
        await _reauth(c)
        r = await c.post(f"{e.base}/approve", json={"run_id": str(uuid.uuid4())})
        assert r.status_code == 409 and "processed again" in r.json()["detail"]

        r = await c.post(
            f"{e.base}/approve", json={"run_id": run_id, "comment": "Checked against the register"}
        )
        assert r.status_code == 200, r.text
        done = r.json()
        assert done["exam_status"] == "approved" and done["run"]["status"] == "approved"
        assert done["actions"]["can_revoke"] is True and done["actions"]["can_process"] is False
        approval = done["approvals"][0]
        assert approval["decision"] == "approved" and approval["revision"] == 1
        assert approval["content_hash"] == o["run"]["content_hash"]
        assert approval["comment"] == "Checked against the register" and approval["decided_by_name"]

        sheet = (await c.get(e.x.sheet())).json()
        assert sheet["submission_status"] == "locked" and sheet["can_edit"] is False
        r = await c.put(e.x.sheet(), json={"changes": [change(e.x.students[0], 1, INT="1")]})
        assert r.status_code == 409
        audit = (await c.get("/api/v1/admin/audit-logs", params={"action": "results.approved"})).json()[
            "items"
        ]
        assert audit[0]["after"]["content_hash"] == o["run"]["content_hash"]

        r = await c.post(f"{e.base}/revoke", json={"reason": "Wrong scheme picked"})
        assert r.status_code == 200, r.text
        back = r.json()
        assert back["exam_status"] == "processed" and back["run"]["status"] == "completed"
        assert [a["decision"] for a in back["approvals"]] == ["revoked", "approved"]
        assert (await c.get(e.x.sheet())).json()["submission_status"] == "submitted"


async def test_approval_rechecks_every_input_even_when_staleness_was_bypassed(app, infra) -> None:
    e, o = await _processed(app, infra)
    async with infra.db.uow(e.x.t.id) as uow:  # a change that didn't go through the marks service
        await uow.session.execute(
            text('UPDATE mark_entries SET components = \'{"INT": "36", "EXT": "50"}\' WHERE student_id = :s'),
            {"s": e.x.students[0]},
        )
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        await _reauth(c)
        r = await c.post(f"{e.base}/approve", json={"run_id": o["run"]["id"]})
        assert r.status_code == 409 and "changed after processing" in r.json()["detail"]
        assert (await c.get(e.base)).json()["exam_status"] == "processed"  # nothing was approved


async def test_maker_checker_needs_a_second_administrator(app, infra) -> None:
    e, o = await _processed(app, infra)  # enterprise: the feature is in the plan
    async with infra.db.uow(e.x.t.id) as uow:
        await uow.session.execute(text("UPDATE tenant_settings SET approval_mode = 'maker_checker'"))
    _, checker = await make_user(infra, e.x.t, "institution_admin")
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        view = (await c.get(e.base)).json()
        assert view["approval_mode"] == "maker_checker" and view["actions"]["can_approve"] is False
        assert "Another administrator" in view["actions"]["approve_blocked_reason"]
        await _reauth(c)
        r = await c.post(f"{e.base}/approve", json={"run_id": o["run"]["id"]})
        assert r.status_code == 403 and "Another administrator" in r.json()["detail"]
    async with Client(app, e.x.t.host) as c:
        await c.login(checker)
        assert (await c.get(e.base)).json()["actions"]["can_approve"] is True
        r = await c.post(f"{e.base}/reject", json={"run_id": o["run"]["id"], "reason": "A002 looks low"})
        assert r.status_code == 200 and r.json()["exam_status"] == "processed"
        assert r.json()["approvals"][0]["decision"] == "rejected"
        r = await c.post(f"{e.base}/approve", json={"run_id": o["run"]["id"]})
        assert r.status_code == 200 and r.json()["exam_status"] == "approved"


async def test_a_run_that_cannot_be_graded_fails_with_a_reason_and_changes_nothing(app, infra) -> None:
    e = await _entered(app, infra)
    async with infra.db.uow(e.x.t.id) as uow:  # a maximum lowered below a mark already entered
        await uow.session.execute(
            text(
                "UPDATE exam_papers SET components = "
                '\'[{"code": "INT", "label": "Internal", "max": "30"}, '
                '{"code": "EXT", "label": "External", "max": "60", "min_pass": "21"}]\''
            )
        )
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await _process(c, e)).status_code == 202
    await drain_jobs(infra, ["processing"])
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        o = (await c.get(e.base)).json()
        assert o["run"]["status"] == "failed" and o["run"]["error_detail"].startswith("A001: ")
        assert o["exam_status"] == "marks_entry_closed" and o["actions"]["can_process"] is True
    async with infra.db.uow(e.x.t.id) as uow:
        assert (
            await uow.session.execute(text("SELECT count(*) FROM student_exam_results"))
        ).scalar_one() == 0


async def test_discarding_results_goes_back_to_marks_entry(app, infra) -> None:
    e, _ = await _processed(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        r = await c.post(f"{e.base}/discard", json={"reason": "A paper was missed"})
        assert r.status_code == 200, r.text
        assert r.json()["exam_status"] == "marks_entry_closed" and r.json()["run"]["status"] == "stale"
        r = await c.post(f"{e.exam}/transitions", json={"action": "reopen_entry", "reason": "Add the paper"})
        assert r.status_code == 200 and r.json()["status"] == "marks_entry_open"


async def test_computed_results_and_decisions_are_append_only_for_the_app(app, infra) -> None:
    e, _ = await _processed(app, infra)
    for sql in (
        "UPDATE student_exam_results SET total = 0",
        "DELETE FROM student_exam_results",
        "UPDATE student_paper_results SET total = 0",
        "DELETE FROM approvals",
        "DELETE FROM result_runs",
    ):
        with pytest.raises(Exception, match="permission denied"):
            async with infra.db.uow(e.x.t.id) as uow:
                await uow.session.execute(text(sql))
