from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, Timestamps, Versioned

FONT_ALLOW_LIST = ("Inter", "Source Sans 3", "Noto Sans", "IBM Plex Sans", "Merriweather Sans")


class TenantBranding(TenantScoped, Versioned, Timestamps, Base):
    """1:1 branding (docs/07 §2.2). Brand tokens only; semantic colours are fixed (docs/09 §5)."""

    __tablename__ = "tenant_branding"
    __table_args__ = (
        CheckConstraint("primary_color ~ '^#[0-9a-f]{6}$'", name="primary_color"),
        CheckConstraint("accent_color ~ '^#[0-9a-f]{6}$'", name="accent_color"),
        CheckConstraint(f"font_family IN {FONT_ALLOW_LIST}", name="font_family"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(120))
    short_name: Mapped[str | None] = mapped_column(String(24))
    logo_file_id: Mapped[uuid.UUID | None]
    primary_color: Mapped[str] = mapped_column(String(7), server_default="#2952cc")
    accent_color: Mapped[str] = mapped_column(String(7), server_default="#0f766e")
    font_family: Mapped[str] = mapped_column(String(40), server_default="Inter")
    login_heading: Mapped[str | None] = mapped_column(String(120))
    login_message: Mapped[str | None] = mapped_column(Text)
    footer_text: Mapped[str | None] = mapped_column(String(300))
    support_email: Mapped[str | None] = mapped_column(String(254))
    show_powered_by: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
