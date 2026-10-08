#!/bin/sh
# Restore a backup made by backup.sh (P16.4; runbook docs/runbooks/backup-and-restore.md).
#
#   restore.sh [s3://.../scorecode-<stamp>.dump.age]    (default: the newest under BACKUP_S3_URI)
#
#   BACKUP_AGE_IDENTITY       file holding the age PRIVATE key (bring it from the vault for the restore)
#   PGHOST PGPORT PGUSER PGPASSWORD   the database owner (scorecode_migrator), into an EMPTY database
#   PGDATABASE                the database to restore into (created by the Postgres init: roles first)
#   RESTORE_JOBS              parallel restore jobs (default 4)
set -eu
: "${BACKUP_AGE_IDENTITY:?age private key file}" "${PGDATABASE:?target database}"
endpoint=${BACKUP_S3_ENDPOINT:+--endpoint-url $BACKUP_S3_ENDPOINT}
src=${1:-}
if [ -z "$src" ]; then
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
# shellcheck disable=SC2086
aws $endpoint s3 cp --only-show-errors "$src" "$work/db.dump.age"
age --decrypt --identity "$BACKUP_AGE_IDENTITY" --output "$work/db.dump" "$work/db.dump.age"
existing=$(psql -Atc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
[ "$existing" = 0 ] || { echo "refusing to restore into $PGDATABASE: it already has $existing tables" >&2; exit 1; }
pg_restore --exit-on-error --jobs="${RESTORE_JOBS:-4}" --dbname="$PGDATABASE" "$work/db.dump"
psql -v ON_ERROR_STOP=1 -c "ANALYZE" > /dev/null
printf '{"restored":"%s","into":"%s","seconds":%s}\n' "$src" "$PGDATABASE" "$(( $(date +%s) - started ))"
