"""The 30-day Pro trial (docs/12 §6): once per institution, whatever the email spelling, domain or device;
soft signals ask for a review instead of locking anyone out; expiry returns to Free and deletes nothing."""

from __future__ import annotations

import random
import uuid
from typing import Any

import asyncpg
import pytest
from sqlalchemy import select, text

from app.core.clock import utcnow
from app.core.device import DEVICE_COOKIE
from app.modules.entitlements.models import TenantTrial
from app.modules.entitlements.trial import TrialService
from tests.conftest import PG_HOST, PG_PORT
from tests.helpers import Client, TenantFixture, make_tenant, make_user, platform_client

pytestmark = pytest.mark.integration

SUB = "/api/v1/admin/subscription"


def _mail(local: str | None = None, domain: str = "gmail.com") -> str:
    return f"{local or 'p' + uuid.uuid4().hex[:10]}@{domain}"


async def _tenant(infra, email: str | None = None, name: str | None = None) -> TenantFixture:
    return await make_tenant(infra, owner_email=email or _mail(), name=name)


async def _owner(app, t: TenantFixture, *, ip: str | None = None, device: str | None = None) -> Client:
    c = Client(app, t.host, ip=ip)
    if device:
        c.http.cookies.set(DEVICE_COOKIE, device)
    await c.login(t.owner_email)
    return c


async def _start(app, t: TenantFixture, **kw: Any) -> Any:
    async with await _owner(app, t, **kw) as c:
        return await c.post(f"{SUB}/trial", json={})


async def _trial(infra, t: TenantFixture) -> TenantTrial | None:
    async with infra.db.platform_uow() as uow:
        return (
            await uow.session.scalars(select(TenantTrial).where(TenantTrial.tenant_id == t.id))
        ).one_or_none()


async def test_the_owner_starts_a_30_day_pro_trial_exactly_once(app, infra) -> None:
    t = await _tenant(infra)
    async with await _owner(app, t) as c:
        before = (await c.get(SUB)).json()
        assert before["plan_code"] == "free"
        assert before["trial"] | {"started_at": None} == {
            "state": "available",
            "days": 30,
            "plan_name": "Pro trial",
            "started_at": None,
            "ends_at": None,
            "days_left": None,
            "can_start": True,
        }
        assert c.http.cookies.get(DEVICE_COOKIE)  # issued on first visit

        r = await c.post(f"{SUB}/trial", json={})
        assert r.status_code == 200, r.text
        s = r.json()
        assert (s["plan_code"], s["status"]) == ("trial", "trialing")
        assert (
            s["trial"]["state"] == "active" and s["trial"]["days_left"] == 30 and not s["trial"]["can_start"]
        )
        limits = {limit["key"]: limit["limit"] for limit in s["limits"]}
        assert limits["max_students"] == 1000 and limits["max_published_exams_per_year"] is None
        f = s["features"]
        assert f["scheduled_publication"] and f["custom_branding"] and f["maker_checker_approval"]
        assert not f["custom_domain"] and not f["api_access"]  # held back during an unpaid month

        again = await c.post(f"{SUB}/trial", json={})
        assert again.status_code == 409
        assert again.json()["code"] == "trial-unavailable" and again.json()["reason"] == "used"
        audit = (await c.get("/api/v1/admin/audit-logs", params={"action": "trial.started"})).json()["items"]
        assert len(audit) == 1 and audit[0]["after"]["risk_score"] == 0

    async with infra.db.platform_uow() as uow:
        jobs = (
            await uow.session.execute(
                text(
                    "SELECT kind, run_at FROM jobs WHERE payload->>'tenant_id' = :t "
                    "AND kind IN ('trials.end', 'trials.remind') ORDER BY run_at"
                ),
                {"t": str(t.id)},
            )
        ).all()
        mails = (
            await uow.session.execute(
                text(
                    "SELECT count(*) FROM jobs WHERE kind = 'notifications.send_email' "
                    "AND payload->>'template' = 'trial_started' AND payload->'params'->>'to' = :to"
                ),
                {"to": t.owner_email},
            )
        ).scalar_one()
    assert [k for k, _ in jobs] == ["trials.remind", "trials.remind", "trials.end"]
    assert abs((jobs[-1][1] - utcnow()).total_seconds() - 30 * 86_400) < 120
    assert mails == 1


async def test_only_the_owner_can_start_it(app, infra) -> None:
    t = await _tenant(infra)
    _, admin_login = await make_user(infra, t, "institution_admin")
    async with Client(app, t.host) as admin:
        await admin.login(admin_login)
        view = (await admin.get(SUB)).json()
        assert view["trial"]["state"] == "available" and view["trial"]["can_start"] is False
        assert (await admin.post(f"{SUB}/trial", json={})).status_code == 403
    assert await _trial(infra, t) is None


