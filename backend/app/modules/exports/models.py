"""A tenant's export of all its data (P18.5): requested by the owner, built by a job, kept 7 days."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, Timestamps, UUIDPrimaryKey, tenant_fk, tenant_unique_id

EXPORT_STATUSES = ("queued", "running", "ready", "failed", "expired")


class DataExport(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "data_exports"
    __table_args__ = (
        tenant_unique_id("data_exports"),
        tenant_fk("file_id", "files"),
        CheckConstraint(f"status IN {EXPORT_STATUSES}", name="status"),
        CheckConstraint("status <> 'ready' OR file_id IS NOT NULL", name="ready_has_file"),
        Index("ix_data_exports__tenant_created", "tenant_id", "created_at"),
    )

    requested_by: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(10), server_default="queued")
    file_id: Mapped[uuid.UUID | None]
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    counts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # rows per file
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]
