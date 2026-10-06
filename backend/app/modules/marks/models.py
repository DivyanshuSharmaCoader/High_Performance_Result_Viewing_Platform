"""Marks (docs/07 §2.6): one row per student × paper.

The row names the cohort the student sits the paper with; a composite FK to ``exam_cohorts`` keeps that
honest, and the FK to ``exam_papers`` is RESTRICT, so a paper with marks can never silently disappear.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, tenant_fk

ATTENDANCE = ("present", "absent", "exempt", "malpractice", "withheld")


class MarkEntry(TenantScoped, Base):
    __tablename__ = "mark_entries"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "exam_paper_id", "student_id"),
        ForeignKeyConstraint(
            ["tenant_id", "exam_paper_id", "exam_id"],
            ["exam_papers.tenant_id", "exam_papers.id", "exam_papers.exam_id"],
            ondelete="RESTRICT",
            name="fk_mark_entries__paper",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "exam_id", "cohort_id"],
            ["exam_cohorts.tenant_id", "exam_cohorts.exam_id", "exam_cohorts.cohort_id"],
            ondelete="RESTRICT",
            name="fk_mark_entries__exam_cohort",
        ),
        tenant_fk("student_id", "students"),
        CheckConstraint(f"attendance IN {ATTENDANCE}", name="attendance"),
        CheckConstraint("total IS NULL OR total >= 0", name="total"),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_mark_entries__tenant_exam_cohort", "tenant_id", "exam_id", "cohort_id"),
        Index("ix_mark_entries__tenant_student", "tenant_id", "student_id"),
    )

    exam_id: Mapped[uuid.UUID]
    exam_paper_id: Mapped[uuid.UUID]
    cohort_id: Mapped[uuid.UUID]
    student_id: Mapped[uuid.UUID]
    components: Mapped[dict[str, Any]] = mapped_column(
        JSONB
    )  # {"INT": "35", "EXT": "50.5"} — decimal strings
    total: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))  # set only when every component is present
    attendance: Mapped[str] = mapped_column(String(12), server_default="present")
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    source: Mapped[str] = mapped_column(String(64), server_default="grid")  # grid | import:<job id>
    updated_by: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
