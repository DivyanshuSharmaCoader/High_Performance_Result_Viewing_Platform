"""Plans & entitlements (P4.1–P4.3): catalogue sync idempotency, table-driven resolution,
the last-seats race, and provisioning completeness."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.core.clock import utcnow
from app.core.errors import FeatureNotInPlan, LimitExceeded
from app.modules.entitlements.catalogue import FEATURES, F
from app.modules.entitlements.models import Plan, TenantFeatureOverride, TenantSubscription
from app.modules.entitlements.service import EntitlementService
from app.modules.entitlements.sync import sync_catalogue
from tests.helpers import make_tenant

pytestmark = pytest.mark.integration


async def test_catalogue_sync_is_idempotent(infra) -> None:
    again = await sync_catalogue(infra.db)
    assert again == {"plans_added": 0, "plan_values_added": 0}
    async with infra.db.platform_uow() as uow:
        codes = (await uow.session.scalars(select(Plan.code).order_by(Plan.sort_order))).all()
        n_values = (await uow.session.execute(text("SELECT count(*) FROM plan_features"))).scalar_one()
    assert list(codes) == ["free", "starter", "growth", "trial", "pro", "enterprise"]
    assert n_values == len(codes) * len(FEATURES)


async def _set_subscription(infra, tenant_id, *, plan: str, status: str = "active", period_end=None) -> None:
    async with infra.db.platform_uow() as uow:
        await uow.session.execute(
            text("UPDATE tenant_subscriptions SET status = 'cancelled' WHERE tenant_id = :t"),
            {"t": tenant_id},
        )
        plan_id = (await uow.session.scalars(select(Plan.id).where(Plan.code == plan))).one()
        uow.session.add(
            TenantSubscription(tenant_id=tenant_id, plan_id=plan_id, status=status, period_end=period_end)
        )


async def _override(infra, tenant_id, key, value, expires_at=None) -> None:
    async with infra.db.platform_uow() as uow:
        uow.session.add(
            TenantFeatureOverride(
                tenant_id=tenant_id, feature_key=key, value=value, reason="test", expires_at=expires_at
            )
        )


async def _effective(infra, tenant_id):
    async with infra.db.uow(tenant_id) as uow:
        return await EntitlementService(infra).effective(uow, fresh=True)


@pytest.mark.parametrize(
    ("plan", "status", "period_end_days", "expect_plan", "max_students", "scheduled"),
    [
        ("free", "active", None, "free", 150, False),
        ("starter", "active", 30, "starter", 600, False),
        ("growth", "trialing", 14, "growth", 2000, True),
        ("growth", "past_due", -3, "growth", 2000, True),  # grace period keeps plan values
        ("pro", "active", -1, "free", 150, False),  # lapsed, not yet flipped → free values
        ("enterprise", "active", None, "enterprise", None, True),  # None = unlimited
    ],
)
async def test_resolution_table(
    infra, plan, status, period_end_days, expect_plan, max_students, scheduled
) -> None:
    t = await make_tenant(infra)
    end = utcnow() + timedelta(days=period_end_days) if period_end_days is not None else None
    await _set_subscription(infra, t.id, plan=plan, status=status, period_end=end)
    ent = await _effective(infra, t.id)
    assert ent.plan_code == expect_plan
    assert ent.limit(F.MAX_STUDENTS) == max_students
    assert ent.has(F.SCHEDULED_PUBLICATION) is scheduled


async def test_overrides_win_until_they_expire(infra) -> None:
    t = await make_tenant(infra)
    await _override(infra, t.id, F.MAX_STUDENTS, 999)
    await _override(infra, t.id, F.SCHEDULED_PUBLICATION, True, expires_at=utcnow() - timedelta(minutes=1))
    ent = await _effective(infra, t.id)
    assert ent.limit(F.MAX_STUDENTS) == 999
    assert ent.has(F.SCHEDULED_PUBLICATION) is False  # expired override ignored
    assert ent.overrides == [F.MAX_STUDENTS]
    with pytest.raises(FeatureNotInPlan):
        ent.require(F.CUSTOM_DOMAIN)


async def test_no_subscription_falls_back_to_free(infra) -> None:
    t = await make_tenant(infra, plan="pro")
    async with infra.db.platform_uow() as uow:
        await uow.session.execute(
            text("UPDATE tenant_subscriptions SET status = 'expired' WHERE tenant_id = :t"), {"t": t.id}
        )
    ent = await _effective(infra, t.id)
    assert ent.plan_code == "free" and ent.subscription_status == "expired"


async def test_parallel_consumers_racing_for_the_last_seats(infra) -> None:
    """Free plan: 150 students. Usage at 140; two concurrent imports of 10 each → exactly one succeeds."""
    t = await make_tenant(infra)
    async with infra.db.uow(t.id) as uow:
        await EntitlementService(infra).set_usage(uow, "active_students", 140)

    started = asyncio.Event()

    async def importer() -> str:
        try:
            async with infra.db.uow(t.id) as uow:
                await EntitlementService(infra).consume(uow, F.MAX_STUDENTS, 10)
                started.set()
                await asyncio.sleep(0.2)  # hold the row lock while the other importer waits
            return "ok"
        except LimitExceeded as exc:
            return f"limit:{exc.extra['current']}"

    results = await asyncio.gather(importer(), importer())
    assert sorted(results) == ["limit:150", "ok"]
    async with infra.db.uow(t.id) as uow:
        assert (await EntitlementService(infra).usage(uow))["active_students"] == 150


async def test_provisioning_creates_a_complete_tenant(infra) -> None:
    t = await make_tenant(infra, plan="growth", name="Complete Institute")
    async with infra.db.uow(t.id) as uow:
        q = lambda sql: uow.session.execute(text(sql))  # noqa: E731
        assert (await q("SELECT name FROM tenants")).scalar_one() == "Complete Institute"
        assert (await q("SELECT official_name FROM tenant_settings")).scalar_one() == "Complete Institute"
        assert (await q("SELECT display_name FROM tenant_branding")).scalar_one() == "Complete Institute"
        assert (
            await q("SELECT count(*) FROM tenant_subscriptions WHERE status = 'active'")
        ).scalar_one() == 1
        counters = dict((await q("SELECT metric, value FROM tenant_usage_counters")).all())
        assert counters == {
            "active_students": 0,
            "staff_users": 1,
            "admin_users": 1,
            "storage_bytes": 0,
            "published_exams_year": 0,
        }
        assert (await q("SELECT role FROM user_roles")).scalar_one() == "institution_owner"
        assert (await q("SELECT action FROM audit_logs")).scalars().all() == ["tenant.created"]
