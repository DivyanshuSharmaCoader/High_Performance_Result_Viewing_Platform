"""Entitlement service (docs/12): the code asks "may this tenant do X?" and "would this exceed limit Z?" —
never "which plan is this tenant on?".

Resolution order per feature key: unexpired tenant override → current plan value → catalogue default.
Lapsed subscriptions fall back to the free plan's values; nothing is deleted.
Limit checks lock the tenant's usage-counter row (``SELECT … FOR UPDATE``) in the caller's transaction
so concurrent imports cannot both take the last seats.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import FeatureNotInPlan, LimitExceeded
from app.core.jobs import maintenance_task
from app.core.metrics import TENANTS_NEAR_LIMIT
from app.modules.entitlements.catalogue import FEATURES, FREE_PLAN_CODE, LIMIT_TO_USAGE_METRIC, F
from app.modules.entitlements.models import (
    Feature,
    Plan,
    PlanFeature,
    TenantFeatureOverride,
    TenantSubscription,
    TenantUsageCounter,
)

CURRENT_STATUSES = ("active", "trialing", "past_due")
CACHE_TTL_S = 300
LOCAL_TTL_S = 15
_FEATURE_DESCRIPTIONS = {f.key: f.description for f in FEATURES}


@dataclass(frozen=True)
class EffectiveEntitlements:
    values: dict[str, Any]
    plan_code: str
    plan_name: str
    subscription_status: str
    period_end: str | None = None
    overrides: list[str] = field(default_factory=list)

    def has(self, key: str) -> bool:
        return bool(self.values.get(key))

    def limit(self, key: str) -> int | None:
        value = self.values.get(key)
        return None if value is None else int(value)

    def require(self, key: str) -> None:
        if not self.has(key):
            raise FeatureNotInPlan(
                f"{_FEATURE_DESCRIPTIONS.get(key, key)} isn't included in the {self.plan_name} plan.",
                feature=key,
                plan=self.plan_name,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": self.values,
            "plan_code": self.plan_code,
            "plan_name": self.plan_name,
            "subscription_status": self.subscription_status,
            "period_end": self.period_end,
            "overrides": self.overrides,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EffectiveEntitlements:
        return cls(**data)


def _cache_key(tenant_id: uuid.UUID) -> str:
    return f"t:{tenant_id}:ent"


async def _resolve(uow: UnitOfWork, tenant_id: uuid.UUID, now: datetime) -> EffectiveEntitlements:
    session = uow.session
    defaults = {f.key: f.default_value for f in (await session.scalars(select(Feature))).all()}
    sub = (
        await session.execute(
            select(TenantSubscription, Plan)
            .join(Plan, Plan.id == TenantSubscription.plan_id)
            .where(TenantSubscription.status.in_(CURRENT_STATUSES))
        )
    ).one_or_none()
    plan: Plan | None
    if sub is not None:
        subscription, plan = sub
        status = subscription.status
        period_end = subscription.period_end
        if period_end is not None and period_end < now and status != "past_due":
            # Lapsed but not yet flipped by the maintenance job: treat as expired.
            plan = None
            status = "expired"
    else:
        plan, status, period_end = None, "expired", None
    if plan is None:
        plan = (await session.scalars(select(Plan).where(Plan.code == FREE_PLAN_CODE))).one()
    plan_values = {
        pf.feature_key: pf.value
        for pf in (await session.scalars(select(PlanFeature).where(PlanFeature.plan_id == plan.id))).all()
    }
    values = dict(defaults)
    values.update(plan_values)
    overrides: list[str] = []
    for ov in (await session.scalars(select(TenantFeatureOverride))).all():
        if ov.expires_at is None or ov.expires_at > now:
            values[ov.feature_key] = ov.value
            overrides.append(ov.feature_key)
    return EffectiveEntitlements(
        values=values,
        plan_code=plan.code,
        plan_name=plan.name,
        subscription_status=status,
        period_end=period_end.isoformat() if period_end else None,
        overrides=sorted(overrides),
    )


class EntitlementService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    async def effective(self, uow: UnitOfWork, *, fresh: bool = False) -> EffectiveEntitlements:
        tenant_id = uow.require_tenant()
        key = _cache_key(tenant_id)
        if not fresh:
            cached = await self.infra.cache.get(key, local_ttl_s=LOCAL_TTL_S)
            if cached is not None:
                return EffectiveEntitlements.from_dict(cached)
        ent = await _resolve(uow, tenant_id, utcnow())
        await self.infra.cache.set(key, ent.to_dict(), CACHE_TTL_S, local_ttl_s=LOCAL_TTL_S)
        return ent

    async def require(self, uow: UnitOfWork, feature: str) -> None:
        (await self.effective(uow)).require(feature)

    async def invalidate(self, tenant_id: uuid.UUID) -> None:
        await self.infra.cache.delete(_cache_key(tenant_id))

    # ---- limits & usage -------------------------------------------------------------------------
    @staticmethod
    async def _locked_counter(uow: UnitOfWork, metric: str) -> int:
        tenant_id = uow.require_tenant()
        await uow.session.execute(
            insert(TenantUsageCounter)
            .values(tenant_id=tenant_id, metric=metric, value=0)
            .on_conflict_do_nothing(index_elements=["tenant_id", "metric"])
        )
        value = (
            await uow.session.execute(
                select(TenantUsageCounter.value).where(TenantUsageCounter.metric == metric).with_for_update()
            )
        ).scalar_one()
        return int(value)

    async def consume(self, uow: UnitOfWork, limit_key: str, delta: int = 1, *, enforce: bool = True) -> None:
        """Check ``limit_key`` and add ``delta`` to its usage counter, atomically with the caller's
        transaction. Raises ``LimitExceeded`` (HTTP 402) with current/max when over the limit.

        ``enforce=False`` only records the usage: for work that other limits already bound and that must
        not fail on the day it matters (marksheets of a publication the plan allowed; docs/12 §4)."""
        if delta <= 0:
            return
        metric = LIMIT_TO_USAGE_METRIC[limit_key]
        current = await self._locked_counter(uow, metric)
        # Limit values come from the DB inside this transaction — never from cache — for correctness.
        limit = (await _resolve(uow, uow.require_tenant(), utcnow())).limit(limit_key)
        scale = 1024 * 1024 if limit_key == F.MAX_STORAGE_MB else 1
        if enforce and limit is not None and current + delta > limit * scale:
            raise LimitExceeded(
                _limit_message(limit_key, current // scale, delta // scale or delta, limit),
                limit=limit_key,
                current=current // scale,
                requested=delta // scale if scale > 1 else delta,
                max=limit,
            )
        await uow.session.execute(
            text(
                "UPDATE tenant_usage_counters SET value = value + :d, updated_at = now() "
                "WHERE tenant_id = :t AND metric = :m"
            ),
            {"d": delta, "t": uow.require_tenant(), "m": metric},
        )

    async def release(self, uow: UnitOfWork, limit_key: str, delta: int = 1) -> None:
        if delta <= 0:
            return
        metric = LIMIT_TO_USAGE_METRIC[limit_key]
        await self._locked_counter(uow, metric)
        await uow.session.execute(
            text(
                "UPDATE tenant_usage_counters SET value = GREATEST(0, value - :d), updated_at = now() "
                "WHERE tenant_id = :t AND metric = :m"
            ),
            {"d": delta, "t": uow.require_tenant(), "m": metric},
        )

    async def usage(self, uow: UnitOfWork) -> dict[str, int]:
        rows = (await uow.session.execute(select(TenantUsageCounter.metric, TenantUsageCounter.value))).all()
        return {r.metric: int(r.value) for r in rows}

    async def set_usage(self, uow: UnitOfWork, metric: str, value: int) -> None:
        """Reconciliation: overwrite a counter with the authoritative count."""
        await self._locked_counter(uow, metric)
        await uow.session.execute(
            text(
                "UPDATE tenant_usage_counters SET value = :v, updated_at = now() WHERE tenant_id = :t AND metric = :m"
            ),
            {"v": value, "t": uow.require_tenant(), "m": metric},
        )


def _limit_message(key: str, current: int, requested: int, limit: int) -> str:
    noun = {
        F.MAX_STUDENTS: "active students",
        F.MAX_STAFF: "staff accounts",
        F.MAX_ADMINS: "administrator seats",
        F.MAX_STORAGE_MB: "MB of storage",
        F.MAX_PUBLISHED_EXAMS_PER_YEAR: "exam publications this academic year",
    }.get(key, key)
    remaining = max(0, limit - current)
    return (
        f"Your plan includes {limit:,} {noun}. You're using {current:,}, so {remaining:,} more can be added "
        f"but this action needs {requested:,}. Upgrade your plan or free up capacity to continue."
    )


@maintenance_task
async def report_tenants_near_limits(infra: Infra) -> dict[str, int]:
    """How many institutions use at least 90% of each plan limit, for ScoreCodeTenantsNearLimit: a
    chance to talk to them before a limit stops an import or a publication."""
    near: dict[str, int] = dict.fromkeys(LIMIT_TO_USAGE_METRIC, 0)
    async with infra.db.uow() as uow:
        tenant_ids = (await uow.session.scalars(text("SELECT * FROM ops_tenant_ids()"))).all()
    service = EntitlementService(infra)
    for tenant_id in tenant_ids:
        async with infra.db.uow(tenant_id) as uow:
            ent = await service.effective(uow)
            used = await service.usage(uow)
        for key, metric in LIMIT_TO_USAGE_METRIC.items():
            limit = ent.limit(key)
            if not limit:
                continue
            scale = 1024 * 1024 if key == F.MAX_STORAGE_MB else 1
            if used.get(metric, 0) >= 0.9 * limit * scale:
                near[key] += 1
    for key, n in near.items():
        TENANTS_NEAR_LIMIT.labels(key).set(n)
    return {"tenants_near_limit": sum(near.values())}
