#!/usr/bin/env bash
# A fingerprint of the ScoreCode database for restore drills (P16.4): the schema version, the row count of
# every table, checksums of what must never change silently (published results, frozen statistics,
# verification records, marksheet fingerprints), and the isolation posture: which tables enable and force
# row-level security, the policies, triggers and grants. Identical output means the restore is complete
# and still isolates tenants.
#
#   infra/ops/db-fingerprint.sh            # the compose stack's postgres container, as the superuser
set -euo pipefail
psql() { docker compose exec -T postgres psql -U postgres -d scorecode -v ON_ERROR_STOP=1 -At "$@"; }
psql -c "SELECT 'alembic_version ' || version_num FROM alembic_version"
for table in $(psql -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"); do
  psql -c "SELECT 'rows $table ' || count(*) FROM \"$table\""
done
psql -c "SELECT 'md5 published_results ' || md5(string_agg(publication_id::text || student_id::text || payload::text, '|' ORDER BY publication_id, student_id)) FROM published_results"
psql -c "SELECT 'md5 exam_statistics ' || md5(string_agg(publication_id::text || stats::text, '|' ORDER BY publication_id)) FROM exam_statistics"
psql -c "SELECT 'md5 verification_records ' || md5(string_agg(row(v.*)::text, '|' ORDER BY row(v.*)::text)) FROM verification_records v"
psql -c "SELECT 'md5 marksheet_documents ' || md5(string_agg(row(d.*)::text, '|' ORDER BY row(d.*)::text)) FROM marksheet_documents d"
psql -c "SELECT 'md5 users ' || md5(string_agg(row(u.*)::text, '|' ORDER BY row(u.*)::text)) FROM users u"
psql -c "SELECT 'md5 audit_logs ' || md5(string_agg(row(a.*)::text, '|' ORDER BY row(a.*)::text)) FROM audit_logs a"
psql -c "SELECT 'rls ' || c.relname || ' enabled=' || c.relrowsecurity || ' forced=' || c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') ORDER BY c.relname"
psql -c "SELECT 'policy ' || tablename || ' ' || policyname || ' ' || md5(coalesce(qual, '') || coalesce(with_check, '')) FROM pg_policies WHERE schemaname = 'public' ORDER BY tablename, policyname"
psql -c "SELECT 'trigger ' || event_object_table || ' ' || trigger_name || ' ' || event_manipulation FROM information_schema.triggers WHERE trigger_schema = 'public' ORDER BY 1"
psql -c "SELECT 'grants ' || md5(string_agg(grantee || ':' || table_name || ':' || privilege_type, ',' ORDER BY grantee, table_name, privilege_type)) FROM information_schema.role_table_grants WHERE table_schema = 'public'"
psql -c "SELECT 'functions ' || md5(string_agg(p.proname || ':' || p.prosecdef || ':' || md5(p.prosrc), ',' ORDER BY p.proname)) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public'"
