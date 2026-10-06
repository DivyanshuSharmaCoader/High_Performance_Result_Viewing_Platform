from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, Timestamps, UUIDPrimaryKey, Versioned

TENANT_TYPES = ("school", "college", "university", "coaching", "other")
TENANT_STATUSES = ("active", "suspended", "closing", "closed")


class Tenant(UUIDPrimaryKey, Timestamps, Base):
    """The institution. Global table; RLS lets the app role see only ``id = app.tenant_id``."""

    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(f"type IN {TENANT_TYPES}", name="type"),
        CheckConstraint(f"status IN {TENANT_STATUSES}", name="status"),
        CheckConstraint(r"slug ~ '^[a-z0-9](-?[a-z0-9]){2,30}$'", name="slug_format"),
    )

    slug: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default="active")
    timezone: Mapped[str] = mapped_column(String(64), server_default="Asia/Kolkata")
    status_reason: Mapped[str | None] = mapped_column(Text)
    config_version: Mapped[int] = mapped_column(Integer, server_default="1")


class TenantDomain(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "tenant_domains"
    __table_args__ = (
        CheckConstraint("kind IN ('custom')", name="kind"),
        CheckConstraint("status IN ('pending','verified','failed')", name="status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    domain: Mapped[str] = mapped_column(String(253), unique=True)
    kind: Mapped[str] = mapped_column(String(20), server_default="custom")
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    verification_token: Mapped[str] = mapped_column(String(64))
    verified_at: Mapped[datetime | None]


DEFAULT_SPECIAL_CODES: dict[str, str] = {
    "AB": "absent",
    "EX": "exempt",
    "MP": "malpractice",
    "WH": "withheld",
}


class TenantSettings(TenantScoped, Versioned, Timestamps, Base):
    """Typed per-tenant settings (docs/07 §2.2) — not a free-form bag."""

    __tablename__ = "tenant_settings"
    __table_args__ = (
        CheckConstraint("approval_mode IN ('single','maker_checker')", name="approval_mode"),
        CheckConstraint("student_activation_mode IN ('code','email')", name="activation_mode"),
        CheckConstraint(
            "verification_disclosure IN ('masked','masked_plus_challenge')", name="verification_disclosure"
        ),
        CheckConstraint("student_stats IN ('none','class_average','full')", name="student_stats"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), primary_key=True
    )
    official_name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    affiliation: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    approval_mode: Mapped[str] = mapped_column(String(20), server_default="single")
    student_activation_mode: Mapped[str] = mapped_column(String(20), server_default="code")
    verification_disclosure: Mapped[str] = mapped_column(String(32), server_default="masked")
    student_stats: Mapped[str] = mapped_column(String(20), server_default="class_average")
    locale: Mapped[str] = mapped_column(String(10), server_default="en-IN")
    publish_notify_email: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    special_codes: Mapped[dict[str, Any]] = mapped_column(
        server_default=text("""'{"AB":"absent","EX":"exempt","MP":"malpractice","WH":"withheld"}'::jsonb""")
    )
    onboarding_dismissed_at: Mapped[datetime | None]
