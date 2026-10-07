"""Computed results (docs/07 §2.7, state diagrams §3).

A *run* is one processing of an exam: revision n, the grading scheme version it was pinned to, a hash of
every input (marks, papers, roster, scheme) and a hash of every output. Its rows in
``student_exam_results`` / ``student_paper_results`` are written once and never changed (the app role has
no UPDATE or DELETE on them); processing again writes a new revision. Approvals are append-only decisions
that name the run and the content hash they approved.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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

from app.core.models import Base, TenantScoped, Timestamps, UUIDPrimaryKey, tenant_fk, tenant_unique_id

RUN_STATUSES = ("running", "completed", "failed", "stale", "approved", "published")
EXAM_OUTCOMES = ("pass", "fail", "absent", "withheld", "incomplete")
PAPER_OUTCOMES = ("pass", "fail", "absent", "exempt", "withheld", "incomplete")
DECISIONS = ("approved", "rejected", "revoked")


class ResultRun(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "result_runs"
    __table_args__ = (
        tenant_unique_id("result_runs"),
        tenant_fk("exam_id", "examinations"),
        tenant_fk("grading_scheme_version_id", "grading_scheme_versions"),
        UniqueConstraint("tenant_id", "exam_id", "revision", name="uq_result_runs__exam_revision"),
        CheckConstraint(f"status IN {RUN_STATUSES}", name="status"),
        CheckConstraint("revision >= 1", name="revision"),
        # At most one run in progress per exam: a second "process" waits for the first.
        Index(
            "uq_result_runs__one_running",
            "tenant_id",
            "exam_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    exam_id: Mapped[uuid.UUID]
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), server_default="running")
    grading_scheme_version_id: Mapped[uuid.UUID]
    input_hash: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    started_by: Mapped[uuid.UUID | None]
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_detail: Mapped[str | None] = mapped_column(Text)
    # Processing despite unsubmitted papers needs a reason; the papers are listed for the audit trail.
    override: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    students: Mapped[int] = mapped_column(Integer, server_default="0")
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    anomalies: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))


class StudentExamResult(TenantScoped, Base):
    __tablename__ = "student_exam_results"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "result_run_id", "student_id"),
        tenant_fk("result_run_id", "result_runs"),
        tenant_fk("student_id", "students"),
        tenant_fk("cohort_id", "cohorts"),
        CheckConstraint(f"outcome IN {EXAM_OUTCOMES}", name="outcome"),
        CheckConstraint("rank IS NULL OR rank >= 1", name="rank"),
        Index("ix_student_exam_results__tenant_student", "tenant_id", "student_id"),
    )

    result_run_id: Mapped[uuid.UUID]
    student_id: Mapped[uuid.UUID]
    cohort_id: Mapped[uuid.UUID]
    outcome: Mapped[str] = mapped_column(String(12))
    # Scales match the engine's widest rounding (3 places), so a stored value is exactly the computed one.
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    max_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    grade: Mapped[str | None] = mapped_column(String(12))
    grade_point: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    sgpa: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    credits_attempted: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    credits_earned: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    rank: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))


class StudentPaperResult(TenantScoped, Base):
    __tablename__ = "student_paper_results"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "result_run_id", "student_id", "exam_paper_id"),
        ForeignKeyConstraint(
            ["tenant_id", "result_run_id", "student_id"],
            [
                "student_exam_results.tenant_id",
                "student_exam_results.result_run_id",
                "student_exam_results.student_id",
            ],
            ondelete="RESTRICT",
            name="fk_student_paper_results__exam_result",
        ),
        tenant_fk("exam_paper_id", "exam_papers"),
        CheckConstraint(f"outcome IN {PAPER_OUTCOMES}", name="outcome"),
        Index("ix_student_paper_results__tenant_run_paper", "tenant_id", "result_run_id", "exam_paper_id"),
    )

    result_run_id: Mapped[uuid.UUID]
    student_id: Mapped[uuid.UUID]
    exam_paper_id: Mapped[uuid.UUID]
    outcome: Mapped[str] = mapped_column(String(12))
    passed: Mapped[bool] = mapped_column(Boolean)
    attendance: Mapped[str | None] = mapped_column(String(12))  # None: no marks entered
    components: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    total: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    max_total: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    grade: Mapped[str | None] = mapped_column(String(12))
    grade_point: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    credits: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    failed_components: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    missing_components: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))


class Approval(UUIDPrimaryKey, TenantScoped, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        tenant_fk("result_run_id", "result_runs"),
        tenant_fk("exam_id", "examinations"),
        CheckConstraint(f"decision IN {DECISIONS}", name="decision"),
        Index("ix_approvals__tenant_exam", "tenant_id", "exam_id", "created_at"),
    )

    result_run_id: Mapped[uuid.UUID]
    exam_id: Mapped[uuid.UUID]
    decision: Mapped[str] = mapped_column(String(12))
    decided_by: Mapped[uuid.UUID]
    content_hash: Mapped[str] = mapped_column(String(64))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
