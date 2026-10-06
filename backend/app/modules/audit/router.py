"""Tenant audit-log viewer (P13.4): filter by entity, actor, action and date; keyset pagination."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select

from app.core.http import Principal, UoW, require
from app.core.pagination import Page, clamp_limit, decode_cursor, encode_cursor
from app.modules.audit.models import AuditLog
from app.modules.identity.permissions import P

router = APIRouter(prefix="/api/v1/admin/audit-logs", tags=["audit"])


class AuditEntry(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_type: str
    actor_id: uuid.UUID | None
    actor_label: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    summary: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    ip: str | None


@router.get("")
async def list_audit_logs(
    uow: UoW,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = Query(default=None, max_length=64),
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    _: Principal = require(P.AUDIT_VIEW),
) -> Page[AuditEntry]:
    n = clamp_limit(limit)
    stmt = select(AuditLog).order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).limit(n + 1)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    if since:
        stmt = stmt.where(AuditLog.occurred_at >= since)
    if until:
        stmt = stmt.where(AuditLog.occurred_at < until)
    after = decode_cursor(cursor)
    if after:
        ts, last_id = datetime.fromisoformat(after[0]), uuid.UUID(after[1])
        stmt = stmt.where(
            or_(AuditLog.occurred_at < ts, and_(AuditLog.occurred_at == ts, AuditLog.id < last_id))
        )
    rows = list((await uow.session.scalars(stmt)).all())
    next_cursor = None
    if len(rows) > n:
        rows = rows[:n]
        next_cursor = encode_cursor([rows[-1].occurred_at.isoformat(), str(rows[-1].id)])
    return Page[AuditEntry](
        items=[AuditEntry.model_validate(r, from_attributes=True) for r in rows], next_cursor=next_cursor
    )
