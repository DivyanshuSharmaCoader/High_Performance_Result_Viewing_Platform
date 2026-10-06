"""Academic structure (docs/07 §2.4): one generic model that fits schools, colleges and coaching
(docs/03 W3) — session → terms; department → program → cohort (per session); course catalogue."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, Timestamps, UUIDPrimaryKey, tenant_fk, tenant_unique_id


class AcademicSession(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "academic_sessions"
    __table_args__ = (
        tenant_unique_id("academic_sessions"),
        Index("uq_academic_sessions__tenant_code", "tenant_id", "code", unique=True),
        Index(
            "uq_academic_sessions__one_current",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        CheckConstraint("starts_on < ends_on", name="dates"),
    )

    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(100))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    archived_at: Mapped[datetime | None]


class Term(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "terms"
    __table_args__ = (
        tenant_unique_id("terms"),
        tenant_fk("session_id", "academic_sessions"),
        Index("uq_terms__tenant_session_code", "tenant_id", "session_id", "code", unique=True),
        CheckConstraint("sequence >= 1", name="sequence"),
        CheckConstraint("starts_on IS NULL OR ends_on IS NULL OR starts_on < ends_on", name="dates"),
    )

    session_id: Mapped[uuid.UUID]
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(100))
    sequence: Mapped[int] = mapped_column(Integer, server_default="1")
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)


class Department(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "departments"
    __table_args__ = (
        tenant_unique_id("departments"),
        Index("uq_departments__tenant_code", "tenant_id", "code", unique=True),
    )

    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(150))
    archived_at: Mapped[datetime | None]


class Program(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "programs"
    __table_args__ = (
        tenant_unique_id("programs"),
        tenant_fk("department_id", "departments"),
        Index("uq_programs__tenant_code", "tenant_id", "code", unique=True),
        CheckConstraint("duration_terms IS NULL OR duration_terms BETWEEN 1 AND 20", name="duration"),
    )

    department_id: Mapped[uuid.UUID | None]
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(150))
    level: Mapped[str | None] = mapped_column(String(60))
    duration_terms: Mapped[int | None] = mapped_column(Integer)
    archived_at: Mapped[datetime | None]


class Cohort(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    """A section/batch/group of a program in one academic session."""

    __tablename__ = "cohorts"
    __table_args__ = (
        tenant_unique_id("cohorts"),
        tenant_fk("program_id", "programs"),
        tenant_fk("session_id", "academic_sessions"),
        Index("uq_cohorts__tenant_session_code", "tenant_id", "session_id", "code", unique=True),
        Index("ix_cohorts__tenant_program", "tenant_id", "program_id"),
    )

    program_id: Mapped[uuid.UUID]
    session_id: Mapped[uuid.UUID]
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(150))
    archived_at: Mapped[datetime | None]


class Course(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    """Subject catalogue entry (e.g. UCS301 Data Structures, 4 credits)."""

    __tablename__ = "courses"
    __table_args__ = (
        tenant_unique_id("courses"),
        tenant_fk("department_id", "departments"),
        Index("uq_courses__tenant_code", "tenant_id", "code", unique=True),
        CheckConstraint("credits IS NULL OR (credits >= 0 AND credits <= 40)", name="credits"),
    )

    department_id: Mapped[uuid.UUID | None]
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    credits: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    archived_at: Mapped[datetime | None]
