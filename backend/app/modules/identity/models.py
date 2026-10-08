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
    LargeBinary,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, Timestamps, UUIDPrimaryKey, tenant_fk, tenant_unique_id

TENANT_ROLES = ("institution_owner", "institution_admin", "faculty", "student")


class User(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    """Every tenant login (staff and students). Users belong to exactly one tenant (D3)."""

    __tablename__ = "users"
    __table_args__ = (
        tenant_unique_id("users"),
        CheckConstraint("kind IN ('staff','student')", name="kind"),
        CheckConstraint("status IN ('invited','active','disabled')", name="status"),
        Index("uq_users__tenant_id_login_id", "tenant_id", "login_id", unique=True),
        Index(
            "uq_users__tenant_id_email",
            "tenant_id",
            func.lower(text("email")),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(10))
    login_id: Mapped[str] = mapped_column(String(254))  # email for staff, enrollment no. for students
    email: Mapped[str | None] = mapped_column(String(254))
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), server_default="invited")
    last_login_at: Mapped[datetime | None]
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default="0")
    locked_until: Mapped[datetime | None]
    password_changed_at: Mapped[datetime | None]
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)  # set while enrolling, kept once enabled
    totp_enabled_at: Mapped[datetime | None]
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)  # a code works once (ASVS V2.8.4)
    totp_recovery_hashes: Mapped[list[Any] | None] = mapped_column(JSONB)  # SHA-256 of unused recovery codes
    # Non-essential email (e.g. "results are published"). Account email (resets, invites) always goes.
    notify_email: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class UserRole(TenantScoped, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "user_id", "role"),
        tenant_fk("user_id", "users", ondelete="CASCADE"),
        CheckConstraint(f"role IN {TENANT_ROLES}", name="role"),
        Index("ix_user_roles__tenant_id_role", "tenant_id", "role"),
    )

    user_id: Mapped[uuid.UUID]
    role: Mapped[str] = mapped_column(String(32))
    granted_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Session(TenantScoped, Base):
    """Server-side session. ``id`` is SHA-256 of the cookie token; the token itself is never stored."""

    __tablename__ = "sessions"
    __table_args__ = (
        tenant_fk("user_id", "users", ondelete="CASCADE"),
        Index("ix_sessions__tenant_id_user_id", "tenant_id", "user_id"),
        Index("ix_sessions__expires_at", "expires_at"),
    )

    id: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    user_id: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    absolute_expires_at: Mapped[datetime]
    reauthenticated_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


AUTH_TOKEN_PURPOSES = ("invite", "password_reset", "activation", "email_verification", "signin_handoff")


class AuthToken(UUIDPrimaryKey, TenantScoped, Base):
    """One-time tokens: invites, password resets, student activation codes (hashed)."""

    __tablename__ = "auth_tokens"
    __table_args__ = (
        tenant_fk("user_id", "users", ondelete="CASCADE"),
        CheckConstraint(f"purpose IN {AUTH_TOKEN_PURPOSES}", name="purpose"),
        Index("uq_auth_tokens__token_hash", "token_hash", unique=True),
        Index("ix_auth_tokens__tenant_id_user_id_purpose", "tenant_id", "user_id", "purpose"),
    )

    user_id: Mapped[uuid.UUID]
    purpose: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_by: Mapped[uuid.UUID | None]


class PlatformUser(UUIDPrimaryKey, Timestamps, Base):
    """ScoreCode staff. Separate realm; authenticate only on the platform host, TOTP mandatory."""

    __tablename__ = "platform_users"
    __table_args__ = (
        CheckConstraint("role IN ('platform_admin','support','readonly')", name="role"),
        CheckConstraint("status IN ('active','disabled')", name="status"),
        Index("uq_platform_users__email", func.lower(text("email")), unique=True),
    )

    email: Mapped[str] = mapped_column(String(254))
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text)
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    totp_confirmed_at: Mapped[datetime | None]
    role: Mapped[str] = mapped_column(String(20), server_default="platform_admin")
    status: Mapped[str] = mapped_column(String(10), server_default="active")
    last_login_at: Mapped[datetime | None]
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default="0")
    locked_until: Mapped[datetime | None]


class PlatformSession(Base):
    __tablename__ = "platform_sessions"
    __table_args__ = (Index("ix_platform_sessions__platform_user_id", "platform_user_id"),)

    id: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    platform_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"))
    totp_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class SignupRequest(UUIDPrimaryKey, Base):
    """Pending self-serve sign-up. The tenant is created only after email verification (docs/03 W1)."""

    __tablename__ = "signup_requests"
    __table_args__ = (
        Index("uq_signup_requests__token_hash", "token_hash", unique=True),
        Index("ix_signup_requests__slug", "slug"),
    )

    email: Mapped[str] = mapped_column(String(254))
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    institution_name: Mapped[str] = mapped_column(String(200))
    institution_type: Mapped[str] = mapped_column(String(20))
    slug: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]
    tenant_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ip: Mapped[str | None] = mapped_column(String(64))
