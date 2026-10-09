from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, Timestamps, UUIDPrimaryKey, tenant_unique_id

FILE_KINDS = ("logo", "import", "marksheet", "export", "error_report", "activation_slips")


class StoredFile(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    """Metadata for every uploaded/generated object. Bytes live in object storage."""

    __tablename__ = "files"
    __table_args__ = (
        tenant_unique_id("files"),
        CheckConstraint(f"kind IN {FILE_KINDS}", name="kind"),
        CheckConstraint("size_bytes >= 0", name="size"),
        Index("uq_files__object_key", "object_key", unique=True),
        Index("ix_files__tenant_id_kind", "tenant_id", "kind"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    object_key: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(32))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[bytes] = mapped_column(LargeBinary(32))
    original_name: Mapped[str | None] = mapped_column(String(255))
    uploaded_by: Mapped[uuid.UUID | None]
    purged_at: Mapped[datetime | None]  # stored object deleted after its retention (uploads)
