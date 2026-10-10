"""corrections after publication: who started one, when and why (P18.3)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-10 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Set while a correction of published results is in progress: from "start correction" until the
    # corrected version is published (or the correction is cancelled). The live version stays visible.
    op.add_column("examinations", sa.Column("correction_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("examinations", sa.Column("correction_started_by", sa.Uuid(), nullable=True))
    op.add_column("examinations", sa.Column("correction_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("examinations", "correction_reason")
    op.drop_column("examinations", "correction_started_by")
    op.drop_column("examinations", "correction_started_at")
