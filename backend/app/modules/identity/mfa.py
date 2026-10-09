"""Two-step sign-in for staff (P15.5; ASVS V2.7, V2.8; docs/10 §2).

* **Enrolment** needs a recent password confirmation. The secret is stored encrypted, and the method is
  switched on only once a first code from the app checks out. Ten one-time recovery codes are then
  shown once and stored as SHA-256 hashes.
* **Verification** accepts the current 30-second code, or the one either side for clock drift. A code is
  accepted **once**: the last used time step is stored, so a code seen over someone's shoulder can't be
  replayed. A recovery code works once and is struck off.
* An owner or administrator can reset another staff member's two-step sign-in (a lost phone), with
  re-authentication and an audit entry. Nobody can reset their own; they turn it off with a code instead.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pyotp
import segno
from sqlalchemy import select

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import InvalidState, NotFound, PermissionDenied, ValidationFailed
from app.core.http import Principal
from app.modules.audit.service import Actor, record
from app.modules.identity.models import User, UserRole
from app.modules.identity.security_notices import notify as security_notice

RECOVERY_CODES = 10
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford: nothing to confuse when read from paper


def _normalise(code: str) -> str:
    return "".join(code.split()).replace("-", "").upper()


def _hash(code: str) -> str:
    return hashlib.sha256(_normalise(code).encode()).hexdigest()


def new_recovery_codes() -> list[str]:
    codes = []
    for _ in range(RECOVERY_CODES):
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(10))  # 50 bits each
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


@dataclass(frozen=True)
class Enrolment:
    secret: str
    uri: str
    qr_svg: str  # data: URI, so the browser needs no QR library


class MfaService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    # ---- verification ---------------------------------------------------------------------------
    def verify(self, user: User, code: str, now: datetime | None = None) -> str | None:
        """``"totp"`` or ``"recovery"`` when ``code`` is good (and marks it used), else ``None``."""
        if not user.totp_secret_enc or user.totp_enabled_at is None:
            return None
        cleaned = _normalise(code)
        if cleaned.isdigit() and len(cleaned) == 6:
            totp = pyotp.TOTP(self.infra.cipher.decrypt(user.totp_secret_enc))
            current = int((now or utcnow()).timestamp() // totp.interval)
            for step in (current - 1, current, current + 1):
                if hmac.compare_digest(totp.at(step * totp.interval), cleaned):
                    if user.totp_last_step is not None and step <= user.totp_last_step:
                        return None  # this code (or an older one) was already used
                    user.totp_last_step = step
                    return "totp"
            return None
        digest = _hash(cleaned)
        remaining = list(user.totp_recovery_hashes or [])
        for h in remaining:
            if hmac.compare_digest(h, digest):
                remaining.remove(h)
                user.totp_recovery_hashes = remaining
                return "recovery"
        return None

    # ---- the person's own settings ----------------------------------------------------------------
    @staticmethod
    async def _me(uow: UnitOfWork, principal: Principal) -> User:
        if principal.user_kind != "staff":
            raise PermissionDenied("Two-step sign-in is for staff accounts.")
        return (await uow.session.scalars(select(User).where(User.id == principal.user_id))).one()

    async def status(self, uow: UnitOfWork, principal: Principal) -> dict[str, Any]:
        user = await self._me(uow, principal)
        return {
            "enabled": user.totp_enabled_at is not None,
            "enabled_at": user.totp_enabled_at,
            "recovery_codes_left": len(user.totp_recovery_hashes or []) if user.totp_enabled_at else 0,
        }

    async def begin(self, uow: UnitOfWork, principal: Principal) -> Enrolment:
        from app.modules.identity.service import AuthService

        AuthService(self.infra).require_recent_auth(principal)
        user = await self._me(uow, principal)
        if user.totp_enabled_at is not None:
            raise InvalidState("Two-step sign-in is already on. Turn it off first to move it to a new phone.")
        secret = pyotp.random_base32()
        user.totp_secret_enc = self.infra.cipher.encrypt(secret)
        user.totp_last_step = None
        label = user.email or user.login_id
        uri = pyotp.TOTP(secret).provisioning_uri(name=label, issuer_name=self.infra.settings.totp_issuer)
        qr = segno.make_qr(uri, error="m").svg_data_uri(scale=5, border=2, dark="#111111")
        return Enrolment(secret=secret, uri=uri, qr_svg=str(qr))

    async def enable(self, uow: UnitOfWork, principal: Principal, code: str) -> list[str]:
        user = await self._me(uow, principal)
        if user.totp_enabled_at is not None:
            raise InvalidState("Two-step sign-in is already on.")
        if not user.totp_secret_enc:
            raise InvalidState("Start setting up two-step sign-in first.")
        user.totp_enabled_at = utcnow()  # verify() only accepts codes for an enabled method
        if self.verify(user, code) != "totp":
            user.totp_enabled_at = None
            raise ValidationFailed(
                "That code didn't match. Check your phone's time is set automatically.", field="code"
            )
        codes = new_recovery_codes()
        user.totp_recovery_hashes = [_hash(c) for c in codes]
        await self._audit(uow, principal, "user.mfa_enabled", "Two-step sign-in turned on")
        await security_notice(self.infra, uow, user, "Two-step sign-in was turned on")
        return codes

    async def disable(self, uow: UnitOfWork, principal: Principal, code: str) -> None:
        user = await self._me(uow, principal)
        if user.totp_enabled_at is None:
            raise InvalidState("Two-step sign-in isn't on.")
        if self.verify(user, code) is None:
            raise ValidationFailed("That code didn't match.", field="code")
        self._clear(user)
        await self._audit(uow, principal, "user.mfa_disabled", "Two-step sign-in turned off")
        await security_notice(self.infra, uow, user, "Two-step sign-in was turned off")

    async def regenerate(self, uow: UnitOfWork, principal: Principal, code: str) -> list[str]:
        user = await self._me(uow, principal)
        if user.totp_enabled_at is None:
            raise InvalidState("Two-step sign-in isn't on.")
        if self.verify(user, code) != "totp":
            raise ValidationFailed("Enter a code from your authenticator app.", field="code")
        codes = new_recovery_codes()
        user.totp_recovery_hashes = [_hash(c) for c in codes]
        await self._audit(uow, principal, "user.mfa_recovery_regenerated", "New recovery codes issued")
        await security_notice(
            self.infra, uow, user, "New recovery codes were created, and the old ones no longer work"
        )
        return codes

    # ---- for someone else -------------------------------------------------------------------------
    async def reset_for(self, uow: UnitOfWork, principal: Principal, user_id: Any) -> None:
        from app.modules.identity.service import AuthService

        AuthService(self.infra).require_recent_auth(principal)
        if user_id == principal.user_id:
            raise InvalidState("Turn off your own two-step sign-in from your account page.")
        user = (
            await uow.session.scalars(select(User).where(User.id == user_id, User.kind == "staff"))
        ).one_or_none()
        if user is None:
            raise NotFound("Staff member not found")
        if user.totp_enabled_at is None:
            raise InvalidState("This person doesn't use two-step sign-in.")
        roles = set(
            (await uow.session.scalars(select(UserRole.role).where(UserRole.user_id == user.id))).all()
        )
        if "institution_owner" in roles:
            # Weakening the owner's sign-in is not something an administrator may do.
            raise PermissionDenied("Only ScoreCode support can reset the owner's two-step sign-in.")
        self._clear(user)
        await record(
            uow,
            Actor.from_principal(principal),
            "user.mfa_reset",
            entity_type="user",
            entity_id=user.id,
            summary=f"Two-step sign-in reset for {user.full_name}",
        )
        await security_notice(self.infra, uow, user, f"{principal.display_name} reset your two-step sign-in")

    @staticmethod
    def _clear(user: User) -> None:
        user.totp_secret_enc = None
        user.totp_enabled_at = None
        user.totp_last_step = None
        user.totp_recovery_hashes = None

    @staticmethod
    async def _audit(uow: UnitOfWork, principal: Principal, action: str, summary: str) -> None:
        await record(
            uow,
            Actor.from_principal(principal),
            action,
            entity_type="user",
            entity_id=principal.user_id,
            summary=summary,
        )
