#!/bin/sh
# Encrypted logical backup of the ScoreCode database to a second storage (P16.4, docs/10 §12).
#
#   PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD   the scorecode_backup role (read-only, BYPASSRLS)
#   BACKUP_AGE_RECIPIENT       age public key; the private key never lives on this server
#   BACKUP_S3_URI              s3://bucket/prefix on the second storage
#   BACKUP_S3_ENDPOINT         for non-AWS S3 (R2, SeaweedFS, ...); empty for AWS
#   AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION
#   BACKUP_FILES_S3_URI        optional: the files bucket, synced too (marksheet PDFs can't be re-rendered
#                              byte for byte, and their SHA-256 is what verification checks)
#   FILES_S3_ENDPOINT FILES_S3_REGION FILES_S3_ACCESS_KEY_ID FILES_S3_SECRET_ACCESS_KEY
#                              optional: the files bucket's own provider and keys (R2), when it is not on
#                              the backup storage; without them the backup storage's are used
#   BACKUP_FILES_MIRROR        optional: a persistent directory, so each run copies only new files
#   PUSHGATEWAY_URL            optional: report success for the ScoreCodeBackupStale alert
#
# Writes <prefix>/db/YYYY/MM/scorecode-<UTC timestamp>.dump.age and prints one line of JSON.
set -eu
: "${BACKUP_AGE_RECIPIENT:?age public key}" "${BACKUP_S3_URI:?s3://bucket/prefix}"
endpoint=${BACKUP_S3_ENDPOINT:+--endpoint-url $BACKUP_S3_ENDPOINT}
stamp=$(date -u +%Y%m%dT%H%M%SZ)
key="${BACKUP_S3_URI%/}/db/$(date -u +%Y/%m)/scorecode-$stamp.dump.age"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
started=$(date +%s)

# Custom format: compressed, restorable in parallel, table by table. One snapshot, so it is consistent
# without stopping writes.
pg_dump --format=custom --compress=6 --no-comments --file="$work/db.dump"
pg_restore --list "$work/db.dump" > /dev/null  # readable before it is shipped
age --encrypt --recipient "$BACKUP_AGE_RECIPIENT" --output "$work/db.dump.age" "$work/db.dump"
sha=$(sha256sum "$work/db.dump.age" | cut -d' ' -f1)
size=$(wc -c < "$work/db.dump.age" | tr -d ' ')
# shellcheck disable=SC2086
aws $endpoint s3 cp --only-show-errors --metadata "sha256=$sha" "$work/db.dump.age" "$key"

if [ -n "${BACKUP_FILES_S3_URI:-}" ]; then
  # Two providers can't sync bucket to bucket, so through a local mirror: files bucket → mirror with the
  # files provider's keys, then mirror → backup storage with the backup keys.
  mirror=${BACKUP_FILES_MIRROR:-$work/files}
  mkdir -p "$mirror"
  files_endpoint=${FILES_S3_ENDPOINT:-${BACKUP_S3_ENDPOINT:-}}
  # shellcheck disable=SC2086
  AWS_ACCESS_KEY_ID=${FILES_S3_ACCESS_KEY_ID:-$AWS_ACCESS_KEY_ID} \
  AWS_SECRET_ACCESS_KEY=${FILES_S3_SECRET_ACCESS_KEY:-$AWS_SECRET_ACCESS_KEY} \
  AWS_DEFAULT_REGION=${FILES_S3_REGION:-$AWS_DEFAULT_REGION} \
    aws ${files_endpoint:+--endpoint-url $files_endpoint} s3 sync --only-show-errors "$BACKUP_FILES_S3_URI" "$mirror"
  # shellcheck disable=SC2086
  aws $endpoint s3 sync --only-show-errors "$mirror" "${BACKUP_S3_URI%/}/files/"
fi

took=$(( $(date +%s) - started ))
if [ -n "${PUSHGATEWAY_URL:-}" ]; then
  cat <<METRICS | curl -fsS --data-binary @- "${PUSHGATEWAY_URL%/}/metrics/job/scorecode_backup" || echo "warning: pushgateway unreachable" >&2
# TYPE scorecode_backup_last_success_timestamp_seconds gauge
scorecode_backup_last_success_timestamp_seconds $(date +%s)
# TYPE scorecode_backup_size_bytes gauge
scorecode_backup_size_bytes $size
# TYPE scorecode_backup_duration_seconds gauge
scorecode_backup_duration_seconds $took
METRICS
fi
printf '{"backup":"%s","bytes":%s,"sha256":"%s","seconds":%s}\n' "$key" "$size" "$sha" "$took"
