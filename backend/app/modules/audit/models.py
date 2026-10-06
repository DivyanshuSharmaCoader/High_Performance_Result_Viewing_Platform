from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Index, PrimaryKeyConstraint, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.core.models import Base, TenantScoped

ACTOR_TYPES = ("user", "platform_user", "system", "api_key")


class AuditLog(TenantScoped, Base):
    """Append-only audit trail, range-partitioned by month (docs/10 §9).

    The app role has INSERT + SELECT only. Partitions are created by migration and the maintenance job.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        PrimaryKeyConstraint("occurred_at", "id"),
        CheckConstraint(f"actor_type IN {ACTOR_TYPES}", name="actor_type"),
        Index("ix_audit_logs__tenant_id_occurred_at", "tenant_id", "occurred_at"),
        Index("ix_audit_logs__tenant_id_entity", "tenant_id", "entity_type", "entity_id"),
        {"postgresql_partition_by": "RANGE (occurred_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid7)
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[uuid.UUID | None]
    actor_label: Mapped[str | None] = mapped_column(String(200))
    impersonated_by: Mapped[uuid.UUID | None]
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class PlatformAuditLog(Base):
    """Actions by ScoreCode staff (platform realm). Not tenant-scoped; optional target tenant."""

    __tablename__ = "platform_audit_logs"
    __table_args__ = (
        Index("ix_platform_audit_logs__occurred_at", "occurred_at"),
        Index("ix_platform_audit_logs__target_tenant_id", "target_tenant_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    platform_user_id: Mapped[uuid.UUID | None]
    actor_label: Mapped[str | None] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(64))
    target_tenant_id: Mapped[uuid.UUID | None]
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
