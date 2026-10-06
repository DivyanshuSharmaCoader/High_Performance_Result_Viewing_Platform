from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.http import InfraDep, Principal, TenantDep, UoW, require
from app.modules.identity.permissions import P
from app.modules.identity.service import AuthService
from app.modules.identity.staff import ProfileData, StaffService

router = APIRouter(prefix="/api/v1/admin/staff", tags=["staff"])


class StaffOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None
    role: str
    status: str
    last_login_at: datetime | None
    created_at: datetime
    employee_code: str | None = None
    designation: str | None = None
    department_id: uuid.UUID | None = None
    phone: str | None = None


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    full_name: str = Field(min_length=2, max_length=200)
    employee_code: str | None = Field(default=None, max_length=40)
    designation: str | None = Field(default=None, max_length=100)
    department_id: uuid.UUID | None = None
    phone: str | None = Field(default=None, max_length=32)


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    role: Literal["institution_admin", "faculty"]


class RoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["institution_admin", "faculty"]


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool


class OkOut(BaseModel):
    ok: bool = True


@router.get("")
async def list_staff(
    uow: UoW,
    infra: InfraDep,
    q: str | None = None,
    role: str | None = None,
    _: Principal = require(P.STAFF_VIEW),
) -> list[StaffOut]:
    members = await StaffService(infra).list(uow, q=q, role=role)
    return [StaffOut(**m.__dict__) for m in members]


@router.post("", status_code=201)
async def invite_staff(
    body: InviteIn,
    uow: UoW,
    tenant: TenantDep,
    infra: InfraDep,
    principal: Principal = require(P.STAFF_MANAGE),
) -> StaffOut:
    svc = StaffService(infra)
    user = await svc.invite(
        uow, tenant, principal, email=str(body.email), full_name=body.full_name, role=body.role
    )
    return StaffOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=body.role,
        status=user.status,
        last_login_at=None,
        created_at=user.created_at,
    )


@router.post("/{user_id}/resend-invite")
async def resend_invite(
    user_id: uuid.UUID,
    uow: UoW,
    tenant: TenantDep,
    infra: InfraDep,
    principal: Principal = require(P.STAFF_MANAGE),
) -> OkOut:
    await StaffService(infra).resend_invite(uow, tenant, principal, user_id)
    return OkOut()


@router.put("/{user_id}/role")
async def change_role(
    user_id: uuid.UUID,
    body: RoleIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.STAFF_MANAGE),
) -> OkOut:
    AuthService(infra).require_recent_auth(principal)
    await StaffService(infra).change_role(uow, principal, user_id, body.role)
    return OkOut()


@router.put("/{user_id}/status")
async def set_status(
    user_id: uuid.UUID,
    body: StatusIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.STAFF_MANAGE),
) -> OkOut:
    await StaffService(infra).set_disabled(uow, principal, user_id, body.disabled)
    return OkOut()


@router.put("/{user_id}/profile")
async def update_profile(
    user_id: uuid.UUID,
    body: ProfileIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.STAFF_MANAGE),
) -> StaffOut:
    member = await StaffService(infra).update_profile(
        uow,
        principal,
        user_id,
        ProfileData(
            full_name=body.full_name,
            employee_code=body.employee_code,
            designation=body.designation,
            department_id=body.department_id,
            phone=body.phone,
        ),
    )
    return StaffOut(**member.__dict__)


@router.post("/{user_id}/transfer-ownership")
async def transfer_ownership(
    user_id: uuid.UUID, uow: UoW, infra: InfraDep, principal: Principal = require(P.OWNER_TRANSFER)
) -> OkOut:
    AuthService(infra).require_recent_auth(principal)
    await StaffService(infra).transfer_ownership(uow, principal, user_id)
    return OkOut()
