"""Publication and the student read path end to end (P10.1, P10.3, P10.4).

Uses the approved exam from test_results (A001 85% pass, A002 50% pass, A003 absent, B001 fail).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import asyncpg
import pytest
from sqlalchemy import text

from app.core.clock import utcnow
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.models import TenantFeatureOverride
from app.modules.entitlements.service import EntitlementService
from app.modules.publishing.service import PublishingService
from tests.conftest import PG_HOST, PG_PORT
from tests.helpers import Client
from tests.integration.test_results import Exam, _processed, _reauth

pytestmark = pytest.mark.integration

STUDENT_PW = "a-long-student-passphrase"


async def _approved(app, infra) -> Exam:
    e, o = await _processed(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        r = await c.post(f"{e.base}/approve", json={"run_id": o["run"]["id"]})
        assert r.status_code == 200, r.text
    return e


def _pubs(e: Exam) -> str:
    return f"/api/v1/admin/exams/{e.x.exam_id}/publications"


async def _publish(c: Client, e: Exam, at: str | None = None, key: str | None = None) -> Any:
    return await c.post(
        _pubs(e), json={"at": at} if at else {}, headers={"Idempotency-Key": key or uuid.uuid4().hex}
    )


async def _logins(app, e: Exam, *enrollments: str) -> None:
    """Give students of cohort A (and B) accounts through activation codes."""
    async with Client(app, e.x.t.host) as admin:
        await admin.login(e.x.t.owner_email)
        slips: dict[str, str] = {}
        for cohort in (e.x.s.cohort_id, e.x.s.sibling_cohort_id):
            r = await admin.post("/api/v1/admin/activation-codes", json={"cohort_id": str(cohort)})
            slips |= {i["enrollment_no"]: i["code"] for i in r.json()["issued"]}
    for enrollment in enrollments:
        async with Client(app, e.x.t.host) as s:
            r = await s.post(
                "/api/v1/auth/activate",
                json={"enrollment_no": enrollment, "code": slips[enrollment], "password": STUDENT_PW},
            )
            assert r.status_code == 200, r.text


async def _as_student(app, e: Exam, enrollment: str) -> Client:
    c = Client(app, e.x.t.host)
    await c.login(enrollment, STUDENT_PW)
    return c


async def _counts(infra, tenant_id: uuid.UUID) -> tuple[int, int, int]:
    counts = []
    async with infra.db.uow(tenant_id) as uow:
        for table in ("publications", "published_results", "exam_statistics"):
            counts.append((await uow.session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())
    return counts[0], counts[1], counts[2]


async def test_publishing_now_shows_each_student_only_their_own_result(app, infra) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001", "A002")
    async with await _as_student(app, e, "A001") as a1:
        assert (await a1.get("/api/v1/me/results")).json() == []  # nothing before publication
        assert (await a1.get("/api/v1/me/results/latest")).json() is None
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        r = await _publish(c, e)
        assert r.status_code == 201, r.text
        pub = r.json()
        assert (pub["status"], pub["version"], pub["students"]) == ("published", 1, 4)
        assert pub["published_at"] and len(pub["content_hash"]) == 64
        assert (await c.get(f"/api/v1/admin/exams/{e.x.exam_id}")).json()["status"] == "published"
        assert (await c.get(e.base)).json()["run"]["status"] == "published"
        assert (await c.get("/api/v1/me/results")).status_code == 403  # staff have no student view
        audit = (await c.get("/api/v1/admin/audit-logs", params={"action": "publication.published"})).json()
        assert audit["items"][0]["after"]["students"] == 4

    async with await _as_student(app, e, "A001") as a1:
        listed = await a1.get("/api/v1/me/results")
        assert listed.headers["cache-control"] == "private, no-store"
        items = listed.json()
        assert [(i["publication_id"], i["outcome"], i["sgpa"], i["revised"]) for i in items] == [
            (pub["id"], "pass", "9", False)
        ]
        latest = (await a1.get("/api/v1/me/results/latest")).json()
        p = latest["payload"]
        assert p["student"]["enrollment_no"] == "A001" and p["result"]["percentage"] == "85"
        assert p["papers"][0]["components"] == [
            {"code": "INT", "label": "Internal", "max": "40", "marks": "35"},
            {"code": "EXT", "label": "External", "max": "60", "marks": "50"},
        ]
        assert p["institution"]["name"] and p["exam"]["name"] == "Finals"
        stats = (await a1.get(f"/api/v1/me/results/{pub['id']}/stats")).json()
        assert stats["available"] is True and set(stats["stats"]) == {"average_percentage", "papers"}

    # The same publication id, asked for by another student, answers with *their* result: identity comes
    # only from the session, so there is no way to name someone else.
    async with await _as_student(app, e, "A002") as a2:
        mine = (await a2.get(f"/api/v1/me/results/{pub['id']}")).json()
        assert mine["payload"]["student"]["enrollment_no"] == "A002"
        assert mine["payload"]["result"]["percentage"] == "50"
        assert (await a2.get(f"/api/v1/me/results/{uuid.uuid4()}")).status_code == 404


async def test_snapshots_cannot_be_changed_by_anyone(app, infra, migrated_db: str) -> None:
    e = await _approved(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await _publish(c, e)).status_code == 201
    # The app has no grant; even the table owner is refused by the trigger.
    for user, password, error in (
        ("scorecode_app", "app-dev-pw", "permission denied"),
        ("scorecode_migrator", "migrator-dev-pw", "published results are immutable"),
    ):
        for sql in ("UPDATE published_results SET payload_hash = 'x'", "DELETE FROM exam_statistics"):
            conn = await asyncpg.connect(
                host=PG_HOST, port=PG_PORT, user=user, password=password, database=migrated_db
            )
            try:
                async with conn.transaction():
                    await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(e.x.t.id))
                    with pytest.raises(asyncpg.PostgresError, match=error):
                        await conn.execute(sql)
            finally:
                await conn.close()


async def test_a_failure_half_way_through_publishing_leaves_nothing_behind(app, infra, monkeypatch) -> None:
    e = await _approved(app, infra)
    real = PublishingService._insert

    async def half_then_fail(uow, rows):
        await real(uow, rows[: len(rows) // 2])
        raise RuntimeError("storage went away")

    monkeypatch.setattr(PublishingService, "_insert", staticmethod(half_then_fail))
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        key = uuid.uuid4().hex
        with pytest.raises(RuntimeError, match="storage went away"):  # in production: a 500
            await _publish(c, e, key=key)
        assert await _counts(infra, e.x.t.id) == (0, 0, 0)
        assert (await c.get(f"/api/v1/admin/exams/{e.x.exam_id}")).json()["status"] == "approved"
        monkeypatch.undo()
        r = await _publish(c, e, key=key)  # the key wasn't kept either: the retry does the work
        assert r.status_code == 201 and r.json()["students"] == 4
        assert await _counts(infra, e.x.t.id) == (1, 4, 1)


async def test_scheduled_publication_goes_live_later_or_can_be_cancelled(app, infra) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001")
    at = (utcnow() + timedelta(hours=2)).isoformat()
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        soon = await _publish(c, e, at=(utcnow() + timedelta(seconds=30)).isoformat())
        assert soon.status_code == 422
        r = await _publish(c, e, at=at)
        assert r.status_code == 201, r.text
        pub = r.json()
        assert pub["status"] == "scheduled" and pub["published_at"] is None
        assert (await c.get(f"/api/v1/admin/exams/{e.x.exam_id}")).json()["status"] == "scheduled"
    async with infra.db.uow(e.x.t.id) as uow:
        run_at = (
            await uow.session.execute(text("SELECT run_at FROM jobs WHERE kind = 'publishing.go_live'"))
        ).scalar_one()
        assert abs((run_at - utcnow()).total_seconds() - 7200) < 60
    async with await _as_student(app, e, "A001") as a1:
        assert (await a1.get("/api/v1/me/results")).json() == []  # not yet

    assert await PublishingService(infra).go_live(e.x.t.id, uuid.UUID(pub["id"])) == {"published": pub["id"]}
    async with await _as_student(app, e, "A001") as a1:
        assert [i["publication_id"] for i in (await a1.get("/api/v1/me/results")).json()] == [pub["id"]]
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await c.get(f"/api/v1/admin/exams/{e.x.exam_id}")).json()["status"] == "published"
        r = await c.post(f"{_pubs(e)}/{pub['id']}/cancel")
        assert r.status_code == 409  # already live

    e2 = await _approved(app, infra)
    async with Client(app, e2.x.t.host) as c:
        await c.login(e2.x.t.owner_email)
        pub2 = (await _publish(c, e2, at=at)).json()
        r = await c.post(f"{_pubs(e2)}/{pub2['id']}/cancel")
        assert r.status_code == 200 and r.json()["status"] == "cancelled"
        assert (await c.get(f"/api/v1/admin/exams/{e2.x.exam_id}")).json()["status"] == "approved"
    assert await PublishingService(infra).go_live(e2.x.t.id, uuid.UUID(pub2["id"])) == {
        "skipped": "cancelled"
    }


async def test_withdrawing_hides_results_and_republishing_makes_a_new_version(app, infra) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001")
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        v1 = (await _publish(c, e)).json()
        r = await c.post(f"{_pubs(e)}/{v1['id']}/withdraw", json={"reason": "Wrong exam picked"})
        assert r.status_code == 200 and r.json()["status"] == "withdrawn"
        assert r.json()["withdraw_reason"] == "Wrong exam picked"
        assert (await c.get(f"/api/v1/admin/exams/{e.x.exam_id}")).json()["status"] == "withdrawn"
    async with await _as_student(app, e, "A001") as a1:
        assert (await a1.get("/api/v1/me/results")).json() == []
        assert (await a1.get(f"/api/v1/me/results/{v1['id']}")).status_code == 404
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        await _reauth(c)
        v2 = (await _publish(c, e)).json()
        assert (v2["version"], v2["status"]) == (2, "published")
        listed = (await c.get(_pubs(e))).json()
        assert [(p["version"], p["status"]) for p in listed] == [(2, "published"), (1, "withdrawn")]
    async with await _as_student(app, e, "A001") as a1:
        items = (await a1.get("/api/v1/me/results")).json()
        assert [(i["publication_id"], i["revised"]) for i in items] == [(v2["id"], True)]


async def test_publishing_needs_approved_results_reauth_and_room_in_the_plan(app, infra) -> None:
    e, _ = await _processed(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        r = await _publish(c, e)
        assert r.status_code == 409 and "approved" in r.json()["detail"]

    e = await _approved(app, infra)
    async with infra.db.platform_uow() as uow:
        uow.session.add(
            TenantFeatureOverride(
                tenant_id=e.x.t.id, feature_key=F.MAX_PUBLISHED_EXAMS_PER_YEAR, value=0, reason="test"
            )
        )
    await EntitlementService(infra).invalidate(e.x.t.id)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        async with infra.db.uow(e.x.t.id) as uow:
            await uow.session.execute(
                text("UPDATE sessions SET reauthenticated_at = now() - interval '1 hour'")
            )
        r = await _publish(c, e)
        assert r.status_code == 401 and r.json()["code"] == "reauth-required"
        await _reauth(c)
        r = await _publish(c, e)
        assert r.status_code == 402 and r.json()["limit"] == F.MAX_PUBLISHED_EXAMS_PER_YEAR
        assert await _counts(infra, e.x.t.id) == (0, 0, 0)
