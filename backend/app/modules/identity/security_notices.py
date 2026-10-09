"""Security notices (ASVS 2.2.3): the person hears about security-relevant changes to their own account
by email, whoever made them. A password changed or reset, two-step sign-in turned on or off or reset by
an administrator, new recovery codes, a recovery code used to sign in. They can't be turned off, carry
no secret, and link to the account page. Sent in the change's own transaction, so a change that rolls
back sends nothing."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.modules.identity.models import User
from app.modules.notifications.emails import queue_email


async def notify(infra: Infra, uow: UnitOfWork, user: User, what: str) -> None:
    if not user.email:
        return  # students without an email address: the audit log still records it
    tenant = (
        await uow.session.execute(
            text("SELECT slug, name, timezone FROM tenants WHERE id = :t"), {"t": user.tenant_id}
        )
    ).one()
    local = utcnow().astimezone(ZoneInfo(tenant.timezone))
    page = "/me/account" if user.kind == "student" else "/account"
    await queue_email(
        uow,
        "security_notice",
        user.email,
        {
            "institution": tenant.name,
            "what": what,
            "when": f"{local.day} {local:%B %Y at %H:%M} ({tenant.timezone})",
            "action_url": f"{infra.settings.tenant_origin(tenant.slug)}{page}",
        },
    )
