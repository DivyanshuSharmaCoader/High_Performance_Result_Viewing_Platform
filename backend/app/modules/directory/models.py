"""Directory: students, their cohort memberships, and staff profiles (docs/07 §2.4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    func,
    text,
)
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

STUDENT_STATUSES = ("active", "graduated", "withdrawn", "archived")


class Student(UUIDPrimaryKey, TenantScoped, Versioned, Timestamps, Base):
    __tablename__ = "students"
    __table_args__ = (
        tenant_unique_id("students"),
        tenant_fk("user_id", "users"),
        CheckConstraint(f"status IN {STUDENT_STATUSES}", name="status"),
        CheckConstraint(
            "admission_year IS NULL OR admission_year BETWEEN 1950 AND 2100", name="admission_year"
        ),
        Index("uq_students__tenant_enrollment", "tenant_id", "enrollment_no", unique=True),
        Index(
            "uq_students__tenant_user",
            "tenant_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index("ix_students__tenant_status", "tenant_id", "status"),
        # Plus a pg_trgm GIN index on lower(full_name) for admin search, created in migration 0004
        # (expression indexes with operator classes are written by hand there).
    )

    enrollment_no: Mapped[str] = mapped_column(String(40))
    full_name: Mapped[str] = mapped_column(String(200))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(32))
    guardian_name: Mapped[str | None] = mapped_column(String(200))
    admission_year: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    user_id: Mapped[uuid.UUID | None]
    archived_at: Mapped[datetime | None]


class CohortMembership(TenantScoped, Base):
    """Student ∈ cohort. Session and program are copied from the cohort (enforced by a composite FK to
    ``cohorts(tenant_id, id, session_id, program_id)``) so the database can guarantee one cohort per
    program per session for each student."""

    __tablename__ = "cohort_memberships"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "cohort_id", "student_id"),
        ForeignKeyConstraint(
            ["tenant_id", "cohort_id", "session_id", "program_id"],
            ["cohorts.tenant_id", "cohorts.id", "cohorts.session_id", "cohorts.program_id"],
            ondelete="RESTRICT",
            name="fk_cohort_memberships__cohort",
        ),
        tenant_fk("student_id", "students"),
        Index(
            "uq_cohort_memberships__one_per_program_session",
            "tenant_id",
            "student_id",
            "session_id",
            "program_id",
            unique=True,
        ),
        Index("ix_cohort_memberships__tenant_student", "tenant_id", "student_id"),
    )

    cohort_id: Mapped[uuid.UUID]
    student_id: Mapped[uuid.UUID]
    session_id: Mapped[uuid.UUID]
    program_id: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class StaffProfile(TenantScoped, Timestamps, Base):
    __tablename__ = "staff_profiles"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "user_id"),
        tenant_fk("user_id", "users", ondelete="CASCADE"),
        tenant_fk("department_id", "departments"),
    )

    user_id: Mapped[uuid.UUID]
    employee_code: Mapped[str | None] = mapped_column(String(40))
    designation: Mapped[str | None] = mapped_column(String(100))
    department_id: Mapped[uuid.UUID | None]
    phone: Mapped[str | None] = mapped_column(String(32))
