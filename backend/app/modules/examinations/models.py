"""Examinations, the cohorts sitting them, papers (course × exam with components), faculty assignments
and per-paper submission state (docs/07 §2.5, state diagrams §1–2).

Consistency the database enforces with composite foreign keys:
* a paper assignment / submission names a cohort that sits *that* exam (FK to ``exam_cohorts``) and a
  paper of *that* exam (FK to ``exam_papers (tenant_id, id, exam_id)``);
* removing a cohort or paper from a draft exam removes its assignments and submissions with it.
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
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    Base,
    TenantScoped,
    Timestamps,
    UUIDPrimaryKey,
    Versioned,
    tenant_fk,
    tenant_unique_id,
)

EXAM_KINDS = ("unit_test", "term", "semester", "supplementary", "other")
EXAM_STATUSES = (
    "draft",
    "marks_entry_open",
    "marks_entry_closed",
    "processed",
    "approved",
    "scheduled",
    "published",
    "correction_draft",
    "withdrawn",
    "archived",
)
SUBMISSION_STATUSES = ("open", "submitted", "returned", "locked")


class Examination(UUIDPrimaryKey, TenantScoped, Versioned, Timestamps, Base):
    __tablename__ = "examinations"
    __table_args__ = (
        tenant_unique_id("examinations"),
        tenant_fk("term_id", "terms"),
        tenant_fk("grading_scheme_id", "grading_schemes"),
        tenant_fk("grading_scheme_version_id", "grading_scheme_versions"),
        CheckConstraint(f"kind IN {EXAM_KINDS}", name="kind"),
        CheckConstraint(f"status IN {EXAM_STATUSES}", name="status"),
        Index(
            "uq_examinations__tenant_term_name", "tenant_id", "term_id", func.lower(text("name")), unique=True
        ),
        Index("ix_examinations__tenant_status", "tenant_id", "status"),
    )

    term_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(20), server_default="term")
    status: Mapped[str] = mapped_column(String(24), server_default="draft")
    grading_scheme_id: Mapped[uuid.UUID]
    grading_scheme_version_id: Mapped[uuid.UUID | None]  # pinned when results are processed
    marks_deadline: Mapped[datetime | None]
    scheduled_publish_at: Mapped[datetime | None]
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None]


class ExamCohort(TenantScoped, Base):
    __tablename__ = "exam_cohorts"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "exam_id", "cohort_id"),
        tenant_fk("exam_id", "examinations", ondelete="CASCADE"),
        tenant_fk("cohort_id", "cohorts"),
        Index("ix_exam_cohorts__tenant_cohort", "tenant_id", "cohort_id"),
    )

    exam_id: Mapped[uuid.UUID]
    cohort_id: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ExamPaper(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "exam_papers"
    __table_args__ = (
        tenant_unique_id("exam_papers"),
        UniqueConstraint("tenant_id", "id", "exam_id", name="uq_exam_papers__tenant_id_id_exam"),
        tenant_fk("exam_id", "examinations", ondelete="CASCADE"),
        tenant_fk("course_id", "courses"),
        Index("uq_exam_papers__tenant_exam_course", "tenant_id", "exam_id", "course_id", unique=True),
        CheckConstraint("max_total > 0", name="max_total"),
        CheckConstraint(
            "pass_total IS NULL OR (pass_total >= 0 AND pass_total <= max_total)", name="pass_total"
        ),
        CheckConstraint("credits IS NULL OR (credits >= 0 AND credits <= 40)", name="credits"),
    )

    exam_id: Mapped[uuid.UUID]
    course_id: Mapped[uuid.UUID]
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    components: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # validated by PaperComponents
    max_total: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    pass_total: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    credits: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 1)
    )  # copied from the course: history stays stable


class PaperAssignment(TenantScoped, Base):
    """Faculty allowed to enter marks for a paper in one cohort."""

    __tablename__ = "paper_assignments"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "exam_paper_id", "cohort_id", "user_id"),
        ForeignKeyConstraint(
            ["tenant_id", "exam_paper_id", "exam_id"],
            ["exam_papers.tenant_id", "exam_papers.id", "exam_papers.exam_id"],
            ondelete="CASCADE",
            name="fk_paper_assignments__paper",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "exam_id", "cohort_id"],
            ["exam_cohorts.tenant_id", "exam_cohorts.exam_id", "exam_cohorts.cohort_id"],
            ondelete="CASCADE",
            name="fk_paper_assignments__exam_cohort",
        ),
        tenant_fk("user_id", "users"),
        Index("ix_paper_assignments__tenant_user", "tenant_id", "user_id"),
    )

    exam_id: Mapped[uuid.UUID]
    exam_paper_id: Mapped[uuid.UUID]
    cohort_id: Mapped[uuid.UUID]
    user_id: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PaperSubmission(TenantScoped, Base):
    """Marks-entry workflow state for one paper in one cohort (state diagram §2)."""

    __tablename__ = "paper_submissions"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "exam_paper_id", "cohort_id"),
        ForeignKeyConstraint(
            ["tenant_id", "exam_paper_id", "exam_id"],
            ["exam_papers.tenant_id", "exam_papers.id", "exam_papers.exam_id"],
            ondelete="CASCADE",
            name="fk_paper_submissions__paper",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "exam_id", "cohort_id"],
            ["exam_cohorts.tenant_id", "exam_cohorts.exam_id", "exam_cohorts.cohort_id"],
            ondelete="CASCADE",
            name="fk_paper_submissions__exam_cohort",
        ),
        CheckConstraint(f"status IN {SUBMISSION_STATUSES}", name="status"),
        Index("ix_paper_submissions__tenant_exam_status", "tenant_id", "exam_id", "status"),
    )

    exam_id: Mapped[uuid.UUID]
    exam_paper_id: Mapped[uuid.UUID]
    cohort_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(12), server_default="open")
    submitted_by: Mapped[uuid.UUID | None]
    submitted_at: Mapped[datetime | None]
    returned_by: Mapped[uuid.UUID | None]
    returned_at: Mapped[datetime | None]
    return_reason: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
