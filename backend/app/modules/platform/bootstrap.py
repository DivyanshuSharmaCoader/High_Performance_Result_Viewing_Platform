"""Operator bootstrap: create ScoreCode staff accounts with mandatory TOTP enrolment."""

from __future__ import annotations

from dataclasses import dataclass

import pyotp
from sqlalchemy import select

from app.core.config import get_settings
from app.core.container import Infra
from app.core.errors import Conflict, ValidationFailed
from app.core.security import password_problems
from app.modules.audit.service import Actor, record_platform
from app.modules.identity.models import PlatformUser


@dataclass(frozen=True)
class CreatedPlatformUser:
    id: str
    email: str
    totp_secret: str
    provisioning_uri: str


async def create_platform_user(
    infra: Infra,
    email: str,
    full_name: str,
    password: str,
    role: str = "platform_admin",
    *,
    totp_secret: str | None = None,
) -> CreatedPlatformUser:
    email = email.strip().lower()
    problems = password_problems(password, min_length=12, context=(email,))
    if problems:
        raise ValidationFailed(" ".join(problems), field="password")
    secret = totp_secret or pyotp.random_base32()
    try:
        pyotp.TOTP(secret).now()  # rejects secrets that aren't valid base32 before they're stored
    except ValueError as exc:
        raise ValidationFailed("TOTP secret must be base32 (A–Z, 2–7).", field="totp_secret") from exc
    async with infra.db.platform_uow() as uow:
        exists = (
            await uow.session.scalars(select(PlatformUser.id).where(PlatformUser.email == email))
        ).first()
        if exists:
            raise Conflict("A platform user with this email already exists.")
        user = PlatformUser(
            email=email,
            full_name=full_name.strip(),
            password_hash=await infra.passwords.hash(password),
            totp_secret_enc=infra.cipher.encrypt(secret),
            role=role,
        )
        uow.session.add(user)
        await uow.flush()
        await record_platform(
            uow,
            Actor.system("cli"),
            "platform_user.created",
            entity_type="platform_user",
            entity_id=user.id,
            after={"email": email, "role": role},
        )
    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=infra.settings.totp_issuer)
    return CreatedPlatformUser(id=str(user.id), email=email, totp_secret=secret, provisioning_uri=uri)


async def create_platform_user_cli(email: str, name: str, password: str, role: str) -> None:
    settings = get_settings()
    infra = Infra.build(settings, app_name="scorecode-cli")
    try:
        created = await create_platform_user(infra, email, name, password, role)
    finally:
        await infra.close()
    print(f"Created platform user {created.email} ({role}).")
    print("Enrol this TOTP secret in an authenticator app now — it is not shown again:")
    print(f"  secret: {created.totp_secret}")
    print(f"  uri:    {created.provisioning_uri}")
