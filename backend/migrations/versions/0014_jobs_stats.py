"""jobs_stats() for the worker's queue metrics (P16.5)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-09 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Counts only, across tenants, for alerting (queue backlog, dead letters, late scheduled work): no rows,
# ids or payloads leave the function. "queued" counts jobs that are due now; scheduled ones aren't backlog.
JOBS_STATS = """
CREATE FUNCTION jobs_stats()
RETURNS TABLE (queue text, status text, jobs bigint, oldest_s double precision)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT j.queue, j.status, count(*)::bigint,
           COALESCE(EXTRACT(EPOCH FROM now() - min(j.run_at)), 0)::double precision
      FROM jobs j
     WHERE j.status IN ('queued', 'running', 'dead')
       AND (j.status <> 'queued' OR j.run_at <= now())
     GROUP BY j.queue, j.status
$$;
"""


def upgrade() -> None:
    op.execute(JOBS_STATS)
    op.execute("REVOKE ALL ON FUNCTION jobs_stats() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION jobs_stats() TO scorecode_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS jobs_stats()")
