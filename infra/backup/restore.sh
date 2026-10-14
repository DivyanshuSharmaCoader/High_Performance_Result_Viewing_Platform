#!/bin/sh
# Restore a backup made by backup.sh (P16.4; runbook docs/runbooks/backup-and-restore.md).
#
#   restore.sh [s3://.../scorecode-<stamp>.dump.age]    (default: the newest under BACKUP_S3_URI)
#
#   BACKUP_AGE_IDENTITY       file holding the age PRIVATE key (bring it from the vault for the restore)
#   PGHOST PGPORT PGUSER PGPASSWORD   the database owner (scorecode_migrator), into an EMPTY database
#   PGDATABASE                the database to restore into (created by the Postgres init: roles first)
#   RESTORE_JOBS              parallel restore jobs (default 4)
#   RESTORE_DUMP              an already-decrypted dump to restore instead (scorecode-ctl restore-test:
#                             the operator decrypts on their own machine, the key never comes here)
set -eu
: "${PGDATABASE:?target database}"
[ -n "${RESTORE_DUMP:-}" ] || : "${BACKUP_AGE_IDENTITY:?age private key file}"
endpoint=${BACKUP_S3_ENDPOINT:+--endpoint-url $BACKUP_S3_ENDPOINT}
src=${1:-}
if [ -z "$src" ] && [ -z "${RESTORE_DUMP:-}" ]; then
  : "${BACKUP_S3_URI:?s3://bucket/prefix}"
  # shellcheck disable=SC2086
  latest=$(aws $endpoint s3 ls --recursive "${BACKUP_S3_URI%/}/db/" | sort | tail -1 | awk '{print $4}')
  [ -n "$latest" ] || { echo "no backups under $BACKUP_S3_URI" >&2; exit 1; }
  bucket=$(echo "${BACKUP_S3_URI#s3://}" | cut -d/ -f1)
  src="s3://$bucket/$latest"
fi
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
started=$(date +%s)
if [ -n "${RESTORE_DUMP:-}" ]; then
  src=$RESTORE_DUMP
  ln -s "$RESTORE_DUMP" "$work/db.dump"
else
  # shellcheck disable=SC2086
  aws $endpoint s3 cp --only-show-errors "$src" "$work/db.dump.age"
  age --decrypt --identity "$BACKUP_AGE_IDENTITY" --output "$work/db.dump" "$work/db.dump.age"
fi
existing=$(psql -Atc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
[ "$existing" = 0 ] || { echo "refusing to restore into $PGDATABASE: it already has $existing tables" >&2; exit 1; }
jobs=${RESTORE_JOBS:-4}
# Tenant tables FORCE row-level security, which binds even their owner. Loading the rows, and validating
# the foreign keys afterwards, are queries a policy would filter, which pg_restore refuses. So it restores
# as the owner, with no superuser (works on managed PostgreSQL), in steps:
#   1. the schema;
#   2. FORCE lifted from exactly the tables that have it;
#   3. the data, then the policies, triggers, indexes and constraints;
#   4. FORCE again.
# Nothing connects during the restore (the API and worker are stopped). db-fingerprint.sh compares the RLS
# flags after a drill.
pg_restore --exit-on-error --section=pre-data --dbname="$PGDATABASE" "$work/db.dump"
forced=$(psql -At -c "SELECT c.oid::regclass FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE n.nspname = 'public' AND c.relforcerowsecurity ORDER BY 1")
for t in $forced; do psql -v ON_ERROR_STOP=1 -q -c "ALTER TABLE $t NO FORCE ROW LEVEL SECURITY"; done
pg_restore --exit-on-error --jobs="$jobs" --section=data --dbname="$PGDATABASE" "$work/db.dump"
pg_restore --exit-on-error --jobs="$jobs" --section=post-data --dbname="$PGDATABASE" "$work/db.dump"
for t in $forced; do psql -v ON_ERROR_STOP=1 -q -c "ALTER TABLE $t FORCE ROW LEVEL SECURITY"; done
psql -v ON_ERROR_STOP=1 -c "ANALYZE" > /dev/null
printf '{"restored":"%s","into":"%s","forced_rls_tables":%s,"seconds":%s}\n' "$src" "$PGDATABASE" \
  "$(echo "$forced" | grep -c . || true)" "$(( $(date +%s) - started ))"
