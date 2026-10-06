"""Platform console API (``admin.<base>`` host only; ScoreCode staff with TOTP)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select

from app.core.http import InfraDep, PlatformUoW, Principal, require_platform
from app.core.pagination import Page, clamp_limit, decode_cursor, encode_cursor
from app.modules.audit.models import PlatformAuditLog
from app.modules.identity.permissions import PlatformP
from app.modules.platform.service import PlatformService

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])

ViewTenants = Annotated[Principal, require_platform(PlatformP.TENANTS_VIEW)]
ManageTenants = Annotated[Principal, require_platform(PlatformP.TENANTS_MANAGE)]


class TenantRow(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    type: str
    status: str
    created_at: datetime
    plan_code: str | None
    plan_name: str
    subscription_status: str
    active_students: int
    staff_users: int
    host: str


class TenantList(BaseModel):
    items: list[TenantRow]
    total: int
    limit: int
    offset: int


@router.get("/tenants")
async def list_tenants(
    uow: PlatformUoW,
    infra: InfraDep,
    _: ViewTenants,
    q: str | None = Query(default=None, max_length=100),
    status: Literal["active", "suspended", "closing", "closed"] | None = None,
    plan: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> TenantList:
    items, total = await PlatformService(infra).list_tenants(
        uow, q=q, status=status, plan=plan, limit=limit, offset=offset
    )
    return TenantList(items=[TenantRow(**i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/tenants/{tenant_id}")
async def tenant_detail(
    tenant_id: uuid.UUID, uow: PlatformUoW, infra: InfraDep, _: ViewTenants
) -> dict[str, Any]:
    return await PlatformService(infra).tenant_detail(uow, tenant_id)


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=500)


class OkOut(BaseModel):
    ok: bool = True


@router.post("/tenants/{tenant_id}/suspend")
async def suspend_tenant(
    tenant_id: uuid.UUID, body: ReasonIn, uow: PlatformUoW, infra: InfraDep, principal: ManageTenants
) -> OkOut:
    await PlatformService(infra).set_status(uow, principal, tenant_id, suspend=True, reason=body.reason)
    return OkOut()


@router.post("/tenants/{tenant_id}/reactivate")
async def reactivate_tenant(
    tenant_id: uuid.UUID, body: ReasonIn, uow: PlatformUoW, infra: InfraDep, principal: ManageTenants
) -> OkOut:
    await PlatformService(infra).set_status(uow, principal, tenant_id, suspend=False, reason=body.reason)
    return OkOut()


class PlanChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    plan_code: str = Field(min_length=2, max_length=32)
    status: Literal["active", "trialing", "past_due"] = "active"
    period_end: datetime | None = None
    billing_ref: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=3, max_length=500)


@router.put("/tenants/{tenant_id}/plan")
async def change_plan(
    tenant_id: uuid.UUID, body: PlanChangeIn, uow: PlatformUoW, infra: InfraDep, principal: ManageTenants
) -> OkOut:
    await PlatformService(infra).change_plan(
        uow,
        principal,
        tenant_id,
        plan_code=body.plan_code,
        status=body.status,
        period_end=body.period_end,
        billing_ref=body.billing_ref,
        reason=body.reason,
    )
    return OkOut()


class OverrideIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    value: bool | int | list[str] | None
    expires_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)


@router.put("/tenants/{tenant_id}/overrides/{feature_key}")
async def set_override(
    tenant_id: uuid.UUID,
    feature_key: str,
    body: OverrideIn,
    uow: PlatformUoW,
    infra: InfraDep,
    principal: ManageTenants,
) -> OkOut:
    await PlatformService(infra).set_override(
        uow,
        principal,
        tenant_id,
        feature_key=feature_key,
        value=body.value,
        expires_at=body.expires_at,
        reason=body.reason,
    )
    return OkOut()


@router.delete("/tenants/{tenant_id}/overrides/{feature_key}")
async def delete_override(
    tenant_id: uuid.UUID,
    feature_key: str,
    uow: PlatformUoW,
    infra: InfraDep,
    principal: ManageTenants,
    reason: str = Query(min_length=3, max_length=500),
) -> OkOut:
    await PlatformService(infra).delete_override(uow, principal, tenant_id, feature_key, reason)
    return OkOut()


@router.get("/plans")
async def plans(uow: PlatformUoW, infra: InfraDep, _: ViewTenants) -> dict[str, Any]:
    return await PlatformService(infra).plans(uow)


@router.get("/metrics/overview")
async def overview(
    uow: PlatformUoW, infra: InfraDep, _: Annotated[Principal, require_platform(PlatformP.HEALTH_VIEW)]
) -> dict[str, Any]:
    return await PlatformService(infra).overview(uow)


@router.get("/health/deep")
async def deep_health(
    infra: InfraDep, _: Annotated[Principal, require_platform(PlatformP.HEALTH_VIEW)]
) -> dict[str, Any]:
    return await PlatformService(infra).deep_health()


class PlatformAuditEntry(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    platform_user_id: uuid.UUID | None
    actor_label: str | None
    action: str
    target_tenant_id: uuid.UUID | None
    entity_type: str | None
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    ip: str | None


@router.get("/audit-logs")
async def platform_audit(
    uow: PlatformUoW,
    _: Annotated[Principal, require_platform(PlatformP.AUDIT_VIEW)],
    tenant_id: uuid.UUID | None = None,
    action: str | None = Query(default=None, max_length=64),
    cursor: str | None = None,
    limit: int | None = None,
) -> Page[PlatformAuditEntry]:
    n = clamp_limit(limit)
    stmt = (
        select(PlatformAuditLog)
        .order_by(PlatformAuditLog.occurred_at.desc(), PlatformAuditLog.id.desc())
        .limit(n + 1)
    )
    if tenant_id:
        stmt = stmt.where(PlatformAuditLog.target_tenant_id == tenant_id)
    if action:
        stmt = stmt.where(PlatformAuditLog.action.startswith(action))
    after = decode_cursor(cursor)
    if after:
        ts, last = datetime.fromisoformat(after[0]), uuid.UUID(after[1])
        stmt = stmt.where(
            or_(
                PlatformAuditLog.occurred_at < ts,
                and_(PlatformAuditLog.occurred_at == ts, PlatformAuditLog.id < last),
            )
        )
    rows = list((await uow.session.scalars(stmt)).all())
    next_cursor = None
    if len(rows) > n:
        rows = rows[:n]
        next_cursor = encode_cursor([rows[-1].occurred_at.isoformat(), str(rows[-1].id)])
    return Page[PlatformAuditEntry](
        items=[PlatformAuditEntry.model_validate(r, from_attributes=True) for r in rows],
        next_cursor=next_cursor,
    )
