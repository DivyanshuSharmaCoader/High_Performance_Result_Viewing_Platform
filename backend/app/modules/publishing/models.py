"""Publication and the student read model (docs/07 §2.7, docs/03 W10).

A *publication* is one released version of an exam's approved results. Publishing writes, in one
transaction, an immutable snapshot per student in ``published_results`` (the JSON the student sees, with its
hash) and an ``exam_statistics`` snapshot. Snapshots are never rewritten: no UPDATE/DELETE grant for the app,
and a trigger refuses it for every role. What students can see is decided only by the publication's status,
and at most one publication per exam is live at a time (partial unique index).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, Timestamps, UUIDPrimaryKey, tenant_fk, tenant_unique_id

PUBLICATION_STATUSES = ("scheduled", "published", "superseded", "withdrawn", "cancelled")
PAYLOAD_SCHEMA = 1  # bump when the snapshot payload changes shape; readers handle every version they meet


class Publication(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "publications"
    __table_args__ = (
        tenant_unique_id("publications"),
        tenant_fk("exam_id", "examinations"),
        tenant_fk("result_run_id", "result_runs"),
        tenant_fk("supersedes_id", "publications"),
        UniqueConstraint("tenant_id", "exam_id", "version", name="uq_publications__exam_version"),
        CheckConstraint(f"status IN {PUBLICATION_STATUSES}", name="status"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("status <> 'scheduled' OR scheduled_at IS NOT NULL", name="scheduled_has_time"),
        CheckConstraint(
            "status NOT IN ('published', 'superseded') OR published_at IS NOT NULL", name="published_has_time"
        ),
        # One live publication per exam, and one waiting to go live.
        Index(
            "uq_publications__one_live",
            "tenant_id",
            "exam_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
        Index(
            "uq_publications__one_scheduled",
            "tenant_id",
            "exam_id",
            unique=True,
            postgresql_where=text("status = 'scheduled'"),
        ),
    )

    exam_id: Mapped[uuid.UUID]
    result_run_id: Mapped[uuid.UUID]
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdraw_reason: Mapped[str | None] = mapped_column(Text)
    supersedes_id: Mapped[uuid.UUID | None]
    created_by: Mapped[uuid.UUID | None]
    students: Mapped[int] = mapped_column(Integer, server_default="0")
    content_hash: Mapped[str] = mapped_column(String(64))  # the approved run's
    payload_schema: Mapped[int] = mapped_column(Integer, server_default=str(PAYLOAD_SCHEMA))


class PublishedResult(TenantScoped, Base):
    __tablename__ = "published_results"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "publication_id", "student_id"),
        tenant_fk("publication_id", "publications"),
        tenant_fk("student_id", "students"),
        tenant_fk("exam_id", "examinations"),
        # "My results" (latest first) is one index range per student, read backwards.
        Index(
            "ix_published_results__student",
            "tenant_id",
            "student_id",
            "created_at",
            postgresql_include=["publication_id", "exam_id"],
        ),
    )

    publication_id: Mapped[uuid.UUID]
    student_id: Mapped[uuid.UUID]
    exam_id: Mapped[uuid.UUID]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExamStatistics(TenantScoped, Base):
    __tablename__ = "exam_statistics"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "publication_id"),
        tenant_fk("publication_id", "publications"),
    )

    publication_id: Mapped[uuid.UUID]
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