async def test_a_second_institution_with_a_variant_of_the_same_email_is_refused(app, infra) -> None:
    local = "head" + uuid.uuid4().hex[:6]
    a = await _tenant(infra, f"{local}@gmail.com")
    b = await _tenant(infra, f"{local[:2]}.{local[2:]}+second@GoogleMail.com")
    assert (await _start(app, a)).status_code == 200
    r = await _start(app, b)
    assert r.status_code == 409 and r.json()["reason"] == "used"
    assert "support@scorecode.in" in r.json()["detail"]
    assert await _trial(infra, b) is None
    async with await _owner(app, b) as c:
        assert (await c.get(SUB)).json()["plan_code"] == "free"


async def test_one_trial_per_institutional_domain(app, infra) -> None:
    domain = f"school{uuid.uuid4().hex[:6]}.edu.in"
    a = await _tenant(infra, f"principal@{domain}")
    b = await _tenant(infra, f"exams@mail.{domain}")  # another person, same institution
    assert (await _start(app, a)).status_code == 200
    assert (await _start(app, b)).json()["reason"] == "used"


async def test_one_trial_per_device(app, infra) -> None:
    device = uuid.uuid4().hex + uuid.uuid4().hex
    a, b = await _tenant(infra), await _tenant(infra)
    assert (await _start(app, a, device=device)).status_code == 200
    assert (await _start(app, b, device=device)).json()["reason"] == "used"
    assert (await _start(app, b, device=uuid.uuid4().hex * 2)).status_code == 200  # a fresh browser


async def test_shared_soft_signals_ask_for_a_review_but_one_alone_does_not(app, infra) -> None:
    phone = f"98{random.randint(10_000_000, 99_999_999)}"
    a = await _tenant(infra, name=f"Green Valley Public School {uuid.uuid4().hex[:6]}")
    b = await _tenant(infra)
    c = await _tenant(infra, name=a.name.upper().replace(" ", "-"))
    for t in (a, b, c):  # the institution's own contact phone, which nobody verified
        async with infra.db.uow(t.id) as uow:
            await uow.session.execute(text("UPDATE tenant_settings SET contact_phone = :p"), {"p": phone})
    assert (await _start(app, a)).status_code == 200
    assert (await _start(app, b)).status_code == 200  # same phone only: allowed, flagged
    trial_b = await _trial(infra, b)
    assert trial_b is not None and (trial_b.risk_score, trial_b.flags) == (1, ["phone"])
    r = await _start(app, c)  # same phone *and* the same name, spelt differently
    assert r.status_code == 409 and r.json()["reason"] == "review"

    async with await platform_client(app, infra) as ops:
        audit = (await ops.get("/api/v1/platform/audit-logs", params={"action": "trial.refused"})).json()
        mine = [x for x in audit["items"] if x["target_tenant_id"] == str(c.id)]
        assert mine and mine[0]["after"] == {"reason": "review", "signals": ["name", "phone"]}
        # A person looked and agreed: staff start it by hand. Still only once.
        r = await ops.post(
            f"/api/v1/platform/tenants/{c.id}/trial", json={"reason": "Verified by phone call"}
        )
        assert r.status_code == 200, r.text
        r = await ops.post(f"/api/v1/platform/tenants/{c.id}/trial", json={"reason": "Twice?"})
        assert r.status_code == 409
        detail = (await ops.get(f"/api/v1/platform/tenants/{c.id}")).json()
        assert detail["trial"]["status"] == "active" and detail["trial"]["granted"] is True


async def test_many_trials_from_one_network_need_a_review(app, infra) -> None:
    net = f"45.{random.randint(1, 250)}.{random.randint(1, 250)}"
    codes = []
    for i in range(5):
        t = await _tenant(infra)
        r = await _start(app, t, ip=f"{net}.{10 + i}")
        codes.append(r.json().get("reason") if r.status_code == 409 else r.status_code)
    # 0 and 1 earlier trials: fine; 2 and 3: allowed but flagged; 4: a person has to look.
    assert codes == [200, 200, 200, 200, "review"]


