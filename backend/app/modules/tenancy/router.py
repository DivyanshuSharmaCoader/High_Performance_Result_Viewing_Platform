"""Institution settings and subscription/usage (tenant admin)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from app.core.errors import Conflict
from app.core.http import InfraDep, Principal, TenantDep, UoW, require
from app.modules.audit.service import Actor, diff, record
from app.modules.branding.service import BrandingService
from app.modules.entitlements.catalogue import FEATURES, LIMIT_TO_USAGE_METRIC, F
from app.modules.entitlements.service import EntitlementService
from app.modules.identity.permissions import P
from app.modules.tenancy import onboarding
from app.modules.tenancy.models import TenantSettings

router = APIRouter(prefix="/api/v1/admin", tags=["settings"])

SETTINGS_FIELDS = (
    "official_name",
    "address",
    "affiliation",
    "contact_email",
    "contact_phone",
    "approval_mode",
    "student_activation_mode",
    "verification_disclosure",
    "student_stats",
    "publish_notify_email",
)


class SettingsOut(BaseModel):
    official_name: str
    address: str | None
    affiliation: str | None
    contact_email: str | None
    contact_phone: str | None
    approval_mode: str
    student_activation_mode: str
    verification_disclosure: str
    student_stats: str
    publish_notify_email: bool
    special_codes: dict[str, Any]
    version: int


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int
    official_name: str = Field(min_length=2, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    affiliation: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=32, pattern=r"^[0-9+()\-\s]{6,32}$")
    approval_mode: Literal["single", "maker_checker"] = "single"
    student_activation_mode: Literal["code", "email"] = "code"
    verification_disclosure: Literal["masked", "masked_plus_challenge"] = "masked"
    student_stats: Literal["none", "class_average", "full"] = "class_average"
    publish_notify_email: bool = True


def _out(s: TenantSettings) -> SettingsOut:
    return SettingsOut(**{k: getattr(s, k) for k in (*SETTINGS_FIELDS, "special_codes", "version")})


@router.get("/settings")
async def get_settings_(uow: UoW, _: Principal = require(P.SETTINGS_MANAGE)) -> SettingsOut:
    return _out((await uow.session.scalars(select(TenantSettings))).one())


@router.put("/settings")
async def update_settings(
    body: SettingsIn,
    uow: UoW,
    tenant: TenantDep,
    infra: InfraDep,
    principal: Principal = require(P.SETTINGS_MANAGE),
) -> SettingsOut:
    s = (await uow.session.scalars(select(TenantSettings).with_for_update())).one()
    if s.version != body.version:
        raise Conflict("Settings were changed by someone else. Reload to see the latest version.")
    ent = await EntitlementService(infra).effective(uow)
    if body.approval_mode == "maker_checker" and s.approval_mode != "maker_checker":
        ent.require(F.MAKER_CHECKER_APPROVAL)
    if (
        body.verification_disclosure == "masked_plus_challenge"
        and s.verification_disclosure != body.verification_disclosure
    ):
        ent.require(F.VERIFICATION_CHALLENGE)
    before = {k: getattr(s, k) for k in SETTINGS_FIELDS}
    data = body.model_dump(exclude={"version"})
    data["contact_email"] = str(body.contact_email) if body.contact_email else None
    for k, v in data.items():
        setattr(s, k, v if v != "" else None)
    s.version += 1
    d_before, d_after = diff(before, {k: getattr(s, k) for k in SETTINGS_FIELDS})
    if d_after:
        await record(
            uow,
            Actor.from_principal(principal),
            "settings.updated",
            entity_type="settings",
            entity_id=tenant.tenant_id,
            before=d_before,
            after=d_after,
        )
        await BrandingService(infra).invalidate(uow, tenant)
    await uow.flush()
    return _out(s)


class LimitUsage(BaseModel):
    key: str
    description: str
    limit: int | None
    used: int


class SubscriptionOut(BaseModel):
    plan_code: str
    plan_name: str
    status: str
    period_end: str | None
    limits: list[LimitUsage]
    features: dict[str, Any]
    overrides: list[str]


@router.get("/subscription")
async def subscription(
    uow: UoW, infra: InfraDep, _: Principal = require(P.SUBSCRIPTION_VIEW)
) -> SubscriptionOut:
    svc = EntitlementService(infra)
    ent = await svc.effective(uow, fresh=True)
    usage = await svc.usage(uow)
    limits = []
    for f in FEATURES:
        if f.kind != "limit":
            continue
        metric = LIMIT_TO_USAGE_METRIC.get(f.key)
        used = usage.get(metric, 0) if metric else 0
        if f.key == F.MAX_STORAGE_MB:
            used = round(used / (1024 * 1024))
        limits.append(LimitUsage(key=f.key, description=f.description, limit=ent.limit(f.key), used=used))
    return SubscriptionOut(
        plan_code=ent.plan_code,
        plan_name=ent.plan_name,
        status=ent.subscription_status,
        period_end=ent.period_end,
        limits=limits,
        features={f.key: ent.values.get(f.key) for f in FEATURES if f.kind != "limit"},
        overrides=ent.overrides,
    )


class OnboardingStep(BaseModel):
    key: str
    title: str
    description: str
    href: str
    required_for_publishing: bool
    done: bool
    detail: str | None


class OnboardingOut(BaseModel):
    steps: list[OnboardingStep]
    completed: int
    total: int
    dismissed: bool


@router.get("/onboarding")
async def get_onboarding(uow: UoW, _: Principal = require(P.SETTINGS_MANAGE)) -> OnboardingOut:
    items = []
    for step in onboarding.steps():
        result = await step.check(uow)
        items.append(
            OnboardingStep(
                key=step.key,
                title=step.title,
                description=step.description,
                href=step.href,
                required_for_publishing=step.required_for_publishing,
                done=result.done,
                detail=result.detail,
            )
        )
    s = (await uow.session.scalars(select(TenantSettings))).one()
    return OnboardingOut(
        steps=items,
        completed=sum(1 for i in items if i.done),
        total=len(items),
        dismissed=s.onboarding_dismissed_at is not None,
    )


class DismissIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dismissed: bool


@router.put("/onboarding")
async def dismiss_onboarding(
    body: DismissIn, uow: UoW, _: Principal = require(P.SETTINGS_MANAGE)
) -> OnboardingOut:
    from app.core.clock import utcnow

    s = (await uow.session.scalars(select(TenantSettings).with_for_update())).one()
    s.onboarding_dismissed_at = utcnow() if body.dismissed else None
    await uow.flush()
    return await get_onboarding(uow)
