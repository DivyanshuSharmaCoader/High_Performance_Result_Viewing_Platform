#!/usr/bin/env bash
# Deploy a released version on the server (P16.3; runbook docs/runbooks/deploy-and-rollback.md).
#
#   infra/ops/deploy.sh v1.2.3          # from /opt/scorecode, which holds compose.prod.yml, env/, certs/
#
# 1. Pull the version's images (built, scanned and pushed by release.yml).
# 2. Back up with the running version, as a restore point from before any migration.
# 3. Start the new version: `migrate` runs first (expand-only migrations, so the previous version still
#    works on the new schema), then the API (healthy before the edge sends it traffic), worker, edge.
# 4. Smoke test through the edge on this machine.
# 5. On failure, start the previous version again, and say so.
#
# SKIP_BACKUP=1 skips step 2 (first install, or rehearsals). SMOKE_CACERT points at the CA that signed the
# origin certificate (Cloudflare's Origin CA root), since this check bypasses Cloudflare.
set -euo pipefail
version=${1:?usage: deploy.sh <version>}
cd "$(dirname "$0")/../.."
[ -f env/deploy.env ] || { echo "env/deploy.env missing (templates: infra/ops/env/)" >&2; exit 2; }
domain=$(grep -E '^BASE_DOMAIN=' env/deploy.env | head -1 | cut -d= -f2 | awk '{print $1}')

files=()  # COMPOSE_FILES=a.yml:b.yml adds overrides (the CI rehearsal adds local object storage and mail)
IFS=: read -r -a extra <<< "${COMPOSE_FILES:-compose.prod.yml}"
for f in "${extra[@]}"; do files+=(-f "$f"); done
dc() {  # dc <version> <compose args...>
  local v=$1; shift
  SCORECODE_VERSION=$v docker compose "${files[@]}" --env-file env/deploy.env "$@"
}
log() { echo "$(date -u +%FT%TZ) $*" | tee -a deploy.log; }
smoke() {
  SMOKE_BASE_DOMAIN=$domain SMOKE_SCHEME=https SMOKE_PORT=443 SMOKE_CONNECT_TO=127.0.0.1:443 \
    SMOKE_CACERT=${SMOKE_CACERT:-} SMOKE_TENANT=${SMOKE_TENANT-thapar} infra/ops/smoke.sh
}

previous=$(cat .deployed-version 2>/dev/null || true)
log "deploying $version (running: ${previous:-nothing})"
[ "${SKIP_PULL:-0}" = 1 ] || dc "$version" pull --quiet

if [ -n "$previous" ] && [ "${SKIP_BACKUP:-0}" != 1 ]; then
  log "restore point: backup with $previous"
  dc "$previous" run --rm backup backup.sh | tee -a deploy.log
fi

started=$(date +%s)
if dc "$version" up -d --wait --remove-orphans && smoke; then
  echo "$version" > .deployed-version
  log "deployed $version in $(( $(date +%s) - started )) s"
  exit 0
fi

log "FAILED: $version did not come up or failed the smoke test"
dc "$version" logs --tail 80 migrate api worker proxy >> deploy.log 2>&1 || true
if [ -n "$previous" ]; then
  dc "$previous" up -d --wait --remove-orphans && smoke && log "rolled back to $previous" \
    || log "ROLLBACK FAILED: $previous is not healthy either; follow docs/runbooks/deploy-and-rollback.md"
fi
exit 1
