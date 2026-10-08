"""Self-serve sign-up (docs/03 W1, P4.4).

1. ``POST /signup`` on the marketing host stores a pending request (password already hashed) and emails a
   30-minute verification link. Nothing is created yet, so nobody can squat a slug without a mailbox.
2. ``POST /signup/verify`` provisions the tenant through the same service the seed command uses and
   issues a 10-minute, single-use sign-in handoff token for the new tenant host (cookies are host-only,
   so the session must be created on the tenant's own origin).
3. ``POST /auth/handoff`` on the tenant host exchanges that token for a session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select

from app.core.breached import password_issues
from app.core.clock import utcnow
from app.core.container import Infra
from app.core.errors import Conflict, ValidationFailed
from app.core.ratelimit import signup_ip_bucket
from app.core.security import hash_token, new_token
from app.core.tenant import TenantContext
from app.modules.audit.service import Actor
from app.modules.identity.models import AuthToken, SignupRequest, User
from app.modules.identity.service import LoginResult
from app.modules.identity.sessions import SessionService
from app.modules.notifications.emails import queue_email
from app.modules.tenancy.models import TENANT_TYPES
from app.modules.tenancy.service import (
    OwnerSpec,
    ProvisionRequest,
    provision_tenant,
    slug_taken,
    validate_slug,
)

SIGNUP_TTL = timedelta(minutes=30)
HANDOFF_TTL = timedelta(minutes=10)
DEFAULT_SIGNUP_PLAN = "free"
DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "10minutemail.com",
        "tempmail.com",
        "yopmail.com",
        "trashmail.com",
        "sharklasers.com",
        "getnada.com",
        "dispostable.com",
        "maildrop.cc",
    }
)


@dataclass(frozen=True)
class SignupInput:
    email: str
    full_name: str
    phone: str | None
    institution_name: str
    institution_type: str
    slug: str
    password: str


@dataclass(frozen=True)
class VerifiedSignup:
    slug: str
    tenant_url: str
    handoff_url: str


class SignupService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra
        self.settings = infra.settings

    async def availability(self, slug: str) -> tuple[bool, str | None]:
        try:
            normalised = validate_slug(slug)
        except ValidationFailed as exc:
            return False, exc.detail
        async with self.infra.db.uow() as uow:
            if await slug_taken(uow, normalised):
                return False, "This address is already taken."
        return True, None

    async def start(self, data: SignupInput, *, ip: str) -> None:
        await self.infra.limiter.hit(signup_ip_bucket(self.settings), ip)
        slug = validate_slug(data.slug)
        email = data.email.strip().lower()
        if email.rsplit("@", 1)[-1] in DISPOSABLE_DOMAINS:
            raise ValidationFailed("Please use your institution or personal email address.", field="email")
        if data.institution_type not in TENANT_TYPES:
            raise ValidationFailed("Choose an institution type.", field="institution_type")
        problems = await password_issues(
            data.password, min_length=12, context=(email, slug), settings=self.settings
        )
        if problems:
            raise ValidationFailed(" ".join(problems), field="password")
        token = new_token(32)
        password_hash = await self.infra.passwords.hash(data.password)
        async with self.infra.db.uow(ip=ip) as uow:
            if await slug_taken(uow, slug):
                raise Conflict("This address is already taken.", field="slug")
            uow.session.add(
                SignupRequest(
                    email=email,
                    full_name=data.full_name.strip(),
                    phone=(data.phone or "").strip() or None,
                    institution_name=data.institution_name.strip(),
                    institution_type=data.institution_type,
                    slug=slug,
                    password_hash=password_hash,
                    token_hash=hash_token(token),
                    expires_at=utcnow() + SIGNUP_TTL,
                    ip=ip,
                )
            )
            site = self.settings.public_origin(self.settings.base_domain)
            await queue_email(
                uow,
                "signup_verify",
                email,
                {
                    "institution": data.institution_name.strip(),
                    "portal_host": f"{slug}.{self.settings.base_domain}",
                    "action_url": f"{site}/signup/verify?token={token}",
                },
                tenant_scoped=False,
            )

    async def verify(self, token: str) -> VerifiedSignup:
        async with self.infra.db.uow() as uow:
            req = (
                await uow.session.scalars(
                    select(SignupRequest)
                    .where(SignupRequest.token_hash == hash_token(token))
                    .with_for_update()
                )
            ).one_or_none()
            if req is None or req.consumed_at is not None or req.expires_at < utcnow():
                raise ValidationFailed(
                    "This link is invalid or has expired. Please sign up again.", field="token"
                )
            tenant = await provision_tenant(
                uow,
                ProvisionRequest(
                    slug=req.slug,
                    name=req.institution_name,
                    type=req.institution_type,
                    plan_code=DEFAULT_SIGNUP_PLAN,
                    owner=OwnerSpec(
                        email=req.email, full_name=req.full_name, password_hash=req.password_hash
                    ),
                ),
                Actor.system("signup"),
            )
            req.consumed_at = utcnow()
            req.tenant_id = tenant.id
            owner = (await uow.session.scalars(select(User).where(User.login_id == req.email))).one()
            handoff = new_token(32)
            uow.session.add(
                AuthToken(
                    tenant_id=tenant.id,
                    user_id=owner.id,
                    purpose="signin_handoff",
                    token_hash=hash_token(handoff),
                    expires_at=utcnow() + HANDOFF_TTL,
                )
            )
        origin = self.settings.tenant_origin(tenant.slug)
        return VerifiedSignup(
            slug=tenant.slug,
            tenant_url=origin,
            handoff_url=f"{origin}/welcome?handoff={handoff}",
        )

    async def handoff(
        self, tenant: TenantContext, token: str, *, ip: str, user_agent: str | None
    ) -> LoginResult:
        sessions = SessionService(self.infra)
        async with self.infra.db.uow(tenant.tenant_id, ip=ip) as uow:
            row = (
                await uow.session.scalars(
                    select(AuthToken).where(AuthToken.token_hash == hash_token(token)).with_for_update()
                )
            ).one_or_none()
            if row is None or row.purpose != "signin_handoff" or row.consumed_at or row.expires_at < utcnow():
                raise ValidationFailed("This sign-in link has expired. Sign in with your email and password.")
            row.consumed_at = utcnow()
            user = (await uow.session.scalars(select(User).where(User.id == row.user_id))).one()
            user.last_login_at = utcnow()
            session_token = await sessions.create(uow, user, ip=ip, user_agent=user_agent)
        return LoginResult(
            token=session_token, user_id=user.id, user_kind="staff", roles=["institution_owner"]
        )
