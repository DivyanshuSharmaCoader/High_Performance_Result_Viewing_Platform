"""Closing an institution's account, and erasing its data (P18.14; migration 0021).

No lock-in and no hidden cancellation: the owner asks to close (re-authenticated, with the institution's
address typed out); everything keeps working for 30 days so the data can be exported (P18.5) and the
decision reversed; every administrator is emailed. After those 30 days a ScoreCode staff member approves
the erasure from the platform console, the portal goes offline, and the worker deletes the stored files
and every row (``ops_erase_tenant`` checks both approvals again). Kept: a tombstone of the institution
(no personal data), its subscription records, its trial record (hashed), and the platform audit log.
Encrypted backups expire on their own schedule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, text

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import InvalidState, ValidationFailed
from app.core.http import Principal
from app.core.jobs import maintenance_task
from app.core.logging import get_logger
from app.modules.audit.service import Actor, record, record_platform
from app.modules.identity.models import User, UserRole
from app.modules.identity.security_notices import notify
from app.modules.identity.service import AuthService
from app.modules.tenancy.models import TenantSettings

log = get_logger(__name__)

GRACE = timedelta(days=30)


@dataclass(frozen=True)
class ClosureState:
    requested: bool
    requested_at: datetime | None
    delete_after: datetime | None
    reason: str | None


def _state(s: TenantSettings) -> ClosureState:
    return ClosureState(
        requested=s.closure_requested_at is not None,
        requested_at=s.closure_requested_at,
        delete_after=s.closure_delete_after,
        reason=s.closure_reason,
    )


class ClosureService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    @staticmethod
    async def _settings(uow: UnitOfWork) -> TenantSettings:
        return (await uow.session.scalars(select(TenantSettings).with_for_update())).one()

    async def state(self, uow: UnitOfWork) -> ClosureState:
        return _state((await uow.session.scalars(select(TenantSettings))).one())

    async def _tell_administrators(self, uow: UnitOfWork, what: str) -> None:
        admins = (
            await uow.session.scalars(
                select(User)
                .join(UserRole, UserRole.user_id == User.id)
                .where(UserRole.role.in_(("institution_owner", "institution_admin")), User.status == "active")
                .distinct()
            )
        ).all()
        for user in admins:
            await notify(self.infra, uow, user, what)

    async def request(
        self, uow: UnitOfWork, principal: Principal, *, reason: str, confirm: str, slug: str
    ) -> ClosureState:
        AuthService(self.infra).require_recent_auth(principal)
        if confirm.strip().lower() != slug:
            raise ValidationFailed(
                "Type your institution's address exactly as shown to confirm.", field="confirm"
            )
        if len(reason.strip()) < 3:
            raise ValidationFailed(
                "Tell us why, in a few words; it is recorded in the audit log.", field="reason"
            )
        s = await self._settings(uow)
        if s.closure_requested_at is not None:
            raise InvalidState("Closing this account is already scheduled.")
        now = utcnow()
        s.closure_requested_at, s.closure_requested_by = now, principal.user_id
        s.closure_reason, s.closure_delete_after = reason.strip(), now + GRACE
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "tenant.closure_requested",
            entity_type="tenant",
            entity_id=uow.require_tenant(),
            summary=f"Closing the account was requested; data is erased after {s.closure_delete_after:%d %B %Y}",
            after={"delete_after": s.closure_delete_after.isoformat()},
            reason=reason.strip(),
        )
        await self._tell_administrators(
            uow,
            f"Closing your institution's ScoreCode account was requested. Its data will be erased after "
            f"{s.closure_delete_after:%d %B %Y}. Until then everything works: export your data (Settings → Your "
            "data), or cancel the closure there",
        )
        return _state(s)

    async def cancel(self, uow: UnitOfWork, principal: Principal) -> ClosureState:
        AuthService(self.infra).require_recent_auth(principal)
        s = await self._settings(uow)
        if s.closure_requested_at is None:
            raise InvalidState("No closure is scheduled.")
        before = s.closure_delete_after
        s.closure_requested_at = s.closure_requested_by = s.closure_reason = s.closure_delete_after = None
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "tenant.closure_cancelled",
            entity_type="tenant",
            entity_id=uow.require_tenant(),
            summary="Closing the account was cancelled; nothing will be erased",
            before={"delete_after": before.isoformat() if before else None},
        )
        await self._tell_administrators(uow, "Closing your institution's ScoreCode account was cancelled")
        return _state(s)


@maintenance_task
async def erase_approved_tenants(infra: Infra) -> dict[str, int]:
    """The erasure itself: stored files first (idempotent), then every row in one transaction."""
    erased = 0
    async with infra.db.uow() as uow:
        due = (await uow.session.execute(text("SELECT id, slug FROM ops_tenants_due_for_erasure()"))).all()
    for tenant_id, slug in due:
        files = await infra.storage.delete_prefix(f"tenants/{tenant_id}/")
        async with infra.db.uow() as uow:
            counts = (
                await uow.session.execute(
                    text("SELECT ops_erase_tenant(:t, :s)"), {"t": tenant_id, "s": slug}
                )
            ).scalar_one()
        async with infra.db.platform_uow() as uow:
            await record_platform(
                uow,
                Actor.system("erasure"),
                "tenant.erased",
                target_tenant_id=tenant_id,
                entity_type="tenant",
                entity_id=tenant_id,
                after={"rows": sum(int(v) for v in counts.values()), "tables": counts, "files": files},
            )
        log.info("tenant_erased", tenant_id=str(tenant_id), files=files)
        erased += 1
    return {"tenants_erased": erased}
