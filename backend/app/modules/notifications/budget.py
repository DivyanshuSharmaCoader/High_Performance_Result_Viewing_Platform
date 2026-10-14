"""The email provider's daily cap, shared by every process (migration 0022; docs/16 §5).

``take`` asks for one send before it happens. ``None``: go ahead. A time: the budget is spent until then,
so the caller waits (a deferred job), instead of failing against the provider and retrying into the same
wall. Result notices are ``bulk`` and stop ``mail_daily_reserve`` short of the limit; password resets,
invitations and security notices may use that reserve.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.core.container import Infra
from app.core.metrics import EMAILS


async def take(infra: Infra, *, bulk: bool) -> datetime | None:
    limit = infra.settings.mail_daily_limit
    if limit <= 0:
        return None
    async with infra.db.uow() as uow:
        until: datetime | None = (
            await uow.session.execute(
                text("SELECT ops_mail_take(:limit, :reserve, :bulk)"),
                {"limit": limit, "reserve": infra.settings.mail_daily_reserve, "bulk": bulk},
            )
        ).scalar_one()
    if until is not None:
        EMAILS.labels("deferred").inc()
    return until
