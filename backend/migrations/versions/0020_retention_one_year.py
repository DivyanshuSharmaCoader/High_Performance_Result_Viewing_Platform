"""retention aligned with the DPDP Rules 2025 (rule 8(3)) and the CERT-In directions (P18.14)

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-10 18:00:00

Records of processing (sign-in sessions with their address and browser, platform sessions, reset and
invitation tokens, background jobs, email deliveries) are kept for one year after they end, then deleted:
the DPDP Rules 2025, rule 8(3) (in force from May 2027) ask for "personal data, associated traffic data and
other logs of the processing" to be kept for at least a year, and the CERT-In directions of 28 April 2022
for logs to be kept 180 days in India. Before this they went after 30 or 90 days.

Unchanged, on purpose: raw import staging rows (copies of uploaded spreadsheets) still go 30 days after
the import ends, and unused sign-up requests 30 days after they expire: data minimisation, and the
imported records themselves remain. Idempotency keys (cached responses) go when they expire; in-app
notices after a year. docs/legal/readiness-matrix.md records the open legal questions.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPS_PURGE = """
CREATE OR REPLACE FUNCTION ops_purge()
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    t record;
    n int;
    c jsonb := '{}'::jsonb;
BEGIN
    -- Not tenant data: platform sessions and sign-up requests.
    DELETE FROM platform_sessions WHERE coalesce(revoked_at, expires_at) < now() - interval '365 days';
    GET DIAGNOSTICS n = ROW_COUNT; c := c || jsonb_build_object('platform_sessions', n);
    DELETE FROM signup_requests WHERE expires_at < now() - interval '30 days';
    GET DIAGNOSTICS n = ROW_COUNT; c := c || jsonb_build_object('signup_requests', n);
    -- Jobs (definer_access, like jobs_reap): payloads hold ids, results hold summaries.
    DELETE FROM jobs
     WHERE status IN ('succeeded', 'cancelled', 'failed', 'dead') AND finished_at < now() - interval '365 days';
    GET DIAGNOSTICS n = ROW_COUNT; c := c || jsonb_build_object('jobs', n);

    c := c || jsonb_build_object('sessions', 0, 'auth_tokens', 0, 'idempotency_keys', 0, 'import_rows', 0,
                                 'notification_deliveries', 0, 'notifications', 0, 'tenants', 0);
    FOR t IN SELECT id FROM tenants ORDER BY id LOOP
        PERFORM set_config('app.tenant_id', t.id::text, true);
        DELETE FROM sessions
         WHERE coalesce(revoked_at, least(expires_at, absolute_expires_at)) < now() - interval '365 days';
        GET DIAGNOSTICS n = ROW_COUNT; c := jsonb_set(c, '{sessions}', to_jsonb((c->>'sessions')::int + n));
        DELETE FROM auth_tokens WHERE expires_at < now() - interval '365 days';
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
           AND (d.created_at < now() - interval '365 days'
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


# 0016's windows (30 and 90 days), restored by a downgrade.
PREVIOUS = """
CREATE OR REPLACE FUNCTION ops_purge()
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


def downgrade() -> None:
    op.execute(PREVIOUS)
