#!/usr/bin/env bash
# A fingerprint of the ScoreCode database for restore drills (P16.4): the schema version, the row count of
# every table, and checksums of what must never change silently — published results, frozen statistics,
# verification records and marksheet fingerprints. Two identical outputs mean the restore is complete.
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
psql -c "SELECT 'md5 verification_records ' || md5(string_agg(row(v.*)::text, '|' ORDER BY v.id)) FROM verification_records v"
psql -c "SELECT 'md5 marksheet_documents ' || md5(string_agg(row(d.*)::text, '|' ORDER BY d.id)) FROM marksheet_documents d"
psql -c "SELECT 'md5 users ' || md5(string_agg(row(u.*)::text, '|' ORDER BY u.id)) FROM users u"
psql -c "SELECT 'md5 audit_logs ' || md5(string_agg(row(a.*)::text, '|' ORDER BY a.id)) FROM audit_logs a"
