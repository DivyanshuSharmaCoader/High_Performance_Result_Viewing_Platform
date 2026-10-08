"""In-app notifications and per-channel deliveries (docs/03 W11, docs/07 §2.8).

* ``notifications`` is the inbox: one row per user and event. ``dedupe_key`` (e.g.
  ``publication:<id>``) makes fan-out idempotent, so a retried job never notifies anyone twice.
* ``notification_deliveries`` tracks each channel (email today) separately: queued → sent, failed or
  skipped (no address, or the person opted out), with attempts and the provider's message id. The
  address itself isn't copied here: it's read from the account when sending, so personal data lives in
  one place.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, UUIDPrimaryKey, tenant_fk, tenant_unique_id

NOTIFICATION_KINDS = ("result_published", "result_revised")
DELIVERY_STATUSES = ("queued", "sent", "failed", "skipped")


class Notification(UUIDPrimaryKey, TenantScoped, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        tenant_unique_id("notifications"),
        tenant_fk("user_id", "users"),
        tenant_fk("publication_id", "publications"),
        CheckConstraint(f"kind IN {NOTIFICATION_KINDS}", name="kind"),
        Index("ix_notifications__inbox", "tenant_id", "user_id", text("created_at DESC")),
        Index(
            "ix_notifications__unread",
            "tenant_id",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
        Index(
            "uq_notifications__once",
            "tenant_id",
            "user_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
        Index(
            "ix_notifications__publication",
            "tenant_id",
            "publication_id",
            postgresql_where=text("publication_id IS NOT NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID]
    publication_id: Mapped[uuid.UUID | None]  # what a results notification is about
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    dedupe_key: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    read_at: Mapped[datetime | None]


class NotificationDelivery(UUIDPrimaryKey, TenantScoped, Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        tenant_fk("notification_id", "notifications", name="fk_notification_deliveries__notification"),
        tenant_fk("user_id", "users"),
        UniqueConstraint("tenant_id", "notification_id", "channel", name="uq_notification_deliveries__once"),
        CheckConstraint("channel IN ('email')", name="channel"),
        CheckConstraint(f"status IN {DELIVERY_STATUSES}", name="status"),
        CheckConstraint("status <> 'sent' OR sent_at IS NOT NULL", name="sent_has_time"),
    )

    notification_id: Mapped[uuid.UUID]
    user_id: Mapped[uuid.UUID]
    channel: Mapped[str] = mapped_column(String(10), server_default="email")
    status: Mapped[str] = mapped_column(String(10), server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    last_error: Mapped[str | None] = mapped_column(String(100))
    sent_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
