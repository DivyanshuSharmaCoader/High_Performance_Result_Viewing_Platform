"""Audit trail: every state-changing service call records an event in the *same* transaction as the
change (docs/10 §9). A rolled-back change therefore never leaves an audit row, and a committed change
always has one."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.db import UnitOfWork
from app.core.http import Principal
from app.modules.audit.models import AuditLog, PlatformAuditLog


@dataclass(frozen=True, slots=True)
class Actor:
    type: str  # user | platform_user | system
    id: uuid.UUID | None
    label: str | None

    @classmethod
    def from_principal(cls, principal: Principal) -> Actor:
        return cls(
            "platform_user" if principal.kind == "platform" else "user",
            principal.user_id,
            principal.display_name,
        )

    @classmethod
    def system(cls, label: str = "system") -> Actor:
        return cls("system", None, label)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Field-level diff: only keys whose values changed."""
    keys = sorted(set(before) | set(after))
    changed = [k for k in keys if before.get(k) != after.get(k)]
    return ({k: before.get(k) for k in changed}, {k: after.get(k) for k in changed})


async def record(
    uow: UnitOfWork,
    actor: Actor,
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
    summary: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    tenant_id = uow.require_tenant()
    uow.session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_type=actor.type,
            actor_id=actor.id,
            actor_label=actor.label,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            summary=summary,
            before=_jsonable(before) if before is not None else None,
            after=_jsonable(after) if after is not None else None,
            reason=reason,
            request_id=uow.meta.get("request_id"),
            ip=uow.meta.get("ip"),
            user_agent=uow.meta.get("user_agent"),
        )
    )


async def record_platform(
    uow: UnitOfWork,
    actor: Actor,
    action: str,
    *,
    target_tenant_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    uow.session.add(
        PlatformAuditLog(
            platform_user_id=actor.id,
            actor_label=actor.label,
            action=action,
            target_tenant_id=target_tenant_id,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            before=_jsonable(before) if before is not None else None,
            after=_jsonable(after) if after is not None else None,
            reason=reason,
            request_id=uow.meta.get("request_id"),
            ip=uow.meta.get("ip"),
        )
    )
