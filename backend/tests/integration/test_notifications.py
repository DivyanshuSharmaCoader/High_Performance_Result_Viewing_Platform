"""Notifications when results are published (P12.1–P12.3): the inbox, email and preferences.

Uses the approved exam from test_results: A001, A002, A003 and B001.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.core.clock import utcnow
from app.modules.notifications.service import Notifier
from app.modules.publishing.service import PublishingService
from tests.helpers import Client, drain_jobs, mailpit_latest
from tests.integration.test_publishing import STUDENT_PW, _approved, _as_student, _logins, _publish, _pubs
from tests.integration.test_results import Exam, _reauth

pytestmark = pytest.mark.integration


async def _with_email(infra, e: Exam, enrollment: str) -> str:
    address = f"{enrollment.lower()}-{uuid.uuid4().hex[:8]}@students.example.org"
    async with infra.db.uow(e.x.t.id) as uow:
        await uow.session.execute(
            text(
                "UPDATE users SET email = :m WHERE id = (SELECT user_id FROM students WHERE enrollment_no = :e)"
            ),
            {"m": address, "e": enrollment},
        )
    return address


async def _inbox(app, e: Exam, enrollment: str) -> dict[str, Any]:
    async with Client(app, e.x.t.host) as c:
        await c.login(enrollment, STUDENT_PW)
        r = await c.get("/api/v1/me/notifications")
        assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
        return r.json()


async def _deliveries(infra, e: Exam) -> list[tuple[str, str]]:
    async with infra.db.uow(e.x.t.id) as uow:
        rows = await uow.session.execute(
            text(
                "SELECT s.enrollment_no, d.status FROM notification_deliveries d "
                "JOIN students s ON s.user_id = d.user_id ORDER BY s.enrollment_no"
            )
        )
        return [tuple(r) for r in rows.all()]  # type: ignore[misc]


async def test_publishing_tells_each_student_in_the_app_and_by_email(app, infra) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001", "A002", "B001")
    a001 = await _with_email(infra, e, "A001")
    await _with_email(infra, e, "A002")
    async with await _as_student(app, e, "A002") as a2:  # A002 doesn't want these emails
        r = await a2.put("/api/v1/me/preferences", json={"email_results": False})
        assert r.status_code == 200 and r.json() == {"email_results": False}
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        pub = (await _publish(c, e)).json()
    assert (await _inbox(app, e, "A001"))["items"] == []  # the fan-out runs in the background
    await drain_jobs(infra, ["notifications"])

    inbox = await _inbox(app, e, "A001")
    assert inbox["unread"] == 1
    [note] = inbox["items"]
    assert note["kind"] == "result_published" and note["read"] is False
    assert note["title"] == "Finals results are available"
    assert note["link"] == f"/me/results/{pub['id']}"
    # Everyone with an account gets the in-app notice, opted out of email or not.
    assert (await _inbox(app, e, "A002"))["unread"] == 1
    assert (await _inbox(app, e, "B001"))["unread"] == 1

    # Email: only A001 has an address and wants it. It links to the result and carries no marks.
    assert await _deliveries(infra, e) == [("A001", "sent")]
    mail = await mailpit_latest(a001)
    assert mail["subject"] == "Finals results are available"
    assert f"{infra.settings.tenant_origin(e.x.t.slug)}/me/results/{pub['id']}" in mail["text"]
    assert "%" not in mail["text"]  # (the HTML layout has width="100%"; the link holds digits)
    for leak in ("SGPA", "Internal", "External", "Passed", "Grade"):
        assert leak not in mail["text"] and leak not in mail["html"], leak
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await c.get(_pubs(e))).json()[0]["emails"] == {
            "queued": 0,
            "sent": 1,
            "failed": 0,
            "skipped": 0,
        }

    # Running the fan-out again (a retried job) notifies nobody twice.
    assert await Notifier(infra).publication_live(e.x.t.id, uuid.UUID(pub["id"])) == {
        "notified": 3,
        "emails_queued": 0,
    }
    await drain_jobs(infra, ["notifications"])
    assert (await _inbox(app, e, "A001"))["unread"] == 1
    assert await _deliveries(infra, e) == [("A001", "sent")]


async def test_reading_notifications_is_personal(app, infra) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001", "A002")
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        await _publish(c, e)
    await drain_jobs(infra, ["notifications"])
    theirs = (await _inbox(app, e, "A002"))["items"][0]["id"]
    async with await _as_student(app, e, "A001") as a1:
        mine = (await a1.get("/api/v1/me/notifications")).json()["items"][0]["id"]
        assert (await a1.post(f"/api/v1/me/notifications/{theirs}/read")).status_code == 404
        assert (await a1.post(f"/api/v1/me/notifications/{mine}/read")).status_code == 200
        assert (await a1.get("/api/v1/me/notifications/unread-count")).json() == {"unread": 0}
        assert (await a1.post(f"/api/v1/me/notifications/{mine}/read")).status_code == 200  # idempotent
    assert (await _inbox(app, e, "A002"))["unread"] == 1  # untouched
    async with await _as_student(app, e, "A002") as a2:
        assert (await a2.post("/api/v1/me/notifications/read-all")).json() == {"updated": 1}
        assert (await a2.post("/api/v1/me/notifications/read-all")).json() == {"updated": 0}
        assert (await a2.get("/api/v1/me/preferences")).json() == {"email_results": True}


async def test_no_email_when_the_institution_turns_it_off(app, infra) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001")
    await _with_email(infra, e, "A001")
    async with infra.db.uow(e.x.t.id) as uow:
        await uow.session.execute(text("UPDATE tenant_settings SET publish_notify_email = false"))
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        await _publish(c, e)
    await drain_jobs(infra, ["notifications"])
    assert (await _inbox(app, e, "A001"))["unread"] == 1
    assert await _deliveries(infra, e) == []


async def test_a_scheduled_release_notifies_when_it_goes_live_and_a_revision_says_so(app, infra) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001")
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        pub = (await _publish(c, e, at=(utcnow() + timedelta(hours=2)).isoformat())).json()
    await drain_jobs(infra, ["notifications"])
    assert (await _inbox(app, e, "A001"))["items"] == []  # nothing before go-live
    await PublishingService(infra).go_live(e.x.t.id, uuid.UUID(pub["id"]))
    await drain_jobs(infra, ["notifications"])
    assert (await _inbox(app, e, "A001"))["unread"] == 1

    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        await _reauth(c)
        await c.post(f"{_pubs(e)}/{pub['id']}/withdraw", json={"reason": "Wrong exam picked"})
        v2 = (await _publish(c, e)).json()
    await drain_jobs(infra, ["notifications"])
    items = (await _inbox(app, e, "A001"))["items"]
    assert [(i["kind"], i["title"]) for i in items] == [
        ("result_revised", "Your Finals result was revised"),
        ("result_published", "Finals results are available"),
    ]
    assert items[0]["link"] == f"/me/results/{v2['id']}"


async def test_results_withdrawn_before_the_fan_out_notify_nobody(app, infra) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001")
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        pub = (await _publish(c, e)).json()
        await _reauth(c)
        await c.post(f"{_pubs(e)}/{pub['id']}/withdraw", json={"reason": "Wrong exam picked"})
    assert await Notifier(infra).publication_live(e.x.t.id, uuid.UUID(pub["id"])) == {"skipped": "withdrawn"}
    await drain_jobs(infra, ["notifications"])
    assert (await _inbox(app, e, "A001"))["items"] == []


async def test_email_failures_are_retried_then_marked_failed(app, infra, monkeypatch) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001", "A002")
    good = await _with_email(infra, e, "A001")
    bad = await _with_email(infra, e, "A002")
    real = infra.mailer.send

    async def flaky(email: Any) -> str:
        if email.to == bad:
            raise ConnectionError("provider down")
        return await real(email)

    monkeypatch.setattr(infra.mailer, "send", flaky)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        pub = (await _publish(c, e)).json()
    notifier = Notifier(infra)
    await notifier.publication_live(e.x.t.id, uuid.UUID(pub["id"]))
    async with infra.db.uow(e.x.t.id) as uow:
        ids = list(
            (await uow.session.execute(text("SELECT id FROM notification_deliveries"))).scalars().all()
        )
    with pytest.raises(RuntimeError, match="1 of 2 emails failed"):
        await notifier.send_batch(e.x.t.id, ids, final_attempt=False)
    assert await _deliveries(infra, e) == [("A001", "sent"), ("A002", "queued")]
    assert (await notifier.send_batch(e.x.t.id, ids, final_attempt=True)) == {
        "sent": 0,
        "failed": 1,
        "skipped": 0,
    }
    assert await _deliveries(infra, e) == [("A001", "sent"), ("A002", "failed")]
    async with infra.db.uow(e.x.t.id) as uow:
        attempts, error = (
            await uow.session.execute(
                text("SELECT attempts, last_error FROM notification_deliveries WHERE status = 'failed'")
            )
        ).one()
    assert (attempts, error) == (2, "ConnectionError")
    assert (await mailpit_latest(good))["subject"] == "Finals results are available"
