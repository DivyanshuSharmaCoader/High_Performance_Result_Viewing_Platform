from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, Timestamps, UUIDPrimaryKey


class Feature(Base):
    """Feature/limit catalogue (global)."""

    __tablename__ = "features"
    __table_args__ = (CheckConstraint("kind IN ('boolean','limit','enum_set')", name="kind"),)

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(Text)
    default_value: Mapped[Any] = mapped_column(JSONB, nullable=True)


class Plan(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, server_default="")
    is_public: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    price_paise_yearly: Mapped[int | None] = mapped_column(BigInteger)
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class PlanFeature(Base):
    __tablename__ = "plan_features"
    __table_args__ = (PrimaryKeyConstraint("plan_id", "feature_key"),)

    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"))
    feature_key: Mapped[str] = mapped_column(ForeignKey("features.key", ondelete="CASCADE"))
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)


SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "cancelled", "expired")


class TenantSubscription(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "tenant_subscriptions"
    __table_args__ = (
        CheckConstraint(f"status IN {SUBSCRIPTION_STATUSES}", name="status"),
        Index(
            "uq_tenant_subscriptions__one_current",
            "tenant_id",
            unique=True,
            postgresql_where=text("status IN ('active','trialing','past_due')"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[datetime] = mapped_column(server_default=func.now())
    period_end: Mapped[datetime | None]
    billing_ref: Mapped[str | None] = mapped_column(String(200))
    changed_by_platform_user: Mapped[uuid.UUID | None]


class TenantFeatureOverride(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "tenant_feature_overrides"
    __table_args__ = (
        Index("uq_tenant_feature_overrides__tenant_feature", "tenant_id", "feature_key", unique=True),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    feature_key: Mapped[str] = mapped_column(ForeignKey("features.key", ondelete="CASCADE"))
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None]
    created_by_platform_user: Mapped[uuid.UUID | None]


USAGE_METRICS = ("active_students", "staff_users", "admin_users", "storage_bytes", "published_exams_year")


class TenantUsageCounter(TenantScoped, Base):
    """Live counters for limited resources; row-locked during limit checks (docs/12 §3)."""

    __tablename__ = "tenant_usage_counters"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "metric"),
        CheckConstraint(f"metric IN {USAGE_METRICS}", name="metric"),
        CheckConstraint("value >= 0", name="non_negative"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    metric: Mapped[str] = mapped_column(String(32))
    value: Mapped[int] = mapped_column(BigInteger, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


TRIAL_STATUSES = ("active", "ended", "converted", "revoked")


class TenantTrial(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    """The one free trial an institution may ever have (docs/12 §6). Unique per tenant, kept forever."""

    __tablename__ = "tenant_trials"
    __table_args__ = (
        Index("uq_tenant_trials__tenant", "tenant_id", unique=True),
        CheckConstraint(f"status IN {TRIAL_STATUSES}", name="status"),
        CheckConstraint("ends_at > started_at", name="window"),
        CheckConstraint("risk_score >= 0", name="risk_score"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(12), server_default="active")
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ends_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    end_reason: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[uuid.UUID | None]  # the owner who started it, or None when granted by the platform
    granted_by_platform_user: Mapped[uuid.UUID | None]
    risk_score: Mapped[int] = mapped_column(Integer, server_default="0")
    flags: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))


TRIAL_SIGNAL_KINDS = ("email", "domain", "device", "tenant", "phone", "name", "subnet")


class TrialClaim(UUIDPrimaryKey, Base):
    """A hashed identity signal of a trial that was taken. Global (across tenants) on purpose and only
    reachable by the platform role: the app role has no grant at all. Hard signals are unique."""

    __tablename__ = "trial_claims"
    __table_args__ = (
        CheckConstraint(f"kind IN {TRIAL_SIGNAL_KINDS}", name="kind"),
        CheckConstraint("length(digest) = 64", name="digest"),
        Index(
            "uq_trial_claims__hard",
            "kind",
            "digest",
            unique=True,
            postgresql_where=text("kind IN ('email', 'domain', 'device', 'tenant')"),
        ),
        Index("ix_trial_claims__lookup", "kind", "digest", "created_at"),
    )

    kind: Mapped[str] = mapped_column(String(12))
    digest: Mapped[str] = mapped_column(String(64))
    trial_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant_trials.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
