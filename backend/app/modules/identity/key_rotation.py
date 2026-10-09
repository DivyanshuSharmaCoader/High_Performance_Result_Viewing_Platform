"""Re-encrypt the TOTP secrets after SCORECODE_SECRET_KEY changes (docs/runbooks/security-incident.md).

The field cipher's key is derived from SCORECODE_SECRET_KEY (core/security.py), so a new key would make
every two-step sign-in fail. ``scorecode reencrypt-secrets`` decrypts each stored secret with the old key
and encrypts it with the new one:
- staff in each tenant, in that tenant's own transaction, as the app role, under RLS;
- platform users, as the platform role.

It is safe to run again: a value the new key already decrypts is left alone. A value neither key
decrypts is counted and reported, never overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from sqlalchemy import text

from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.security import FieldCipher


@dataclass
class RotationReport:
    reencrypted: int = 0
    already_new: int = 0
    unreadable: list[str] = field(default_factory=list)  # "users:<id>" / "platform_users:<id>"


def _readable(cipher: FieldCipher, token: str) -> bool:
    try:
        cipher.decrypt(token)
    except (InvalidTag, ValueError):
        return False
    return True


# The two tables that hold encrypted secrets, as literal statements (no SQL is built at run time).
_STATEMENTS = {
    "users": (
        text("SELECT id, totp_secret_enc FROM users WHERE totp_secret_enc IS NOT NULL"),
        text("UPDATE users SET totp_secret_enc = :value WHERE id = :id AND totp_secret_enc = :was"),
    ),
    "platform_users": (
        text("SELECT id, totp_secret_enc FROM platform_users WHERE totp_secret_enc IS NOT NULL"),
        text("UPDATE platform_users SET totp_secret_enc = :value WHERE id = :id AND totp_secret_enc = :was"),
    ),
}


async def _rotate_table(
    uow: UnitOfWork, table: str, old: FieldCipher, new: FieldCipher, report: RotationReport, dry_run: bool
) -> None:
    select_sql, update_sql = _STATEMENTS[table]
    for row in (await uow.session.execute(select_sql)).all():
        if _readable(new, row.totp_secret_enc):
            report.already_new += 1
            continue
        try:
            secret = old.decrypt(row.totp_secret_enc)
        except (InvalidTag, ValueError):
            report.unreadable.append(f"{table}:{row.id}")
            continue
        if not dry_run:
            values = {"value": new.encrypt(secret), "id": row.id, "was": row.totp_secret_enc}
            await uow.session.execute(update_sql, values)
        report.reencrypted += 1


async def reencrypt_secrets(infra: Infra, old_key: str, *, dry_run: bool = False) -> RotationReport:
    old, new = FieldCipher(old_key), infra.cipher
    report = RotationReport()
    async with infra.db.platform_uow() as uow:
        tenant_ids = (await uow.session.scalars(text("SELECT id FROM tenants ORDER BY id"))).all()
        await _rotate_table(uow, "platform_users", old, new, report, dry_run)
    for tenant_id in tenant_ids:
        async with infra.db.uow(tenant_id) as uow:
            await _rotate_table(uow, "users", old, new, report, dry_run)
    return report
