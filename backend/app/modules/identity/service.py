"""Authentication use cases (docs/10 §2): login/logout, password reset, staff invites, student activation,
re-authentication and platform login with mandatory TOTP.

Anti-enumeration rules: unknown accounts, wrong passwords, disabled and locked accounts all produce the
same response after the same amount of Argon2 work; reset/forgot endpoints always answer 202.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import pyotp
from sqlalchemy import select, update

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import Conflict, InvalidCredentials, NotFound, ReauthRequired, ValidationFailed
from app.core.http import Principal
from app.core.metrics import LOGINS
from app.core.ratelimit import (
    ACTIVATION,
    LOGIN_PER_ACCOUNT,
    PASSWORD_RESET,
    PLATFORM_LOGIN_PER_IP,
    activation_ip_bucket,
    login_failure_bucket,
    login_ip_bucket,
)
from app.core.security import hash_token, new_token, normalise_human_code, password_problems
from app.core.tenant import TenantContext
from app.modules.audit.service import Actor, record, record_platform
from app.modules.identity.models import AuthToken, PlatformUser, User, UserRole
from app.modules.identity.sessions import SessionService
from app.modules.notifications.emails import queue_email

LOCKED_HINT = (
    "Check your login details. After several wrong attempts an account is locked for a few minutes; "
    "you can also reset your password."
)
INVITE_TTL = timedelta(days=7)
RESET_TTL = timedelta(minutes=60)
ACTIVATION_TTL = timedelta(days=120)


def normalise_login_id(raw: str) -> str:
    value = raw.strip()
    if "@" in value:
        return value.lower()
    return "".join(value.split()).upper()


def activation_token_hash(tenant_id: uuid.UUID, login_id: str, code: str) -> bytes:
    return hash_token(f"activation:{tenant_id}:{normalise_login_id(login_id)}:{normalise_human_code(code)}")


@dataclass(frozen=True)
class LoginResult:
    token: str
    user_id: uuid.UUID
    user_kind: str
    roles: list[str]


class AuthService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra
        self.settings = infra.settings
        self.sessions = SessionService(infra)

    # ---- helpers --------------------------------------------------------------------------------
    def _lockout_until(self, failures: int, now: datetime) -> datetime | None:
        if failures < self.settings.login_max_failures:
            return None
        exponent = failures - self.settings.login_max_failures
        minutes = min(60, self.settings.login_lockout_minutes * (2**exponent))
        return now + timedelta(minutes=minutes)

    async def _check_password_rules(self, password: str, *, staff: bool, context: tuple[str, ...]) -> None:
        problems = password_problems(password, min_length=12 if staff else 10, context=context)
        if problems:
            raise ValidationFailed(" ".join(problems), field="password")

    # ---- login ----------------------------------------------------------------------------------
    async def login(
        self, tenant: TenantContext, login_id: str, password: str, *, ip: str, user_agent: str | None
    ) -> LoginResult:
        await self.infra.limiter.hit(login_ip_bucket(self.settings), f"{ip}")
        await self.infra.limiter.check(login_failure_bucket(self.settings), f"{ip}")
        normalised = normalise_login_id(login_id)
        await self.infra.limiter.hit(LOGIN_PER_ACCOUNT, f"{tenant.tenant_id}:{normalised}")
        now = utcnow()
        async with self.infra.db.uow(tenant.tenant_id, ip=ip, user_agent=user_agent) as uow:
            user = (
                await uow.session.scalars(select(User).where(User.login_id == normalised).with_for_update())
            ).one_or_none()
            usable = user is not None and user.status == "active" and user.password_hash is not None
            locked = bool(user and user.locked_until and user.locked_until > now)
            if not usable or locked:
                await self.infra.passwords.burn(password)
                await self.infra.limiter.consume(login_failure_bucket(self.settings), f"{ip}")
                LOGINS.labels("tenant", "rejected").inc()
                raise InvalidCredentials(LOCKED_HINT)
            assert user is not None and user.password_hash is not None
            ok = await self.infra.passwords.verify(user.password_hash, password)
            if not ok:
                user.failed_login_count += 1
                lock = self._lockout_until(user.failed_login_count, now)
                if lock is not None:
                    user.locked_until = lock
                    await record(
                        uow,
                        Actor.system("auth"),
                        "user.login_locked",
                        entity_type="user",
                        entity_id=user.id,
                        summary="Account temporarily locked after repeated failed sign-ins",
                        after={"locked_until": lock, "failures": user.failed_login_count},
                    )
                failed = True
            else:
                failed = False
                user.failed_login_count = 0
                user.locked_until = None
                user.last_login_at = now
                if self.infra.passwords.needs_rehash(user.password_hash):
                    user.password_hash = await self.infra.passwords.hash(password)
                roles = sorted(
                    (
                        await uow.session.scalars(select(UserRole.role).where(UserRole.user_id == user.id))
                    ).all()
                )
                token = await self.sessions.create(uow, user, ip=ip, user_agent=user_agent)
                if user.kind == "staff":
                    await record(
                        uow,
                        Actor("user", user.id, user.full_name),
                        "auth.login",
                        entity_type="user",
                        entity_id=user.id,
                    )
        if failed:
            await self.infra.limiter.consume(login_failure_bucket(self.settings), f"{ip}")
            LOGINS.labels("tenant", "failed").inc()
            raise InvalidCredentials(LOCKED_HINT)
        LOGINS.labels("tenant", "success").inc()
        return LoginResult(token=token, user_id=user.id, user_kind=user.kind, roles=list(roles))

    async def logout(self, uow: UnitOfWork, principal: Principal) -> None:
        await self.sessions.revoke(uow, principal.session_hash)

    async def logout_everywhere(self, uow: UnitOfWork, principal: Principal) -> int:
        return await self.sessions.revoke_all_for_user(uow, principal.user_id)

    async def reauthenticate(self, uow: UnitOfWork, principal: Principal, password: str) -> None:
        user = (await uow.session.scalars(select(User).where(User.id == principal.user_id))).one()
        if not await self.infra.passwords.verify(user.password_hash, password):
            raise InvalidCredentials("That password isn't right.")
        await self.sessions.mark_reauthenticated(uow, principal.session_hash)

    def require_recent_auth(self, principal: Principal) -> None:
        """Sensitive actions (publish, withdraw, role changes) need a password confirmation within the
        re-auth window (docs/10 §2)."""
        window = timedelta(minutes=self.settings.reauth_window_minutes)
        if principal.reauthenticated_at is None or utcnow() - principal.reauthenticated_at > window:
            raise ReauthRequired()

    async def change_password(
        self, uow: UnitOfWork, principal: Principal, current: str, new: str, tenant: TenantContext
    ) -> None:
        user = (await uow.session.scalars(select(User).where(User.id == principal.user_id))).one()
        if not await self.infra.passwords.verify(user.password_hash, current):
            raise ValidationFailed("Your current password isn't right.", field="current_password")
        await self._check_password_rules(
            new, staff=user.kind == "staff", context=(user.login_id, user.email or "", tenant.slug)
        )
        user.password_hash = await self.infra.passwords.hash(new)
        user.password_changed_at = utcnow()
        await self.sessions.revoke_all_for_user(uow, user.id, except_hash=principal.session_hash)
        await record(
            uow,
            Actor.from_principal(principal),
            "user.password_changed",
            entity_type="user",
            entity_id=user.id,
        )

    # ---- password reset -------------------------------------------------------------------------
    async def request_password_reset(self, tenant: TenantContext, identifier: str, *, ip: str) -> None:
        await self.infra.limiter.hit(PASSWORD_RESET, f"ip:{ip}")
        normalised = normalise_login_id(identifier)
        await self.infra.limiter.hit(PASSWORD_RESET, f"acct:{tenant.tenant_id}:{normalised}")
        async with self.infra.db.uow(tenant.tenant_id, ip=ip) as uow:
            user = (
                await uow.session.scalars(
                    select(User).where((User.login_id == normalised) | (User.email == normalised.lower()))
                )
            ).first()
            if user is None or user.status != "active" or not user.email:
                return  # identical response either way (no account enumeration)
            token = new_token(32)
            uow.session.add(
                AuthToken(
                    tenant_id=tenant.tenant_id,
                    user_id=user.id,
                    purpose="password_reset",
                    token_hash=hash_token(token),
                    expires_at=utcnow() + RESET_TTL,
                )
            )
            await queue_email(
                uow,
                "password_reset",
                user.email,
                {
                    "institution": tenant.name,
                    "action_url": f"{self.settings.public_origin(tenant.host)}/reset-password?token={token}",
                },
            )

    async def _consume_token(self, uow: UnitOfWork, token: str, purpose: str) -> AuthToken:
        row = (
            await uow.session.scalars(
                select(AuthToken).where(AuthToken.token_hash == hash_token(token)).with_for_update()
            )
        ).one_or_none()
        if row is None or row.purpose != purpose or row.consumed_at is not None or row.expires_at < utcnow():
            raise ValidationFailed("This link is invalid or has expired. Request a new one.", field="token")
        row.consumed_at = utcnow()
        return row

    async def reset_password(self, tenant: TenantContext, token: str, new_password: str) -> None:
        async with self.infra.db.uow(tenant.tenant_id) as uow:
            row = await self._consume_token(uow, token, "password_reset")
            user = (await uow.session.scalars(select(User).where(User.id == row.user_id))).one()
            await self._check_password_rules(
                new_password,
                staff=user.kind == "staff",
                context=(user.login_id, user.email or "", tenant.slug),
            )
            user.password_hash = await self.infra.passwords.hash(new_password)
            user.password_changed_at = utcnow()
            user.failed_login_count = 0
            user.locked_until = None
            await self.sessions.revoke_all_for_user(uow, user.id)
            await record(
                uow,
                Actor("user", user.id, user.full_name),
                "user.password_reset",
                entity_type="user",
                entity_id=user.id,
            )

    # ---- invitations ----------------------------------------------------------------------------
    async def issue_invite(
        self, uow: UnitOfWork, tenant: TenantContext, user: User, role_label: str, inviter: str
    ) -> None:
        await uow.session.execute(
            update(AuthToken)
            .where(
                AuthToken.user_id == user.id, AuthToken.purpose == "invite", AuthToken.consumed_at.is_(None)
            )
            .values(consumed_at=utcnow())
        )
        token = new_token(32)
        uow.session.add(
            AuthToken(
                tenant_id=tenant.tenant_id,
                user_id=user.id,
                purpose="invite",
                token_hash=hash_token(token),
                expires_at=utcnow() + INVITE_TTL,
            )
        )
        assert user.email
        await queue_email(
            uow,
            "staff_invite",
            user.email,
            {
                "institution": tenant.name,
                "inviter": inviter,
                "role_label": role_label,
                "action_url": f"{self.settings.public_origin(tenant.host)}/accept-invite?token={token}",
            },
        )

    async def accept_invite(
        self, tenant: TenantContext, token: str, password: str, *, ip: str, user_agent: str | None
    ) -> LoginResult:
        async with self.infra.db.uow(tenant.tenant_id, ip=ip, user_agent=user_agent) as uow:
            row = await self._consume_token(uow, token, "invite")
            user = (
                await uow.session.scalars(select(User).where(User.id == row.user_id).with_for_update())
            ).one()
            if user.status == "disabled":
                raise ValidationFailed("This invitation is no longer valid.", field="token")
            await self._check_password_rules(password, staff=True, context=(user.login_id, tenant.slug))
            user.password_hash = await self.infra.passwords.hash(password)
            user.password_changed_at = utcnow()
            user.status = "active"
            user.last_login_at = utcnow()
            roles = sorted(
                (await uow.session.scalars(select(UserRole.role).where(UserRole.user_id == user.id))).all()
            )
            session_token = await self.sessions.create(uow, user, ip=ip, user_agent=user_agent)
            await record(
                uow,
                Actor("user", user.id, user.full_name),
                "user.invite_accepted",
                entity_type="user",
                entity_id=user.id,
            )
        return LoginResult(token=session_token, user_id=user.id, user_kind=user.kind, roles=list(roles))

    async def peek_invite(self, tenant: TenantContext, token: str) -> dict[str, str]:
        async with self.infra.db.uow(tenant.tenant_id) as uow:
            row = (
                await uow.session.scalars(select(AuthToken).where(AuthToken.token_hash == hash_token(token)))
            ).one_or_none()
            if (
                row is None
                or row.purpose != "invite"
                or row.consumed_at is not None
                or row.expires_at < utcnow()
            ):
                raise NotFound("This invitation is invalid or has expired.")
            user = (await uow.session.scalars(select(User).where(User.id == row.user_id))).one()
            return {"full_name": user.full_name, "email": user.email or ""}

    # ---- student activation ---------------------------------------------------------------------
    async def activate_student(
        self,
        tenant: TenantContext,
        enrollment_no: str,
        code: str,
        password: str,
        *,
        ip: str,
        user_agent: str | None,
    ) -> LoginResult:
        login_id = normalise_login_id(enrollment_no)
        await self.infra.limiter.hit(ACTIVATION, f"{tenant.tenant_id}:{login_id}")
        await self.infra.limiter.hit(activation_ip_bucket(self.settings), ip)
        token_hash = activation_token_hash(tenant.tenant_id, login_id, code)
        async with self.infra.db.uow(tenant.tenant_id, ip=ip, user_agent=user_agent) as uow:
            row = (
                await uow.session.scalars(
                    select(AuthToken).where(AuthToken.token_hash == token_hash).with_for_update()
                )
            ).one_or_none()
            if (
                row is None
                or row.purpose != "activation"
                or row.consumed_at is not None
                or row.expires_at < utcnow()
            ):
                raise ValidationFailed(
                    "That enrollment number and activation code don't match an account waiting for "
                    "activation. Check the slip from your institution.",
                    field="code",
                )
            user = (
                await uow.session.scalars(select(User).where(User.id == row.user_id).with_for_update())
            ).one()
            if user.login_id != login_id or user.status == "disabled":
                raise ValidationFailed("This activation code isn't valid.", field="code")
            await self._check_password_rules(password, staff=False, context=(login_id, tenant.slug))
            row.consumed_at = utcnow()
            user.password_hash = await self.infra.passwords.hash(password)
            user.password_changed_at = utcnow()
            user.status = "active"
            user.last_login_at = utcnow()
            session_token = await self.sessions.create(uow, user, ip=ip, user_agent=user_agent)
            await record(
                uow,
                Actor("user", user.id, user.full_name),
                "student.activated",
                entity_type="user",
                entity_id=user.id,
            )
        return LoginResult(token=session_token, user_id=user.id, user_kind="student", roles=["student"])

    # ---- platform realm -------------------------------------------------------------------------
    async def platform_login(
        self, email: str, password: str, totp_code: str, *, ip: str, user_agent: str | None
    ) -> str:
        await self.infra.limiter.hit(PLATFORM_LOGIN_PER_IP, ip)
        now = utcnow()
        async with self.infra.db.platform_uow(ip=ip) as uow:
            user = (
                await uow.session.scalars(
                    select(PlatformUser).where(PlatformUser.email == email.strip().lower()).with_for_update()
                )
            ).one_or_none()
            if user is None or user.status != "active" or (user.locked_until and user.locked_until > now):
                await self.infra.passwords.burn(password)
                LOGINS.labels("platform", "rejected").inc()
                raise InvalidCredentials()
            password_ok = await self.infra.passwords.verify(user.password_hash, password)
            totp_ok = False
            if password_ok and user.totp_secret_enc:
                secret = self.infra.cipher.decrypt(user.totp_secret_enc)
                totp_ok = pyotp.TOTP(secret).verify(totp_code.strip().replace(" ", ""), valid_window=1)
            if not (password_ok and totp_ok):
                user.failed_login_count += 1
                user.locked_until = self._lockout_until(user.failed_login_count, now)
                failed = True
            else:
                failed = False
                user.failed_login_count = 0
                user.locked_until = None
                user.last_login_at = now
                if user.totp_confirmed_at is None:
                    user.totp_confirmed_at = now
                token = await self.sessions.create_platform(uow, user, ip=ip, user_agent=user_agent)
                await record_platform(uow, Actor("platform_user", user.id, user.full_name), "platform.login")
        if failed:
            LOGINS.labels("platform", "failed").inc()
            raise InvalidCredentials()
        LOGINS.labels("platform", "success").inc()
        return token


async def assert_unique_login(uow: UnitOfWork, login_id: str, email: str | None) -> None:
    clash = (
        await uow.session.scalars(
            select(User.id).where((User.login_id == login_id) | ((User.email == email) if email else False))
        )
    ).first()
    if clash is not None:
        raise Conflict("An account with this email or ID already exists.", field="email")
