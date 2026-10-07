"""Platform console use cases (docs/03 W17, P4.7, P13.5). Runs on the BYPASSRLS platform role — the only
module allowed to — and records every action in ``platform_audit_logs`` (and, when it affects a tenant,
in that tenant's own audit log so the institution can see it)."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text, update

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import InvalidState, NotFound, ValidationFailed
from app.core.http import Principal
from app.core.metrics import CACHE_EVENTS, HTTP_LATENCY, HTTP_REQUESTS
from app.modules.audit.models import AuditLog
from app.modules.audit.service import Actor, record_platform
from app.modules.entitlements.catalogue import FEATURES
from app.modules.entitlements.models import (
    Feature,
    Plan,
    PlanFeature,
    TenantFeatureOverride,
    TenantSubscription,
    TenantTrial,
    TenantUsageCounter,
)
from app.modules.entitlements.trial import TrialService
from app.modules.identity.models import Session, User
from app.modules.tenancy.models import Tenant, TenantSettings

FEATURE_KINDS = {f.key: f.kind for f in FEATURES}


def _tenant_audit(uow: UnitOfWork, tenant_id: uuid.UUID, actor: Actor, action: str, **fields: Any) -> None:
    uow.session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_type="platform_user",
            actor_id=actor.id,
            actor_label=f"ScoreCode staff ({actor.label})",
            action=action,
            request_id=uow.meta.get("request_id"),
            ip=uow.meta.get("ip"),
            **fields,
        )
    )


class PlatformService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    # ---- tenants --------------------------------------------------------------------------------
    async def list_tenants(
        self, uow: UnitOfWork, *, q: str | None, status: str | None, plan: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        current_sub = (
            select(
                TenantSubscription.tenant_id,
                Plan.code.label("plan_code"),
                Plan.name.label("plan_name"),
                TenantSubscription.status.label("sub_status"),
            )
            .join(Plan, Plan.id == TenantSubscription.plan_id)
            .where(TenantSubscription.status.in_(("active", "trialing", "past_due")))
            .subquery()
        )
        students = (
            select(TenantUsageCounter.tenant_id, TenantUsageCounter.value.label("active_students"))
            .where(TenantUsageCounter.metric == "active_students")
            .subquery()
        )
        staff = (
            select(TenantUsageCounter.tenant_id, TenantUsageCounter.value.label("staff_users"))
            .where(TenantUsageCounter.metric == "staff_users")
            .subquery()
        )
        stmt = (
            select(
                Tenant,
                current_sub.c.plan_code,
                current_sub.c.plan_name,
                current_sub.c.sub_status,
                func.coalesce(students.c.active_students, 0).label("active_students"),
                func.coalesce(staff.c.staff_users, 0).label("staff_users"),
            )
            .outerjoin(current_sub, current_sub.c.tenant_id == Tenant.id)
            .outerjoin(students, students.c.tenant_id == Tenant.id)
            .outerjoin(staff, staff.c.tenant_id == Tenant.id)
        )
        if q:
            like = f"%{q.strip().lower()}%"
            stmt = stmt.where(func.lower(Tenant.name).like(like) | func.lower(Tenant.slug).like(like))
        if status:
            stmt = stmt.where(Tenant.status == status)
        if plan:
            stmt = stmt.where(current_sub.c.plan_code == plan)
        total = (await uow.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await uow.session.execute(stmt.order_by(Tenant.created_at.desc()).limit(limit).offset(offset))
        ).all()
        items = [
            {
                "id": t.id,
                "slug": t.slug,
                "name": t.name,
                "type": t.type,
                "status": t.status,
                "created_at": t.created_at,
                "plan_code": plan_code,
                "plan_name": plan_name or "—",
                "subscription_status": sub_status or "expired",
                "active_students": int(active_students),
                "staff_users": int(staff_users),
                "host": f"{t.slug}.{self.infra.settings.base_domain}",
            }
            for t, plan_code, plan_name, sub_status, active_students, staff_users in rows
        ]
        return items, int(total)

    async def _tenant(self, uow: UnitOfWork, tenant_id: uuid.UUID, *, lock: bool = False) -> Tenant:
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        if lock:
            stmt = stmt.with_for_update()
        tenant = (await uow.session.scalars(stmt)).one_or_none()
        if tenant is None:
            raise NotFound("Tenant not found")
        return tenant

    async def tenant_detail(self, uow: UnitOfWork, tenant_id: uuid.UUID) -> dict[str, Any]:
        t = await self._tenant(uow, tenant_id)
        settings = (
            await uow.session.scalars(select(TenantSettings).where(TenantSettings.tenant_id == t.id))
        ).one_or_none()
        subs = (
            await uow.session.execute(
                select(TenantSubscription, Plan)
                .join(Plan, Plan.id == TenantSubscription.plan_id)
                .where(TenantSubscription.tenant_id == t.id)
                .order_by(TenantSubscription.created_at.desc())
            )
        ).all()
        overrides = (
            await uow.session.scalars(
                select(TenantFeatureOverride).where(TenantFeatureOverride.tenant_id == t.id)
            )
        ).all()
        usage = {
            r.metric: int(r.value)
            for r in (
                await uow.session.execute(
                    select(TenantUsageCounter.metric, TenantUsageCounter.value).where(
                        TenantUsageCounter.tenant_id == t.id
                    )
                )
            ).all()
        }
        user_counts = dict(
            (
                await uow.session.execute(
                    select(User.kind, func.count()).where(User.tenant_id == t.id).group_by(User.kind)
                )
            ).all()
        )
        last_activity = (
            await uow.session.execute(select(func.max(Session.last_seen_at)).where(Session.tenant_id == t.id))
        ).scalar_one()
        current = next((s for s, _ in subs if s.status in ("active", "trialing", "past_due")), None)
        trial = (
            await uow.session.scalars(select(TenantTrial).where(TenantTrial.tenant_id == t.id))
        ).one_or_none()
        return {
            "id": t.id,
            "slug": t.slug,
            "name": t.name,
            "type": t.type,
            "status": t.status,
            "status_reason": t.status_reason,
            "timezone": t.timezone,
            "created_at": t.created_at,
            "host": f"{t.slug}.{self.infra.settings.base_domain}",
            "official_name": settings.official_name if settings else t.name,
            "contact_email": settings.contact_email if settings else None,
            "current_plan": next((p.code for s, p in subs if s is current), None),
            "subscriptions": [
                {
                    "id": s.id,
                    "plan_code": p.code,
                    "plan_name": p.name,
                    "status": s.status,
                    "period_start": s.period_start,
                    "period_end": s.period_end,
                    "billing_ref": s.billing_ref,
                    "created_at": s.created_at,
                }
                for s, p in subs
            ],
            "overrides": [
                {
                    "feature_key": o.feature_key,
                    "value": o.value,
                    "reason": o.reason,
                    "expires_at": o.expires_at,
                }
                for o in overrides
            ],
            "usage": usage,
            "trial": (
                {
                    "status": trial.status,
                    "started_at": trial.started_at,
                    "ends_at": trial.ends_at,
                    "ended_at": trial.ended_at,
                    "end_reason": trial.end_reason,
                    "risk_score": trial.risk_score,
                    "flags": trial.flags,
                    "granted": trial.granted_by_platform_user is not None,
                }
                if trial
                else None
            ),
            "users": {
                "staff": int(user_counts.get("staff", 0)),
                "students": int(user_counts.get("student", 0)),
            },
            "last_activity_at": last_activity,
        }

    async def _invalidate_tenant(self, uow: UnitOfWork, tenant: Tenant) -> None:
        await uow.session.execute(
            update(Tenant).where(Tenant.id == tenant.id).values(config_version=Tenant.config_version + 1)
        )
        host_key = f"tenant:host:{tenant.slug}.{self.infra.settings.base_domain}"
        keys = [host_key, f"t:{tenant.id}:ent", f"t:{tenant.id}:config"]
        uow.after_commit(lambda: self.infra.cache.delete(*keys))

    async def set_status(
        self, uow: UnitOfWork, principal: Principal, tenant_id: uuid.UUID, *, suspend: bool, reason: str
    ) -> None:
        if not reason.strip():
            raise ValidationFailed("A reason is required.", field="reason")
        t = await self._tenant(uow, tenant_id, lock=True)
        target = "suspended" if suspend else "active"
        if t.status == target:
            return
        if t.status not in ("active", "suspended"):
            raise InvalidState(f"Tenant is {t.status}.")
        before = t.status
        t.status = target
        t.status_reason = reason.strip() if suspend else None
        actor = Actor.from_principal(principal)
        if suspend:
            hashes = (
                await uow.session.scalars(
                    select(Session.id).where(Session.tenant_id == t.id, Session.revoked_at.is_(None))
                )
            ).all()
            await uow.session.execute(
                update(Session)
                .where(Session.tenant_id == t.id, Session.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
            keys = ["sess:" + h.hex() for h in hashes]
            if keys:
                uow.after_commit(lambda: self.infra.cache.delete(*keys))
        await self._invalidate_tenant(uow, t)
        await record_platform(
            uow,
            actor,
            "tenant.suspended" if suspend else "tenant.reactivated",
            target_tenant_id=t.id,
            entity_type="tenant",
            entity_id=t.id,
            before={"status": before},
            after={"status": target},
            reason=reason,
        )
        _tenant_audit(
            uow,
            t.id,
            actor,
            "tenant.suspended" if suspend else "tenant.reactivated",
            entity_type="tenant",
            entity_id=str(t.id),
            before={"status": before},
            after={"status": target},
            reason=reason,
        )

    async def change_plan(
        self,
        uow: UnitOfWork,
        principal: Principal,
        tenant_id: uuid.UUID,
        *,
        plan_code: str,
        status: str,
        period_end: datetime | None,
        billing_ref: str | None,
        reason: str,
    ) -> None:
        t = await self._tenant(uow, tenant_id, lock=True)
        plan = (
            await uow.session.scalars(select(Plan).where(Plan.code == plan_code, Plan.active))
        ).one_or_none()
        if plan is None:
            raise ValidationFailed("Unknown plan.", field="plan_code")
        current = (
            await uow.session.execute(
                select(TenantSubscription, Plan)
                .join(Plan, Plan.id == TenantSubscription.plan_id)
                .where(
                    TenantSubscription.tenant_id == t.id,
                    TenantSubscription.status.in_(("active", "trialing", "past_due")),
                )
                .with_for_update(of=TenantSubscription)
            )
        ).one_or_none()
        before = None
        if current is not None:
            sub, old_plan = current
            before = {"plan": old_plan.code, "status": sub.status}
            sub.status = "cancelled"
            sub.period_end = sub.period_end or utcnow()
            await uow.flush()
        uow.session.add(
            TenantSubscription(
                tenant_id=t.id,
                plan_id=plan.id,
                status=status,
                period_end=period_end,
                billing_ref=billing_ref,
                changed_by_platform_user=principal.user_id,
            )
        )
        await TrialService.close_for_plan_change(uow, t.id, new_plan_code=plan.code)
        await self._invalidate_tenant(uow, t)
        actor = Actor.from_principal(principal)
        after = {"plan": plan.code, "status": status, "period_end": period_end}
        await record_platform(
            uow,
            actor,
            "tenant.plan_changed",
            target_tenant_id=t.id,
            entity_type="subscription",
            entity_id=t.id,
            before=before,
            after=after,
            reason=reason,
        )
        _tenant_audit(
            uow,
            t.id,
            actor,
            "tenant.plan_changed",
            entity_type="subscription",
            entity_id=str(t.id),
            before=before,
            after={"plan": plan.code, "status": status},
            reason=reason,
        )

    async def set_override(
        self,
        uow: UnitOfWork,
        principal: Principal,
        tenant_id: uuid.UUID,
        *,
        feature_key: str,
        value: Any,
        expires_at: datetime | None,
        reason: str,
    ) -> None:
        kind = FEATURE_KINDS.get(feature_key)
        if kind is None:
            raise ValidationFailed("Unknown feature.", field="feature_key")
        if kind == "boolean" and not isinstance(value, bool):
            raise ValidationFailed("This feature takes true or false.", field="value")
        if (
            kind == "limit"
            and value is not None
            and (not isinstance(value, int) or isinstance(value, bool) or value < 0)
        ):
            raise ValidationFailed("Limits are whole numbers (or empty for unlimited).", field="value")
        if kind == "enum_set" and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            raise ValidationFailed("Provide a list of values.", field="value")
        t = await self._tenant(uow, tenant_id)
        existing = (
            await uow.session.scalars(
                select(TenantFeatureOverride).where(
                    TenantFeatureOverride.tenant_id == t.id, TenantFeatureOverride.feature_key == feature_key
                )
            )
        ).one_or_none()
        before = {"value": existing.value, "expires_at": existing.expires_at} if existing else None
        if existing is None:
            uow.session.add(
                TenantFeatureOverride(
                    tenant_id=t.id,
                    feature_key=feature_key,
                    value=value,
                    reason=reason,
                    expires_at=expires_at,
                    created_by_platform_user=principal.user_id,
                )
            )
        else:
            existing.value = value
            existing.expires_at = expires_at
            existing.reason = reason
            existing.created_by_platform_user = principal.user_id
        await self._invalidate_tenant(uow, t)
        actor = Actor.from_principal(principal)
        await record_platform(
            uow,
            actor,
            "tenant.override_set",
            target_tenant_id=t.id,
            entity_type="override",
            entity_id=feature_key,
            before=before,
            after={"value": value, "expires_at": expires_at},
            reason=reason,
        )
        _tenant_audit(
            uow,
            t.id,
            actor,
            "tenant.override_set",
            entity_type="override",
            entity_id=feature_key,
            after={"value": value, "expires_at": expires_at.isoformat() if expires_at else None},
            reason=reason,
        )

    async def delete_override(
        self, uow: UnitOfWork, principal: Principal, tenant_id: uuid.UUID, feature_key: str, reason: str
    ) -> None:
        t = await self._tenant(uow, tenant_id)
        existing = (
            await uow.session.scalars(
                select(TenantFeatureOverride).where(
                    TenantFeatureOverride.tenant_id == t.id, TenantFeatureOverride.feature_key == feature_key
                )
            )
        ).one_or_none()
        if existing is None:
            raise NotFound("Override not found")
        await uow.session.delete(existing)
        await self._invalidate_tenant(uow, t)
        await record_platform(
            uow,
            Actor.from_principal(principal),
            "tenant.override_removed",
            target_tenant_id=t.id,
            entity_type="override",
            entity_id=feature_key,
            before={"value": existing.value},
            reason=reason,
        )

    # ---- catalogue ------------------------------------------------------------------------------
    async def plans(self, uow: UnitOfWork) -> dict[str, Any]:
        plans = (await uow.session.scalars(select(Plan).order_by(Plan.sort_order))).all()
        values = (await uow.session.scalars(select(PlanFeature))).all()
        features = (await uow.session.scalars(select(Feature))).all()
        by_plan: dict[uuid.UUID, dict[str, Any]] = {}
        for v in values:
            by_plan.setdefault(v.plan_id, {})[v.feature_key] = v.value
        return {
            "plans": [
                {
                    "code": p.code,
                    "name": p.name,
                    "description": p.description,
                    "price_paise_yearly": p.price_paise_yearly,
                    "is_public": p.is_public,
                    "active": p.active,
                    "values": by_plan.get(p.id, {}),
                }
                for p in plans
            ],
            "features": [{"key": f.key, "kind": f.kind, "description": f.description} for f in features],
        }

    # ---- observability --------------------------------------------------------------------------
    async def overview(self, uow: UnitOfWork) -> dict[str, Any]:
        s = uow.session
        by_status = dict((await s.execute(select(Tenant.status, func.count()).group_by(Tenant.status))).all())
        by_plan = dict(
            (
                await s.execute(
                    select(Plan.code, func.count())
                    .join(TenantSubscription, TenantSubscription.plan_id == Plan.id)
                    .where(TenantSubscription.status.in_(("active", "trialing", "past_due")))
                    .group_by(Plan.code)
                )
            ).all()
        )
        totals = (
            await s.execute(
                text(
                    "SELECT coalesce(sum(value) FILTER (WHERE metric = 'active_students'), 0) AS students, "
                    "coalesce(sum(value) FILTER (WHERE metric = 'staff_users'), 0) AS staff FROM tenant_usage_counters"
                )
            )
        ).one()
        queues = [
            {"queue": r.queue, "status": r.status, "count": int(r.n), "oldest_seconds": float(r.oldest or 0)}
            for r in (
                await s.execute(
                    text(
                        "SELECT queue, status, count(*) AS n, "
                        "extract(epoch FROM now() - min(run_at) FILTER (WHERE status = 'queued')) AS oldest "
                        "FROM jobs WHERE status IN ('queued','running','dead') GROUP BY queue, status ORDER BY queue, status"
                    )
                )
            ).all()
        ]
        signups_7d = (
            await s.execute(text("SELECT count(*) FROM tenants WHERE created_at > now() - interval '7 days'"))
        ).scalar_one()
        extra = await self._domain_counters(uow)
        return {
            "tenants": {"by_status": by_status, "by_plan": by_plan, "new_last_7_days": int(signups_7d)},
            "users": {"active_students": int(totals.students), "staff": int(totals.staff)},
            "queues": queues,
            **extra,
            "process_metrics": process_metrics(),
        }

    async def _domain_counters(self, uow: UnitOfWork) -> dict[str, Any]:
        """Counters from later modules (publications) when their tables exist."""
        exists = (
            await uow.session.execute(text("SELECT to_regclass('public.publications') IS NOT NULL"))
        ).scalar_one()
        if not exists:
            return {"publications": {"last_7_days": 0, "live": 0}}
        row = (
            await uow.session.execute(
                text(
                    "SELECT count(*) FILTER (WHERE published_at > now() - interval '7 days') AS week, "
                    "count(*) FILTER (WHERE status = 'published') AS live FROM publications"
                )
            )
        ).one()
        return {"publications": {"last_7_days": int(row.week), "live": int(row.live)}}

    async def deep_health(self) -> dict[str, Any]:
        async def timed(name: str, coro: Any) -> dict[str, Any]:
            started = time.perf_counter()
            try:
                ok = await asyncio.wait_for(coro, timeout=3)
                status = "up" if ok is not False else "down"
            except Exception as exc:
                return {
                    "name": name,
                    "status": "down",
                    "error": type(exc).__name__,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            return {
                "name": name,
                "status": status,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }

        async def db_ping() -> bool:
            async with self.infra.db.uow() as uow:
                await uow.session.execute(text("SELECT 1"))
            return True

        async def redis_ping() -> bool:
            if self.infra.cache.redis is None:
                return False
            return bool(await self.infra.cache.redis.ping())

        async def smtp_ping() -> bool:
            _reader, writer = await asyncio.open_connection(
                self.infra.settings.smtp_host, self.infra.settings.smtp_port
            )
            writer.close()
            await writer.wait_closed()
            return True

        checks = await asyncio.gather(
            timed("database", db_ping()),
            timed("redis", redis_ping()),
            timed("object_storage", self.infra.storage.ping()),
            timed("email", smtp_ping()),
        )
        redis_check = next(c for c in checks if c["name"] == "redis")
        if self.infra.cache.redis is None:
            redis_check["status"] = "not_configured"
        redis_check["circuit_breaker"] = self.infra.cache.breaker.state
        return {"checks": list(checks), "checked_at": utcnow().isoformat()}


def process_metrics() -> dict[str, Any]:
    """Aggregates from this API process's Prometheus registry (since process start).

    Labelled as such in the console: with several API processes, the authoritative view is Prometheus.
    """
    cache = {"hits": 0.0, "misses": 0.0}
    for metric in CACHE_EVENTS.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and sample.labels.get("cache") == "redis":
                if sample.labels.get("event") == "hit":
                    cache["hits"] += sample.value
                elif sample.labels.get("event") == "miss":
                    cache["misses"] += sample.value
    lookups = cache["hits"] + cache["misses"]
    requests = {"total": 0.0, "errors_5xx": 0.0}
    for metric in HTTP_REQUESTS.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total"):
                requests["total"] += sample.value
                if sample.labels.get("status", "").startswith("5"):
                    requests["errors_5xx"] += sample.value
    p95 = {}
    for metric in HTTP_LATENCY.collect():
        buckets: dict[str, list[tuple[float, float]]] = {}
        counts: dict[str, float] = {}
        for sample in metric.samples:
            klass = sample.labels.get("route_class", "")
            if sample.name.endswith("_bucket"):
                buckets.setdefault(klass, []).append((float(sample.labels["le"]), sample.value))
            elif sample.name.endswith("_count"):
                counts[klass] = sample.value
        for klass, bs in buckets.items():
            total = counts.get(klass, 0)
            if total < 20:
                continue
            target = total * 0.95
            for le, cumulative in sorted(bs):
                if cumulative >= target:
                    p95[klass] = None if le == float("inf") else le * 1000
                    break
    return {
        "scope": "this API process since start",
        "redis_cache_hit_rate": round(cache["hits"] / lookups, 4) if lookups else None,
        "requests_total": int(requests["total"]),
        "errors_5xx": int(requests["errors_5xx"]),
        "p95_upper_bound_ms_by_route_class": p95,
    }
