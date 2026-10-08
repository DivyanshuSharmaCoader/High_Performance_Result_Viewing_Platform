"""Marksheet render state (docs/07 §2.7): one row per published result.

The PDF itself is a ``files`` row (kind ``marksheet``) in object storage. A row starts ``pending`` when the
publication is created, and the ``pdf`` worker moves it to ``rendered`` (with the file and its SHA-256) or
``failed`` (with the error, after the job's last attempt). Rows are never deleted: a withdrawn or
superseded publication keeps its marksheets, so verification can still say what was issued.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, PrimaryKeyConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantScoped, tenant_fk

DOCUMENT_STATUSES = ("pending", "rendered", "failed")


class MarksheetDocument(TenantScoped, Base):
    __tablename__ = "marksheet_documents"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "publication_id", "student_id"),
        ForeignKeyConstraint(
            ["tenant_id", "publication_id", "student_id"],
            [
                "published_results.tenant_id",
                "published_results.publication_id",
                "published_results.student_id",
            ],
            ondelete="RESTRICT",
            name="fk_marksheet_documents__published_results",
        ),
        tenant_fk("file_id", "files"),
        CheckConstraint(f"status IN {DOCUMENT_STATUSES}", name="status"),
        CheckConstraint(
            "status <> 'rendered' OR (file_id IS NOT NULL AND sha256 IS NOT NULL AND rendered_at IS NOT NULL)",
            name="rendered_has_file",
        ),
        CheckConstraint("sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
    )

    publication_id: Mapped[uuid.UUID]
    student_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(10), server_default="pending")
    template_code: Mapped[str] = mapped_column(String(40))
    template_version: Mapped[int] = mapped_column(Integer)
    file_id: Mapped[uuid.UUID | None]
    sha256: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(300))
    rendered_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
