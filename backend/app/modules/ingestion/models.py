"""Import staging (docs/13): one job per uploaded file, one staged row per data row. Nothing touches live
data until an explicit commit."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
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

IMPORT_STATUSES = (
    "uploaded",
    "parsing",
    "needs_mapping",
    "validating",
    "validated",
    "committing",
    "committed",
    "failed",
    "cancelled",
)
ROW_STATUSES = ("pending", "valid", "warning", "error", "skipped")


class ImportJob(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        tenant_unique_id("import_jobs"),
        tenant_fk("file_id", "files"),
        CheckConstraint(f"status IN {IMPORT_STATUSES}", name="status"),
        CheckConstraint("kind IN ('students', 'marks')", name="kind"),
        tenant_fk("supersedes_id", "import_jobs"),
        Index("ix_import_jobs__tenant_created", "tenant_id", "created_at"),
        # The same bytes can be "in flight" only once per kind/target: re-uploading resumes that job,
        # and a file that was already committed is reported instead of being imported twice (docs/13 §2).
        Index(
            "uq_import_jobs__active_file",
            "tenant_id",
            "kind",
            "target_exam_id",
            "file_sha256",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=text("status NOT IN ('cancelled', 'failed')"),
        ),
    )

    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default="uploaded")
    file_id: Mapped[uuid.UUID]
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_sha256: Mapped[bytes] = mapped_column(LargeBinary(32))
    target_exam_id: Mapped[uuid.UUID | None]  # marks imports (Phase 8); FK added with the exams table
    supersedes_id: Mapped[uuid.UUID | None]  # the job this re-upload replaced
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")  # e.g. {"session_id": ...}
    sheet_name: Mapped[str | None] = mapped_column(String(100))
    columns: Mapped[list[Any] | None] = mapped_column(JSONB)  # header labels as found in the file
    header_row: Mapped[int | None] = mapped_column(Integer)
    mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # field key -> column index
    file_issues: Mapped[list[Any] | None] = mapped_column(JSONB)
    rows_total: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_valid: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_warning: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_error: Mapped[int] = mapped_column(Integer, server_default="0")
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # preview of what commit will do / did
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None]
    committed_by: Mapped[uuid.UUID | None]
    committed_at: Mapped[datetime | None]
    last_job_id: Mapped[uuid.UUID | None]


class ImportRow(TenantScoped, Base):
    __tablename__ = "import_rows"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "import_job_id", "row_no"),
        tenant_fk("import_job_id", "import_jobs", ondelete="CASCADE"),
        CheckConstraint(f"status IN {ROW_STATUSES}", name="status"),
        Index("ix_import_rows__job_status", "tenant_id", "import_job_id", "status"),
    )

    import_job_id: Mapped[uuid.UUID]
    row_no: Mapped[int] = mapped_column(Integer)  # 1-based row number as shown in the spreadsheet
    raw: Mapped[list[Any]] = mapped_column(JSONB)
    normalized: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    issues: Mapped[list[Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(10), server_default="pending")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
