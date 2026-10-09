"""ops_purge(): the retention policy for operational data, applied daily (docs/10 §12, ASVS 8.3.4)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-09 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Retention (docs/10 §12): sessions and tokens 30 days after they ended; idempotency keys at expiry;
# finished jobs 30 days, failed or dead ones 90; import staging rows (raw student data and marks) 30 days
# after the import ended, the import's summary row stays; email delivery records 90 days; in-app
# notifications 365 days. Audit logs, publications, results and verification records are never purged
# here: they are the record.
#
# SECURITY DEFINER, but tenant data is still deleted under RLS: the function sets each tenant's context in
# turn (the tenant_isolation policies apply to every role, the owner included), so one tenant's iteration
# can only see that tenant's rows. The runtime role may call it; it still holds no DELETE on the
# append-only tables (notifications, deliveries).
OPS_PURGE = """
CREATE FUNCTION ops_purge()
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    t record;
    n int;
    c jsonb := '{}'::jsonb;
BEGIN
    -- Not tenant data: platform sessions and sign-up requests.
    DELETE FROM platform_sessions WHERE coalesce(revoked_at, expires_at) < now() - interval '30 days';
    GET DIAGNOSTICS n = ROW_COUNT; c := c || jsonb_build_object('platform_sessions', n);
    DELETE FROM signup_requests WHERE expires_at < now() - interval '30 days';
    GET DIAGNOSTICS n = ROW_COUNT; c := c || jsonb_build_object('signup_requests', n);
    -- Jobs (definer_access, like jobs_reap): payloads hold ids, results hold summaries.
    DELETE FROM jobs
     WHERE (status IN ('succeeded', 'cancelled') AND finished_at < now() - interval '30 days')
        OR (status IN ('failed', 'dead') AND finished_at < now() - interval '90 days');
    GET DIAGNOSTICS n = ROW_COUNT; c := c || jsonb_build_object('jobs', n);

    c := c || jsonb_build_object('sessions', 0, 'auth_tokens', 0, 'idempotency_keys', 0, 'import_rows', 0,
                                 'notification_deliveries', 0, 'notifications', 0, 'tenants', 0);
    FOR t IN SELECT id FROM tenants ORDER BY id LOOP
        PERFORM set_config('app.tenant_id', t.id::text, true);
        DELETE FROM sessions
         WHERE coalesce(revoked_at, least(expires_at, absolute_expires_at)) < now() - interval '30 days';
        GET DIAGNOSTICS n = ROW_COUNT; c := jsonb_set(c, '{sessions}', to_jsonb((c->>'sessions')::int + n));
        DELETE FROM auth_tokens WHERE expires_at < now() - interval '30 days';
        GET DIAGNOSTICS n = ROW_COUNT; c := jsonb_set(c, '{auth_tokens}', to_jsonb((c->>'auth_tokens')::int + n));
        DELETE FROM idempotency_keys WHERE expires_at < now();
        GET DIAGNOSTICS n = ROW_COUNT;
        c := jsonb_set(c, '{idempotency_keys}', to_jsonb((c->>'idempotency_keys')::int + n));
        DELETE FROM import_rows r USING import_jobs j
         WHERE r.import_job_id = j.id AND j.status IN ('committed', 'failed', 'cancelled')
           AND j.updated_at < now() - interval '30 days';
        GET DIAGNOSTICS n = ROW_COUNT; c := jsonb_set(c, '{import_rows}', to_jsonb((c->>'import_rows')::int + n));
        DELETE FROM notification_deliveries d
         WHERE d.status IN ('sent', 'failed', 'skipped')
           AND (d.created_at < now() - interval '90 days'
                OR d.notification_id IN (SELECT id FROM notifications WHERE created_at < now() - interval '365 days'));
        GET DIAGNOSTICS n = ROW_COUNT;
        c := jsonb_set(c, '{notification_deliveries}', to_jsonb((c->>'notification_deliveries')::int + n));
        DELETE FROM notifications x
         WHERE x.created_at < now() - interval '365 days'
           AND NOT EXISTS (SELECT 1 FROM notification_deliveries d WHERE d.notification_id = x.id);
        GET DIAGNOSTICS n = ROW_COUNT;
        c := jsonb_set(c, '{notifications}', to_jsonb((c->>'notifications')::int + n));
        c := jsonb_set(c, '{tenants}', to_jsonb((c->>'tenants')::int + 1));
    END LOOP;
    PERFORM set_config('app.tenant_id', '', true);  -- no tenant context leaks out of the function
    PERFORM ensure_audit_partitions(3);  -- a long-running API never restarts to make next month's
    RETURN c;
END
$$;
"""


def upgrade() -> None:
    op.execute(OPS_PURGE)
    op.execute("REVOKE ALL ON FUNCTION ops_purge() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ops_purge() TO scorecode_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS ops_purge()")
