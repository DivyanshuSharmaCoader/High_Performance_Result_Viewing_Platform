"""Authentication & self-service endpoints (tenant realm) and platform authentication."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from app.core.config import Settings
from app.core.errors import NotAuthenticated
from app.core.http import (
    InfraDep,
    PlatformUoW,
    Principal,
    TenantDep,
    UoW,
    client_ip,
    get_principal,
    public,
    require,
    require_platform,
)
from app.core.tenant import Realm
from app.modules.entitlements.service import EntitlementService
from app.modules.identity.models import User
from app.modules.identity.service import AuthService

router = APIRouter(prefix="/api/v1", tags=["auth"])
platform_router = APIRouter(prefix="/api/v1/platform", tags=["platform-auth"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def set_session_cookie(response: Response, settings: Settings, token: str, max_age: int) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )


class LoginIn(Strict):
    login_id: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class SessionOut(BaseModel):
    user_kind: str
    roles: list[str]


class OkOut(BaseModel):
    ok: bool = True


@router.get("/auth/csrf", dependencies=[public()])
async def csrf() -> OkOut:
    """Ensures the CSRF cookie exists (the middleware issues it on any API response)."""
    return OkOut()


@router.post("/auth/login", dependencies=[public(Realm.TENANT)])
async def login(
    body: LoginIn, request: Request, response: Response, tenant: TenantDep, infra: InfraDep
) -> SessionOut:
    svc = AuthService(infra)
    result = await svc.login(
        tenant,
        body.login_id,
        body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, infra.settings, result.token, svc.sessions.cookie_max_age(result.user_kind))
    return SessionOut(user_kind=result.user_kind, roles=result.roles)


@router.post("/auth/logout", dependencies=[public(Realm.TENANT)])
async def logout(request: Request, response: Response, uow: UoW, infra: InfraDep) -> OkOut:
    try:
        principal = await get_principal(request)
    except NotAuthenticated:
        principal = None
    if principal is not None and principal.kind == "user":
        await AuthService(infra).logout(uow, principal)
    clear_session_cookie(response, infra.settings)
    return OkOut()


class LogoutAllOut(BaseModel):
    revoked: int


@router.post("/auth/logout-all")
async def logout_all(
    response: Response, uow: UoW, infra: InfraDep, principal: Principal = require()
) -> LogoutAllOut:
    n = await AuthService(infra).logout_everywhere(uow, principal)
    clear_session_cookie(response, infra.settings)
    return LogoutAllOut(revoked=n)


class ForgotIn(Strict):
    identifier: str = Field(min_length=1, max_length=254)


@router.post("/auth/password/forgot", status_code=202, dependencies=[public(Realm.TENANT)])
async def forgot_password(body: ForgotIn, request: Request, tenant: TenantDep, infra: InfraDep) -> OkOut:
    await AuthService(infra).request_password_reset(tenant, body.identifier, ip=client_ip(request))
    return OkOut()


class ResetIn(Strict):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=1, max_length=256)


@router.post("/auth/password/reset", dependencies=[public(Realm.TENANT)])
async def reset_password(body: ResetIn, tenant: TenantDep, infra: InfraDep) -> OkOut:
    await AuthService(infra).reset_password(tenant, body.token, body.password)
    return OkOut()


class ActivateIn(Strict):
    enrollment_no: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=6, max_length=32)
    password: str = Field(min_length=1, max_length=256)


@router.post("/auth/activate", dependencies=[public(Realm.TENANT)])
async def activate(
    body: ActivateIn, request: Request, response: Response, tenant: TenantDep, infra: InfraDep
) -> SessionOut:
    svc = AuthService(infra)
    result = await svc.activate_student(
        tenant,
        body.enrollment_no,
        body.code,
        body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, infra.settings, result.token, svc.sessions.cookie_max_age("student"))
    return SessionOut(user_kind=result.user_kind, roles=result.roles)


class InvitePeekOut(BaseModel):
    full_name: str
    email: str


@router.get("/auth/invitations/{token}", dependencies=[public(Realm.TENANT)])
async def peek_invitation(token: str, tenant: TenantDep, infra: InfraDep) -> InvitePeekOut:
    return InvitePeekOut(**await AuthService(infra).peek_invite(tenant, token))


class AcceptInviteIn(Strict):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=1, max_length=256)


@router.post("/auth/invitations/accept", dependencies=[public(Realm.TENANT)])
async def accept_invitation(
    body: AcceptInviteIn, request: Request, response: Response, tenant: TenantDep, infra: InfraDep
) -> SessionOut:
    svc = AuthService(infra)
    result = await svc.accept_invite(
        tenant, body.token, body.password, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    set_session_cookie(response, infra.settings, result.token, svc.sessions.cookie_max_age("staff"))
    return SessionOut(user_kind=result.user_kind, roles=result.roles)


class ReauthIn(Strict):
    password: str = Field(min_length=1, max_length=256)


@router.post("/auth/reauth")
async def reauth(body: ReauthIn, uow: UoW, infra: InfraDep, principal: Principal = require()) -> OkOut:
    await AuthService(infra).reauthenticate(uow, principal, body.password)
    return OkOut()


# ---- /me ----------------------------------------------------------------------------------------


class TenantSummary(BaseModel):
    id: str
    slug: str
    name: str


class MeOut(BaseModel):
    id: str
    full_name: str
    email: str | None
    login_id: str
    kind: str
    roles: list[str]
    permissions: list[str]
    tenant: TenantSummary
    features: dict[str, Any]
    plan: dict[str, Any]
    reauthenticated_at: datetime | None


@router.get("/me")
async def me(uow: UoW, tenant: TenantDep, infra: InfraDep, principal: Principal = require()) -> MeOut:
    user = (await uow.session.scalars(select(User).where(User.id == principal.user_id))).one()
    ent = await EntitlementService(infra).effective(uow)
    return MeOut(
        id=str(user.id),
        full_name=user.full_name,
        email=user.email,
        login_id=user.login_id,
        kind=user.kind,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
        tenant=TenantSummary(id=str(tenant.tenant_id), slug=tenant.slug, name=tenant.name),
        features=ent.values,
        plan={
            "code": ent.plan_code,
            "name": ent.plan_name,
            "status": ent.subscription_status,
            "period_end": ent.period_end,
        },
        reauthenticated_at=principal.reauthenticated_at,
    )


class ChangePasswordIn(Strict):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


@router.put("/me/password")
async def change_password(
    body: ChangePasswordIn, uow: UoW, tenant: TenantDep, infra: InfraDep, principal: Principal = require()
) -> OkOut:
    await AuthService(infra).change_password(uow, principal, body.current_password, body.new_password, tenant)
    return OkOut()


class SessionItem(BaseModel):
    current: bool
    created_at: datetime
    last_seen_at: datetime
    ip: str | None
    user_agent: str | None


@router.get("/me/sessions")
async def my_sessions(uow: UoW, infra: InfraDep, principal: Principal = require()) -> list[SessionItem]:
    rows = await AuthService(infra).sessions.list_for_user(uow, principal.user_id)
    return [
        SessionItem(
            current=r.id == principal.session_hash,
            created_at=r.created_at,
            last_seen_at=r.last_seen_at,
            ip=r.ip,
            user_agent=r.user_agent,
        )
        for r in rows
    ]


# ---- platform realm -----------------------------------------------------------------------------


class PlatformLoginIn(Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    totp_code: str = Field(min_length=6, max_length=10)


class PlatformMeOut(BaseModel):
    id: str
    full_name: str
    roles: list[str]
    permissions: list[str]


@platform_router.post("/auth/login", dependencies=[public(Realm.PLATFORM)])
async def platform_login(
    body: PlatformLoginIn, request: Request, response: Response, infra: InfraDep
) -> OkOut:
    token = await AuthService(infra).platform_login(
        body.email,
        body.password,
        body.totp_code,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, infra.settings, token, infra.settings.platform_session_hours * 3600)
    return OkOut()


@platform_router.post("/auth/logout", dependencies=[public(Realm.PLATFORM)])
async def platform_logout(request: Request, response: Response, uow: PlatformUoW, infra: InfraDep) -> OkOut:
    try:
        principal = await get_principal(request)
    except NotAuthenticated:
        principal = None
    if principal is not None and principal.kind == "platform":
        await AuthService(infra).sessions.revoke_platform(uow, principal.session_hash)
    clear_session_cookie(response, infra.settings)
    return OkOut()


@platform_router.get("/me")
async def platform_me(principal: Annotated[Principal, require_platform()]) -> PlatformMeOut:
    return PlatformMeOut(
        id=str(principal.user_id),
        full_name=principal.display_name,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
    )
