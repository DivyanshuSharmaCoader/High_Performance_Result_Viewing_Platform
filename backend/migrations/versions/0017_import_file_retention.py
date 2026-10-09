"""import file retention: files.purged_at, and tenant ids for maintenance tasks (docs/10 §12)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-09 16:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tenant ids only (no names, nothing else), so a maintenance task can visit each tenant under its own RLS
# context without the platform role.
OPS_TENANT_IDS = """
CREATE FUNCTION ops_tenant_ids()
RETURNS SETOF uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT id FROM tenants ORDER BY id
$$;
"""


def upgrade() -> None:
    # The stored object of an upload is deleted after its retention; the row stays (imports reference it).
    op.add_column("files", sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("GRANT UPDATE (purged_at) ON files TO scorecode_app")
    op.execute(OPS_TENANT_IDS)
    op.execute("REVOKE ALL ON FUNCTION ops_tenant_ids() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ops_tenant_ids() TO scorecode_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS ops_tenant_ids()")
    op.execute("REVOKE UPDATE (purged_at) ON files FROM scorecode_app")
    op.drop_column("files", "purged_at")