async def test_the_trial_ends_on_time_back_to_free_without_losing_anything(app, infra) -> None:
    t = await _tenant(infra)
    assert (await _start(app, t)).status_code == 200
    trial = await _trial(infra, t)
    assert trial is not None
    async with infra.db.uow(t.id) as uow:  # 400 students arrived during the trial...
        await uow.session.execute(
            text(
                "INSERT INTO tenant_usage_counters (tenant_id, metric, value) VALUES (:t, 'active_students', 400) "
                "ON CONFLICT (tenant_id, metric) DO UPDATE SET value = 400"
            ),
            {"t": t.id},
        )
    async with infra.db.platform_uow() as uow:  # ...and the month passes
        await uow.session.execute(
            text(
                "UPDATE tenant_trials SET started_at = now() - interval '31 days', ends_at = now() - interval '1 day'"
                " WHERE id = :id"
            ),
            {"id": trial.id},
        )
        await uow.session.execute(
            text(
                "UPDATE tenant_subscriptions SET period_end = now() - interval '1 day' WHERE status = 'trialing'"
                " AND tenant_id = :t"
            ),
            {"t": t.id},
        )
    async with await _owner(app, t) as c:
        lapsed = (await c.get(SUB)).json()  # before the end job: already Free
        assert lapsed["plan_code"] == "free" and lapsed["trial"]["state"] == "ended"

    assert (await TrialService(infra).end(t.id, trial.id))["reason"] == "expired"
    assert (await TrialService(infra).end(t.id, trial.id)) == {"skipped": "ended"}  # idempotent
    async with await _owner(app, t) as c:
        s = (await c.get(SUB)).json()
        assert (s["plan_code"], s["status"], s["trial"]["state"]) == ("free", "active", "ended")
        assert next(x for x in s["limits"] if x["key"] == "max_students")["used"] == 400
        r = await c.post(
            "/api/v1/admin/students", json={"enrollment_no": "OVER1", "full_name": "One More Student"}
        )
        assert r.status_code == 402  # over Free's 150: nothing deleted, nothing more added
        assert (await c.post(f"{SUB}/trial", json={})).json()["reason"] == "used"


async def test_upgrading_during_the_trial_converts_it(app, infra) -> None:
    t = await _tenant(infra)
    assert (await _start(app, t)).status_code == 200
    async with await platform_client(app, infra) as ops:
        r = await ops.put(
            f"/api/v1/platform/tenants/{t.id}/plan",
            json={"plan_code": "growth", "reason": "Paid by bank transfer", "billing_ref": "INV-1"},
        )
        assert r.status_code == 200, r.text
    trial = await _trial(infra, t)
    assert trial is not None and trial.status == "converted"
    assert (await TrialService(infra).end(t.id, trial.id)) == {"skipped": "converted"}
    async with await _owner(app, t) as c:
        s = (await c.get(SUB)).json()
        assert (s["plan_code"], s["trial"]["state"]) == ("growth", "converted")


async def test_institutions_that_paid_before_are_not_offered_a_trial(app, infra) -> None:
    t = await _tenant(infra)
    async with await platform_client(app, infra) as ops:
        await ops.put(
            f"/api/v1/platform/tenants/{t.id}/plan", json={"plan_code": "starter", "reason": "Paid"}
        )
        await ops.put(f"/api/v1/platform/tenants/{t.id}/plan", json={"plan_code": "free", "reason": "Lapsed"})
    async with await _owner(app, t) as c:
        assert (await c.get(SUB)).json()["trial"]["state"] == "ineligible"
        r = await c.post(f"{SUB}/trial", json={})
        assert r.status_code == 409 and r.json()["reason"] == "ineligible"


async def test_trial_records_are_out_of_reach_of_tenants(app, infra, migrated_db: str) -> None:
    a, b = await _tenant(infra), await _tenant(infra)
    assert (await _start(app, a)).status_code == 200
    conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user="scorecode_app", password="app-dev-pw", database=migrated_db
    )
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(b.id))
            assert await conn.fetchval("SELECT count(*) FROM tenant_trials") == 0  # RLS: only B's own
            with pytest.raises(asyncpg.PostgresError, match="permission denied"):
                await conn.execute("UPDATE tenant_trials SET status = 'active'")
        async with conn.transaction():
            with pytest.raises(asyncpg.PostgresError, match="permission denied"):
                await conn.fetchval("SELECT count(*) FROM trial_claims")
    finally:
        await conn.close()


async def test_the_public_plan_catalogue(app, infra) -> None:
    t = await _tenant(infra)
    async with Client(app, t.host) as anon:
        r = await anon.get("/api/v1/plans")
        assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=300"
        body = r.json()
        assert [p["code"] for p in body["plans"]] == ["free", "starter", "growth", "pro"]
        free = body["plans"][0]["limits"]
        assert (free["max_students"], free["max_staff"], free["max_published_exams_per_year"]) == (150, 5, 6)
        assert body["trial"]["code"] == "trial" and body["trial_days"] == 30
        assert body["trial"]["limits"]["max_students"] == 1000
        assert "enterprise" not in str(body)
