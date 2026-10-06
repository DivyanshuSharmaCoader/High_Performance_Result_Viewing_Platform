"""Tables owned by the shared kernel: the job queue and idempotency keys."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base

JOB_STATUSES = ("queued", "running", "succeeded", "failed", "dead", "cancelled")


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(f"status IN {JOB_STATUSES}", name="status"),
        Index("ix_jobs__claim", "queue", "run_at", postgresql_where=text("status = 'queued'")),
        Index("ix_jobs__running", "tenant_id", "queue", postgresql_where=text("status = 'running'")),
        Index(
            "uq_jobs__dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL AND status IN ('queued','running')"),
        ),
        Index("ix_jobs__tenant_id_created_at", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    queue: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="5")
    run_at: Mapped[datetime] = mapped_column(server_default=func.now())
    locked_by: Mapped[str | None] = mapped_column(String(128))
    locked_until: Mapped[datetime | None]
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_error: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IdempotencyKey(Base):
    """Safe retries of state-changing POSTs (docs/08 §5)."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "key"),
        Index("ix_idempotency_keys__expires_at", "expires_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[Any] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
