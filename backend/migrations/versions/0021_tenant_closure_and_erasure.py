"""closing an institution's account and erasing its data (P18.14; docs/legal, runbooks/tenant-offboarding.md)

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-10 19:00:00

Two independent approvals, then a worker does the erasure:
1. The institution's owner asks to close the account (tenant_settings.closure_*): 30 days to export and to
   change their mind; everything keeps working meanwhile.
2. After those 30 days, a ScoreCode staff member approves (tenants.status = 'closing', a column only the
   platform role may change). The portal goes offline at that moment.
3. The worker's maintenance task deletes the stored files, then calls ``ops_erase_tenant``, which checks
   both approvals and the institution's address again and deletes every tenant row in dependency order.

Kept, on purpose (and said so in the docs): the ``tenants`` row as a tombstone (status 'closed', no
personal data), ``tenant_subscriptions`` (financial records), ``tenant_trials`` and the hashed
``trial_claims`` (so a closed institution can't take a second free trial), and the platform audit log.
Encrypted backups keep the data until they expire.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every table with tenant_id, children first, except the ones kept (KEPT). tests/unit check that a new
# tenant table can't be forgotten here.
ERASE_ORDER = (
    "verification_records", "notification_deliveries", "marksheet_documents", "student_paper_results",
    "published_results", "notifications", "exam_statistics", "student_exam_results", "publications",
    "paper_submissions", "paper_assignments", "mark_entries", "import_rows", "approvals", "result_runs",
    "import_jobs", "exam_papers", "exam_cohorts", "cohort_memberships", "user_roles", "students",
    "staff_profiles", "sessions", "examinations", "data_exports", "cohorts", "auth_tokens", "users", "terms",
    "tenant_usage_counters", "tenant_settings", "tenant_feature_overrides", "tenant_domains",
    "tenant_branding", "programs", "jobs", "idempotency_keys", "grading_scheme_versions", "files", "courses",
    "signup_requests", "grading_schemes", "departments", "audit_logs", "academic_sessions",
)  # fmt: skip
KEPT = ("tenant_subscriptions", "tenant_trials")

# The snapshots stay immutable for everyone, except inside the erasure of their own institution.
IMMUTABLE = """
CREATE OR REPLACE FUNCTION published_snapshots_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' AND current_setting('app.erasing_tenant', true) = OLD.tenant_id::text THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'published results are immutable; publish a new version instead'
    USING ERRCODE = 'restrict_violation';
END $$
"""
IMMUTABLE_BEFORE = """
CREATE OR REPLACE FUNCTION published_snapshots_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'published results are immutable; publish a new version instead'
    USING ERRCODE = 'restrict_violation';
END $$
"""

ERASE = (
    """
CREATE FUNCTION ops_erase_tenant(p_tenant uuid, p_slug text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    t record;
    due timestamptz;
    tbl text;
    n int;
    c jsonb := '{}'::jsonb;
BEGIN
    SELECT id, slug, status INTO t FROM tenants WHERE id = p_tenant FOR UPDATE;
    IF NOT FOUND OR t.slug <> p_slug THEN
        RAISE EXCEPTION 'unknown institution, or the address does not match' USING ERRCODE = 'no_data_found';
    END IF;
    IF t.status <> 'closing' THEN
        RAISE EXCEPTION 'erasure needs ScoreCode''s approval first (status closing)' USING ERRCODE = 'restrict_violation';
    END IF;
    PERFORM set_config('app.tenant_id', p_tenant::text, true);
    SELECT closure_delete_after INTO due FROM tenant_settings WHERE tenant_id = p_tenant;
    IF due IS NULL OR due > now() THEN
        RAISE EXCEPTION 'the institution has not asked to close, or its 30 days have not passed'
            USING ERRCODE = 'restrict_violation';
    END IF;
    PERFORM set_config('app.erasing_tenant', p_tenant::text, true);
    FOREACH tbl IN ARRAY ARRAY["""
    + ", ".join(f"'{t}'" for t in ERASE_ORDER)
    + """] LOOP
        EXECUTE format('DELETE FROM %I WHERE tenant_id = $1', tbl) USING p_tenant;
        GET DIAGNOSTICS n = ROW_COUNT;
        c := c || jsonb_build_object(tbl, n);
    END LOOP;
    UPDATE tenants
       SET status = 'closed', status_reason = 'Data erased at the institution''s request',
           config_version = config_version + 1
     WHERE id = p_tenant;
    PERFORM set_config('app.erasing_tenant', '', true);
    PERFORM set_config('app.tenant_id', '', true);
    RETURN c;
END
$$;
"""
)

DUE = """
CREATE FUNCTION ops_tenants_due_for_erasure()
RETURNS TABLE (id uuid, slug text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    t record;
BEGIN
    FOR t IN SELECT x.id, x.slug::text AS slug FROM tenants x WHERE x.status = 'closing' ORDER BY x.id LOOP
        PERFORM set_config('app.tenant_id', t.id::text, true);
        IF EXISTS (SELECT 1 FROM tenant_settings s WHERE s.tenant_id = t.id AND s.closure_delete_after <= now()) THEN
            id := t.id;
            slug := t.slug;
            RETURN NEXT;
        END IF;
    END LOOP;
    PERFORM set_config('app.tenant_id', '', true);
END
$$;
"""


def upgrade() -> None:
    op.add_column("tenant_settings", sa.Column("closure_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenant_settings", sa.Column("closure_requested_by", sa.Uuid(), nullable=True))
    op.add_column("tenant_settings", sa.Column("closure_reason", sa.Text(), nullable=True))
    op.add_column("tenant_settings", sa.Column("closure_delete_after", sa.DateTime(timezone=True), nullable=True))
    op.execute(IMMUTABLE)
    op.execute(ERASE)
    op.execute(DUE)
    for fn in ("ops_erase_tenant(uuid, text)", "ops_tenants_due_for_erasure()"):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO scorecode_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS ops_tenants_due_for_erasure()")
    op.execute("DROP FUNCTION IF EXISTS ops_erase_tenant(uuid, text)")
    op.execute(IMMUTABLE_BEFORE)
    for col in ("closure_delete_after", "closure_reason", "closure_requested_by", "closure_requested_at"):
        op.drop_column("tenant_settings", col)
