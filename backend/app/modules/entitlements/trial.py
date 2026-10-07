"""The 30-day Pro trial: once per institution, ever (docs/12 §6).

Starting a trial runs in one platform-role transaction, because the check has to look *across* tenants:

1. the tenant is active, has never had a trial (``tenant_trials`` is unique per tenant) and never paid;
2. the owner's identity signals are hashed (``trial_signals``). If any *hard* signal — the owner's
   normalised email, its institutional domain, this browser's device id, the tenant — was used for a trial
   before, the trial is refused. Postgres advisory locks on those digests serialise two concurrent attempts,
   and a partial unique index on ``trial_claims`` is the last line of defence;
3. *soft* signals (an unverified phone, the institution's name, a busy network) add risk. Two or more and
   the trial waits for a person (the owner is asked to contact support), so typing someone else's phone
   number can never lock them out on its own;
4. the free subscription is replaced by a ``trialing`` one that ends after 30 days. Jobs remind the owner
   7 days and 1 day before, and end the trial on time. If the end job never ran, entitlement resolution
   already treats a past ``period_end`` as expired.

Refusals are audited for the platform team (kinds of signal only, never values).
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import Conflict, PermissionDenied
from app.core.ids import uuid7
from app.core.jobs import JobContext, enqueue, registry
from app.modules.audit.models import AuditLog
from app.modules.audit.service import Actor, record_platform
from app.modules.entitlements.catalogue import FREE_PLAN_CODE, TRIAL_DAYS, TRIAL_PLAN_CODE
from app.modules.entitlements.models import Plan, TenantSubscription, TenantTrial, TrialClaim
from app.modules.entitlements.service import EntitlementService
from app.modules.entitlements.trial_signals import HARD_KINDS, Signal, collect
from app.modules.identity.models import SignupRequest, User, UserRole
from app.modules.notifications.emails import queue_email
from app.modules.tenancy.models import Tenant, TenantSettings

CURRENT = ("active", "trialing", "past_due")
SUBNET_WINDOW = timedelta(days=90)
REVIEW_AT = 2  # soft-risk score at which a person has to look first
REMINDERS = (7, 1)  # days before the end


@dataclass(frozen=True)
class TrialView:
    state: str  # available | active | ended | converted | revoked | ineligible
    days: int
    plan_name: str
    started_at: datetime | None = None
    ends_at: datetime | None = None
    days_left: int | None = None
    reason: str | None = None


class TrialRefused(Conflict):
    code = "trial-unavailable"
    title = "Trial not available"


def _days_left(ends_at: datetime, now: datetime) -> int:
    return max(0, math.ceil((ends_at - now).total_seconds() / 86_400))


async def _plan(uow: UnitOfWork, code: str) -> Plan:
    return (await uow.session.scalars(select(Plan).where(Plan.code == code))).one()


class TrialService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra
        self.key = infra.settings.abuse_signal_key.get_secret_value().encode()

    # ---- read (tenant transaction) --------------------------------------------------------------
    async def view(self, uow: UnitOfWork) -> TrialView:
        plan = await _plan(uow, TRIAL_PLAN_CODE)
        now = utcnow()
        trial = (await uow.session.scalars(select(TenantTrial))).one_or_none()
        if trial is not None:
            state = trial.status
            if state == "active" and trial.ends_at <= now:
                state = "ended"  # the end job hasn't run yet; entitlements already treat it as over
            return TrialView(
                state=state,
                days=TRIAL_DAYS,
                plan_name=plan.name,
                started_at=trial.started_at,
                ends_at=trial.ends_at,
                days_left=_days_left(trial.ends_at, now) if state == "active" else None,
            )
        if await self._paid_before(uow):
            return TrialView(state="ineligible", days=TRIAL_DAYS, plan_name=plan.name, reason="paid")
        return TrialView(state="available", days=TRIAL_DAYS, plan_name=plan.name)

    @staticmethod
    async def _paid_before(uow: UnitOfWork, tenant_id: uuid.UUID | None = None) -> bool:
        stmt = (
            select(func.count())
            .select_from(TenantSubscription)
            .join(Plan, Plan.id == TenantSubscription.plan_id)
            .where(Plan.code.not_in((FREE_PLAN_CODE, TRIAL_PLAN_CODE)))
        )
        if tenant_id is not None:
            stmt = stmt.where(TenantSubscription.tenant_id == tenant_id)
        return bool(await uow.session.scalar(stmt))

    # ---- start (platform transaction) -----------------------------------------------------------
    async def start(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        user_label: str,
        device_id: str | None,
        ip: str | None,
    ) -> TenantTrial:
        refusal: tuple[str, str, list[str]] | None = (
            None  # (reason, message, signal kinds) — audited, then raised
        )
        trial: TenantTrial | None = None
        async with self.infra.db.platform_uow(ip=ip) as uow:
            s = uow.session
            tenant = (await s.scalars(select(Tenant).where(Tenant.id == tenant_id).with_for_update())).one()
            if tenant.status != "active":
                raise PermissionDenied("This institution isn't active.")
            owner = (
                await s.scalars(
                    select(User)
                    .join(UserRole, UserRole.user_id == User.id)
                    .where(User.tenant_id == tenant.id, UserRole.role == "institution_owner")
                )
            ).first()
            if owner is None or owner.id != user_id:
                raise PermissionDenied("Only the institution's owner can start the trial.")
            if (await s.scalars(select(TenantTrial.id).where(TenantTrial.tenant_id == tenant.id))).first():
                raise TrialRefused("Your institution has already used its free trial.", reason="used")
            if await self._paid_before(uow, tenant.id):
                raise TrialRefused(
                    "Trials are for institutions that haven't had a paid plan.", reason="ineligible"
                )

            phones = [
                *(
                    await s.scalars(select(SignupRequest.phone).where(SignupRequest.tenant_id == tenant.id))
                ).all(),
                (
                    await s.scalars(
                        select(TenantSettings.contact_phone).where(TenantSettings.tenant_id == tenant.id)
                    )
                ).one_or_none(),
            ]
            signals = collect(
                self.key,
                tenant_id=str(tenant.id),
                owner_email=owner.email or owner.login_id,
                device_id=device_id,
                phones=phones,
                institution_name=tenant.name,
                ip=ip,
            )
            hard = sorted((x for x in signals if x.kind in HARD_KINDS), key=lambda x: (x.kind, x.digest))
            for sig in hard:  # two attempts with the same identity queue up here instead of racing
                await s.execute(select(func.pg_advisory_xact_lock(int(sig.digest[:15], 16))))
            used = (
                await s.scalars(
                    select(TrialClaim.kind).where(
                        tuple_(TrialClaim.kind, TrialClaim.digest).in_([(x.kind, x.digest) for x in hard])
                    )
                )
            ).all()
            if used:
                refusal = (
                    "used",
                    "This institution, email address or device has already used a free trial. If that's a "
                    "mistake, write to support@scorecode.in and we'll sort it out.",
                    sorted(set(used)),
                )
            else:
                score, flags = await self._soft_risk(uow, [x for x in signals if x.kind not in HARD_KINDS])
                if score >= REVIEW_AT:
                    refusal = (
                        "review",
                        "We couldn't start the trial automatically. Write to support@scorecode.in and we'll "
                        "start it for you within a working day.",
                        flags,
                    )
                else:
                    trial = await self._begin(uow, tenant, owner, user_label, signals, score, flags)
            if refusal is not None:
                await record_platform(
                    uow,
                    Actor.system(f"tenant owner {user_label}"),
                    "trial.refused",
                    target_tenant_id=tenant.id,
                    entity_type="tenant",
                    entity_id=tenant.id,
                    after={"reason": refusal[0], "signals": refusal[2]},
                )
        if refusal is not None:
            raise TrialRefused(refusal[1], reason=refusal[0])
        assert trial is not None
        await EntitlementService(self.infra).invalidate(tenant_id)
        return trial

    @staticmethod
    async def _soft_risk(uow: UnitOfWork, soft: list[Signal]) -> tuple[int, list[str]]:
        score, flags = 0, []
        for sig in soft:
            if sig.kind == "subnet":
                recent = await uow.session.scalar(
                    select(func.count())
                    .select_from(TrialClaim)
                    .where(
                        TrialClaim.kind == "subnet",
                        TrialClaim.digest == sig.digest,
                        TrialClaim.created_at > utcnow() - SUBNET_WINDOW,
                    )
                )
                if recent and recent >= 2:
                    score += 2 if recent >= 4 else 1
                    flags.append("subnet")
            elif (
                await uow.session.scalars(
                    select(TrialClaim.id).where(TrialClaim.kind == sig.kind, TrialClaim.digest == sig.digest)
                )
            ).first():
                score += 1
                flags.append(sig.kind)
        return score, sorted(set(flags))

    async def _begin(
        self,
        uow: UnitOfWork,
        tenant: Tenant,
        owner: User,
        user_label: str,
        signals: list[Signal],
        score: int,
        flags: list[str],
        *,
        granted_by: uuid.UUID | None = None,
    ) -> TenantTrial:
        s = uow.session
        now = utcnow()
        plan = await _plan(uow, TRIAL_PLAN_CODE)
        trial = TenantTrial(
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="active",
            started_at=now,
            ends_at=now + timedelta(days=TRIAL_DAYS),
            started_by=None if granted_by else owner.id,
            granted_by_platform_user=granted_by,
            risk_score=score,
            flags=flags,
        )
        s.add(trial)
        await s.flush()
        if granted_by is None:
            s.add_all(TrialClaim(kind=x.kind, digest=x.digest, trial_id=trial.id) for x in signals)
            try:
                await s.flush()
            except IntegrityError as exc:  # a concurrent trial claimed the same identity first
                raise TrialRefused("This identity has just been used for a trial.", reason="used") from exc
        else:  # staff decided: record what isn't recorded yet, so this identity can't start another one
            for x in signals:
                await s.execute(
                    pg_insert(TrialClaim)
                    .values(id=uuid7(), kind=x.kind, digest=x.digest, trial_id=trial.id)
                    .on_conflict_do_nothing()
                )
        current = (
            await s.scalars(
                select(TenantSubscription)
                .where(TenantSubscription.tenant_id == tenant.id, TenantSubscription.status.in_(CURRENT))
                .with_for_update()
            )
        ).one_or_none()
        before = None
        if current is not None:
            before = {"status": current.status}
            current.status, current.period_end = "cancelled", now
            await s.flush()
        s.add(
            TenantSubscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="trialing",
                period_start=now,
                period_end=trial.ends_at,
                billing_ref=f"trial:{trial.id}",
            )
        )
        payload = {"tenant_id": str(tenant.id), "trial_id": str(trial.id)}
        for days in REMINDERS:
            await enqueue(
                uow,
                "trials.remind",
                payload | {"days": days},
                run_at=trial.ends_at - timedelta(days=days),
                dedupe_key=f"trial:{trial.id}:remind:{days}",
                tenant_scoped=False,
            )
        await enqueue(
            uow,
            "trials.end",
            payload,
            run_at=trial.ends_at,
            dedupe_key=f"trial:{trial.id}:end",
            tenant_scoped=False,
        )
        if owner.email:
            await queue_email(
                uow,
                "trial_started",
                owner.email,
                {
                    "institution": tenant.name,
                    "plan_name": plan.name,
                    "ends_on": trial.ends_at.strftime("%d %B %Y"),
                    "action_url": f"{self.infra.settings.tenant_origin(tenant.slug)}/admin/plan",
                },
                tenant_scoped=False,
            )
        actor = Actor.system(f"tenant owner {user_label}")  # platform log: not a platform user
        after = {"plan": plan.code, "ends_at": trial.ends_at.isoformat(), "risk_score": score, "flags": flags}
        s.add(
            AuditLog(
                tenant_id=tenant.id,
                actor_type="user",
                actor_id=owner.id,
                actor_label=user_label,
                action="trial.started",
                entity_type="subscription",
                entity_id=str(tenant.id),
                summary=f"{plan.name} started; ends {trial.ends_at:%d %b %Y}",
                before=before,
                after=after,
                request_id=uow.meta.get("request_id"),
                ip=uow.meta.get("ip"),
            )
        )
        await record_platform(
            uow,
            actor,
            "trial.started",
            target_tenant_id=tenant.id,
            entity_type="tenant",
            entity_id=tenant.id,
            after=after,
        )
        return trial

    async def grant(self, uow: UnitOfWork, staff: Actor, tenant_id: uuid.UUID, reason: str) -> TenantTrial:
        """ScoreCode staff start a trial by hand (e.g. after a review). Still once per tenant."""
        s = uow.session
        tenant = (await s.scalars(select(Tenant).where(Tenant.id == tenant_id).with_for_update())).one()
        if (await s.scalars(select(TenantTrial.id).where(TenantTrial.tenant_id == tenant.id))).first():
            raise TrialRefused("This institution has already had its trial.", reason="used")
        if await self._paid_before(uow, tenant.id):
            raise TrialRefused("This institution has had a paid plan.", reason="ineligible")
        owner = (
            await s.scalars(
                select(User)
                .join(UserRole, UserRole.user_id == User.id)
                .where(User.tenant_id == tenant.id, UserRole.role == "institution_owner")
            )
        ).one()
        signals = collect(
            self.key,
            tenant_id=str(tenant.id),
            owner_email=owner.email or owner.login_id,
            device_id=None,
            phones=[],
            institution_name=tenant.name,
            ip=None,
        )
        trial = await self._begin(uow, tenant, owner, owner.full_name, signals, 0, [], granted_by=staff.id)
        await record_platform(
            uow,
            staff,
            "trial.granted",
            target_tenant_id=tenant.id,
            entity_type="tenant",
            entity_id=tenant.id,
            after={"ends_at": trial.ends_at.isoformat()},
            reason=reason,
        )
        return trial

    @staticmethod
    async def close_for_plan_change(uow: UnitOfWork, tenant_id: uuid.UUID, *, new_plan_code: str) -> None:
        """A platform plan change ends a running trial: converted to a paid plan, or revoked."""
        trial = (
            await uow.session.scalars(
                select(TenantTrial)
                .where(TenantTrial.tenant_id == tenant_id, TenantTrial.status == "active")
                .with_for_update()
            )
        ).one_or_none()
        if trial is not None:
            trial.status = "revoked" if new_plan_code in (FREE_PLAN_CODE, TRIAL_PLAN_CODE) else "converted"
            trial.ended_at, trial.end_reason = utcnow(), "plan changed by ScoreCode"

    # ---- end ------------------------------------------------------------------------------------
    async def end(
        self, tenant_id: uuid.UUID, trial_id: uuid.UUID, *, reason: str = "expired"
    ) -> dict[str, Any]:
        """Back to Free when the trial runs out (or is revoked). Nothing is deleted: over-limit data stays
        readable, and adding more is blocked until the institution upgrades or archives (docs/12 §4)."""
        async with self.infra.db.platform_uow() as uow:
            s = uow.session
            trial = (
                await s.scalars(select(TenantTrial).where(TenantTrial.id == trial_id).with_for_update())
            ).one_or_none()
            if trial is None or trial.tenant_id != tenant_id or trial.status != "active":
                return {"skipped": trial.status if trial else "missing"}
            now = utcnow()
            if reason == "expired" and trial.ends_at > now + timedelta(minutes=1):
                return {"skipped": "not yet"}
            trial.status = "ended" if reason == "expired" else "revoked"
            trial.ended_at, trial.end_reason = now, reason
            sub = (
                await s.scalars(
                    select(TenantSubscription)
                    .where(
                        TenantSubscription.tenant_id == tenant_id,
                        TenantSubscription.status == "trialing",
                        TenantSubscription.billing_ref == f"trial:{trial.id}",
                    )
                    .with_for_update()
                )
            ).one_or_none()
            if sub is not None:
                sub.status, sub.period_end = ("expired" if reason == "expired" else "cancelled"), now
                await s.flush()
                free = await _plan(uow, FREE_PLAN_CODE)
                s.add(
                    TenantSubscription(
                        tenant_id=tenant_id, plan_id=free.id, status="active", period_start=now
                    )
                )
            tenant = (await s.scalars(select(Tenant).where(Tenant.id == tenant_id))).one()
            s.add(
                AuditLog(
                    tenant_id=tenant_id,
                    actor_type="system",
                    actor_label="ScoreCode",
                    action="trial.ended",
                    entity_type="subscription",
                    entity_id=str(tenant_id),
                    summary="Trial ended; back on the Free plan",
                    after={"reason": reason},
                )
            )
            owner_email = await self._owner_email(uow, tenant_id)
            if owner_email and reason == "expired":
                await queue_email(
                    uow,
                    "trial_ended",
                    owner_email,
                    {
                        "institution": tenant.name,
                        "action_url": f"{self.infra.settings.tenant_origin(tenant.slug)}/admin/plan",
                    },
                    tenant_scoped=False,
                )
        await EntitlementService(self.infra).invalidate(tenant_id)
        return {"ended": str(trial_id), "reason": reason}

    async def remind(self, tenant_id: uuid.UUID, trial_id: uuid.UUID, days: int) -> dict[str, Any]:
        async with self.infra.db.platform_uow() as uow:
            trial = (
                await uow.session.scalars(select(TenantTrial).where(TenantTrial.id == trial_id))
            ).one_or_none()
            if trial is None or trial.status != "active" or trial.tenant_id != tenant_id:
                return {"skipped": "inactive"}
            tenant = (await uow.session.scalars(select(Tenant).where(Tenant.id == tenant_id))).one()
            email = await self._owner_email(uow, tenant_id)
            if email:
                await queue_email(
                    uow,
                    "trial_ending",
                    email,
                    {
                        "institution": tenant.name,
                        "days": days,
                        "ends_on": trial.ends_at.strftime("%d %B %Y"),
                        "action_url": f"{self.infra.settings.tenant_origin(tenant.slug)}/admin/plan",
                    },
                    tenant_scoped=False,
                )
        return {"reminded": days}

    @staticmethod
    async def _owner_email(uow: UnitOfWork, tenant_id: uuid.UUID) -> str | None:
        return (
            await uow.session.scalars(
                select(User.email)
                .join(UserRole, UserRole.user_id == User.id)
                .where(User.tenant_id == tenant_id, UserRole.role == "institution_owner")
            )
        ).first()


def _ids(ctx: JobContext) -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(ctx.job.payload["tenant_id"]), uuid.UUID(ctx.job.payload["trial_id"])


@registry.register("trials.end", queue="maintenance", max_attempts=5)
async def end_trial(ctx: JobContext) -> dict[str, Any]:
    tenant_id, trial_id = _ids(ctx)
    return await TrialService(ctx.infra).end(tenant_id, trial_id)


@registry.register("trials.remind", queue="maintenance", max_attempts=3)
async def remind_trial(ctx: JobContext) -> dict[str, Any]:
    tenant_id, trial_id = _ids(ctx)
    return await TrialService(ctx.infra).remind(tenant_id, trial_id, int(ctx.job.payload["days"]))
