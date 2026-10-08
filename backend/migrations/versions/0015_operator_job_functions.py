"""operator job functions: list and retry dead jobs (P16.6 runbooks)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-09 11:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# For `scorecode jobs dead|retry` (docs/runbooks/stuck-publication.md). Granted to the platform role only:
# the running API and workers (scorecode_app) can't call them. Payloads never leave; errors are truncated.
JOBS_DEAD = """
CREATE FUNCTION jobs_dead(p_limit int)
RETURNS TABLE (id uuid, queue text, kind text, tenant_id uuid, attempts int, last_error text,
               finished_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT j.id, j.queue, j.kind, j.tenant_id, j.attempts, left(j.last_error, 300), j.finished_at
      FROM jobs j
     WHERE j.status = 'dead'
     ORDER BY j.finished_at DESC NULLS LAST
     LIMIT p_limit
$$;
"""

# A dead job runs again from attempt 0. If an equivalent job (same dedupe key) is already queued or
# running, there's nothing to retry: false.
JOBS_RETRY = """
CREATE FUNCTION jobs_retry(p_id uuid)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    n int;
BEGIN
    UPDATE jobs
       SET status = 'queued', attempts = 0, run_at = now(), locked_by = NULL, locked_until = NULL,
           finished_at = NULL, updated_at = now()
     WHERE id = p_id AND status = 'dead';
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n = 1;
EXCEPTION WHEN unique_violation THEN
    RETURN false;
END
$$;
"""


def upgrade() -> None:
    op.execute(JOBS_DEAD)
    op.execute(JOBS_RETRY)
    for signature in ("jobs_dead(int)", "jobs_retry(uuid)"):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO scorecode_platform")
    op.execute("GRANT EXECUTE ON FUNCTION jobs_stats() TO scorecode_platform")


def downgrade() -> None:
    op.execute("REVOKE EXECUTE ON FUNCTION jobs_stats() FROM scorecode_platform")
    op.execute("DROP FUNCTION IF EXISTS jobs_retry(uuid)")
    op.execute("DROP FUNCTION IF EXISTS jobs_dead(int)")
