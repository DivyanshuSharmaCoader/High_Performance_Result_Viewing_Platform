"""SQL for the kernel migration: functions that must run with the schema owner's rights.

Every function is ``SECURITY DEFINER`` with a pinned ``search_path`` and EXECUTE revoked from PUBLIC.
They expose exactly one narrow capability each, so the runtime role never needs cross-tenant reads.
"""

RESOLVE_TENANT = """
CREATE OR REPLACE FUNCTION resolve_tenant(p_slug text, p_domain text)
RETURNS TABLE (id uuid, slug text, name text, status text, config_version int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT t.id, t.slug::text, t.name::text, t.status::text, t.config_version
      FROM tenants t
     WHERE p_slug IS NOT NULL AND t.slug = p_slug
    UNION ALL
    SELECT t.id, t.slug::text, t.name::text, t.status::text, t.config_version
      FROM tenant_domains d JOIN tenants t ON t.id = d.tenant_id
     WHERE p_slug IS NULL AND d.domain = p_domain AND d.status = 'verified'
    LIMIT 1
$$;
"""

SLUG_TAKEN = """
CREATE OR REPLACE FUNCTION tenant_slug_taken(p_slug text)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT EXISTS (SELECT 1 FROM tenants WHERE slug = p_slug)
$$;
"""

JOBS_CLAIM = """
CREATE OR REPLACE FUNCTION jobs_claim(p_queues text[], p_worker text, p_limit int, p_lease_s int, p_tenant_cap int)
RETURNS TABLE (id uuid, tenant_id uuid, queue text, kind text, payload jsonb, attempts int, max_attempts int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    RETURN QUERY
    WITH candidates AS (
        SELECT j.id
          FROM jobs j
         WHERE j.status = 'queued'
           AND j.queue = ANY (p_queues)
           AND j.run_at <= now()
           AND (j.tenant_id IS NULL OR (
                SELECT count(*) FROM jobs r
                 WHERE r.status = 'running' AND r.tenant_id = j.tenant_id AND r.queue = j.queue
               ) < p_tenant_cap)
         ORDER BY j.run_at, j.id
         LIMIT p_limit
         FOR UPDATE SKIP LOCKED
    )
    UPDATE jobs AS u
       SET status = 'running',
           attempts = u.attempts + 1,
           locked_by = p_worker,
           locked_until = now() + make_interval(secs => p_lease_s),
           started_at = now(),
           updated_at = now()
      FROM candidates c
     WHERE u.id = c.id
    RETURNING u.id, u.tenant_id, u.queue::text, u.kind::text, u.payload, u.attempts, u.max_attempts;
END
$$;
"""

JOBS_FINISH = """
CREATE OR REPLACE FUNCTION jobs_finish(p_id uuid, p_worker text, p_status text, p_result jsonb,
                                       p_error text, p_retry_in_s int)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    IF p_status NOT IN ('succeeded', 'failed', 'dead', 'queued') THEN
        RAISE EXCEPTION 'invalid job status %', p_status;
    END IF;
    UPDATE jobs
       SET status = p_status,
           result = COALESCE(p_result, result),
           last_error = p_error,
           finished_at = CASE WHEN p_status = 'queued' THEN NULL ELSE now() END,
           run_at = CASE WHEN p_status = 'queued'
                         THEN now() + make_interval(secs => COALESCE(p_retry_in_s, 0)) ELSE run_at END,
           locked_by = NULL,
           locked_until = NULL,
           updated_at = now()
     WHERE id = p_id AND locked_by = p_worker AND status = 'running';
END
$$;
"""

JOBS_HEARTBEAT = """
CREATE OR REPLACE FUNCTION jobs_heartbeat(p_id uuid, p_worker text, p_lease_s int)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    UPDATE jobs SET locked_until = now() + make_interval(secs => p_lease_s), updated_at = now()
     WHERE id = p_id AND locked_by = p_worker AND status = 'running'
$$;
"""

JOBS_REAP = """
CREATE OR REPLACE FUNCTION jobs_reap()
RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    n int;
BEGIN
    UPDATE jobs
       SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
           last_error = 'lease expired (worker lost)',
           finished_at = CASE WHEN attempts >= max_attempts THEN now() ELSE NULL END,
           locked_by = NULL,
           locked_until = NULL,
           run_at = now(),
           updated_at = now()
     WHERE status = 'running' AND locked_until < now();
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END
$$;
"""

JOBS_MAKE_DUE = """
CREATE OR REPLACE FUNCTION jobs_make_due(p_queues text[])
RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    n int;
BEGIN
    -- Operational helper ("run scheduled work now"); used by the CLI and tests.
    UPDATE jobs SET run_at = now(), updated_at = now()
     WHERE status = 'queued' AND queue = ANY (p_queues) AND run_at > now();
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END
$$;
"""

AUDIT_PARTITIONS = """
CREATE OR REPLACE FUNCTION ensure_audit_partitions(p_months_ahead int)
RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    start_month date := date_trunc('month', now() - interval '1 month')::date;
    m date;
    part text;
    created int := 0;
BEGIN
    FOR i IN 0..(p_months_ahead + 1) LOOP
        m := (start_month + make_interval(months => i))::date;
        part := 'audit_logs_p' || to_char(m, 'YYYYMM');
        IF to_regclass(part) IS NULL THEN
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF audit_logs FOR VALUES FROM (%L) TO (%L)',
                part, m, (m + interval '1 month')::date
            );
            created := created + 1;
        END IF;
    END LOOP;
    RETURN created;
END
$$;
"""

DEFINER_FUNCTIONS = {
    "resolve_tenant(text, text)": RESOLVE_TENANT,
    "tenant_slug_taken(text)": SLUG_TAKEN,
    "jobs_claim(text[], text, int, int, int)": JOBS_CLAIM,
    "jobs_finish(uuid, text, text, jsonb, text, int)": JOBS_FINISH,
    "jobs_heartbeat(uuid, text, int)": JOBS_HEARTBEAT,
    "jobs_reap()": JOBS_REAP,
    "jobs_make_due(text[])": JOBS_MAKE_DUE,
    "ensure_audit_partitions(int)": AUDIT_PARTITIONS,
}
