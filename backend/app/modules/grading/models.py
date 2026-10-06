"""Grading schemes and their immutable versions (docs/07 §2.5).

Editing a scheme always creates a new version; a version row is never changed (no UPDATE grant for the
app role, and a trigger refuses UPDATE for everyone). Exams pin the version they were processed with, so
re-processing an old exam gives the same result even after the scheme is edited.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, Timestamps, UUIDPrimaryKey, tenant_fk, tenant_unique_id

STRATEGIES = ("percentage_bands", "credit_gpa", "marks_only")


class GradingScheme(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "grading_schemes"
    __table_args__ = (
        tenant_unique_id("grading_schemes"),
        CheckConstraint(f"strategy IN {STRATEGIES}", name="strategy"),
        Index("uq_grading_schemes__tenant_name", "tenant_id", func.lower(text("name")), unique=True),
    )

    name: Mapped[str] = mapped_column(String(100))
    strategy: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None]


class GradingSchemeVersion(UUIDPrimaryKey, TenantScoped, Base):
    __tablename__ = "grading_scheme_versions"
    __table_args__ = (
        tenant_unique_id("grading_scheme_versions"),
        tenant_fk("scheme_id", "grading_schemes"),
        CheckConstraint("version >= 1", name="version"),
        Index("uq_grading_scheme_versions__scheme_version", "tenant_id", "scheme_id", "version", unique=True),
    )

    scheme_id: Mapped[uuid.UUID]
    version: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
