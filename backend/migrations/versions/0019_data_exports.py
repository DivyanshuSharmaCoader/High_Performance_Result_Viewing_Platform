"""data exports: the institution's data as a ZIP of CSVs (P18.5)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-10 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.helpers import enable_tenant_rls, grant_app, grant_platform

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_exports",
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="queued", nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed', 'expired')", name=op.f("ck_data_exports__status")
        ),
        sa.CheckConstraint("status <> 'ready' OR file_id IS NOT NULL", name=op.f("ck_data_exports__ready_has_file")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "file_id"],
            ["files.tenant_id", "files.id"],
            name=op.f("fk_data_exports__tenant_id_file_id__files"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_exports")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_data_exports__tenant_id_id"),
    )
    op.create_index("ix_data_exports__tenant_created", "data_exports", ["tenant_id", "created_at"], unique=False)
    enable_tenant_rls("data_exports")
    grant_platform("data_exports", "SELECT")
    # The job moves an export through its states; nothing deletes one (the audit trail refers to it).
    grant_app("data_exports", "SELECT, INSERT, UPDATE")


def downgrade() -> None:
    op.drop_index("ix_data_exports__tenant_created", table_name="data_exports")
    op.drop_table("data_exports")
