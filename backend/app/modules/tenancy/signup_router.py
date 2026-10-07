from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.device import remember_device
from app.core.http import InfraDep, TenantDep, client_ip, public
from app.core.ratelimit import Bucket
from app.core.tenant import Realm
from app.modules.identity.router import SessionOut, set_session_cookie
from app.modules.identity.sessions import SessionService
from app.modules.tenancy.signup import SignupInput, SignupService

router = APIRouter(prefix="/api/v1", tags=["signup"])
SLUG_CHECK = Bucket.per_minute("slug_check", 60, burst=30)


class AvailabilityOut(BaseModel):
    slug: str
    available: bool
    reason: str | None
    host: str


@router.get("/signup/slug-availability", dependencies=[public(Realm.SITE)])
async def slug_availability(
    request: Request, infra: InfraDep, slug: str = Query(min_length=1, max_length=40)
) -> AvailabilityOut:
    await infra.limiter.hit(SLUG_CHECK, client_ip(request))
    available, reason = await SignupService(infra).availability(slug)
    normalised = slug.strip().lower()
    return AvailabilityOut(
        slug=normalised, available=available, reason=reason, host=f"{normalised}.{infra.settings.base_domain}"
    )


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=32, pattern=r"^[0-9+()\-\s]{6,32}$")
    institution_name: str = Field(min_length=3, max_length=200)
    institution_type: Literal["school", "college", "university", "coaching", "other"]
    slug: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=1, max_length=256)


class SignupStartedOut(BaseModel):
    email: str


@router.post("/signup", status_code=202, dependencies=[public(Realm.SITE)])
async def signup(body: SignupIn, request: Request, response: Response, infra: InfraDep) -> SignupStartedOut:
    remember_device(request, response, infra.settings)  # one of the trial signals later (docs/12 §6)
    await SignupService(infra).start(
        SignupInput(
            email=str(body.email),
            full_name=body.full_name,
            phone=body.phone,
            institution_name=body.institution_name,
            institution_type=body.institution_type,
            slug=body.slug,
            password=body.password,
        ),
        ip=client_ip(request),
    )
    return SignupStartedOut(email=str(body.email).lower())


class VerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=200)


class VerifyOut(BaseModel):
    slug: str
    tenant_url: str
    handoff_url: str


@router.post("/signup/verify", dependencies=[public(Realm.SITE)])
async def verify_signup(body: VerifyIn, infra: InfraDep) -> VerifyOut:
    result = await SignupService(infra).verify(body.token)
    return VerifyOut(slug=result.slug, tenant_url=result.tenant_url, handoff_url=result.handoff_url)


class HandoffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=200)


@router.post("/auth/handoff", dependencies=[public(Realm.TENANT)])
async def handoff(
    body: HandoffIn, request: Request, response: Response, tenant: TenantDep, infra: InfraDep
) -> SessionOut:
    result = await SignupService(infra).handoff(
        tenant, body.token, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    set_session_cookie(response, infra.settings, result.token, SessionService(infra).cookie_max_age("staff"))
    return SessionOut(user_kind=result.user_kind, roles=result.roles)
