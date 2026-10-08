#!/usr/bin/env bash
# Smoke test of a running ScoreCode deployment (P16.2): every host answers, with its security headers.
#
#   SMOKE_BASE_DOMAIN=scorecode.example SMOKE_SCHEME=https SMOKE_TENANT=thapar infra/ops/smoke.sh
#   infra/ops/smoke.sh        # the local stack: http://*.localhost:8080, tenant thapar
#
# Exits non-zero on the first failure and prints what failed. Read-only: it signs nobody in and writes
# nothing, so it is safe against production.
set -euo pipefail
domain=${SMOKE_BASE_DOMAIN:-localhost}
scheme=${SMOKE_SCHEME:-http}
port=${SMOKE_PORT:-$([ "$scheme" = http ] && echo 8080 || echo 443)}
tenant=${SMOKE_TENANT-thapar}  # SMOKE_TENANT= (empty) skips the tenant's own checks: a first install
suffix=$([ "$port" = 443 ] || [ "$port" = 80 ] && echo "" || echo ":$port")
connect=()  # extra curl options: where to connect, and which CA to trust
[ -n "${SMOKE_CONNECT_TO:-}" ] && connect+=(--connect-to "::${SMOKE_CONNECT_TO}")  # e.g. 127.0.0.1:443
[ -n "${SMOKE_CACERT:-}" ] && connect+=(--cacert "$SMOKE_CACERT")  # an origin certificate's CA
failures=0

check() {  # check <name> <url> <expected status> [header regex...]
  local name=$1 url=$2 want=$3; shift 3
  local headers status
  headers=$(curl -sS -o /dev/null -D - --max-time 10 "${connect[@]}" "$url") || { echo "FAIL $name: $url unreachable"; failures=$((failures + 1)); return; }
  status=$(printf '%s' "$headers" | head -1 | awk '{print $2}')
  if [ "$status" != "$want" ]; then echo "FAIL $name: $url answered $status, expected $want"; failures=$((failures + 1)); return; fi
  for pattern in "$@"; do
    if ! printf '%s' "$headers" | tr -d '\r' | grep -qiE "$pattern"; then
      echo "FAIL $name: $url is missing header /$pattern/"; failures=$((failures + 1)); return
    fi
  done
  echo "ok   $name ($status)"
}

body() {  # body <name> <url> <regex>
  local out
  out=$(curl -sS --max-time 10 "${connect[@]}" "$2") || { echo "FAIL $1: unreachable"; failures=$((failures + 1)); return; }
  if printf '%s' "$out" | grep -qE "$3"; then echo "ok   $1"; else echo "FAIL $1: body doesn't match /$3/"; failures=$((failures + 1)); fi
}

t="$scheme://${tenant:-any-institution}.$domain$suffix"
check "tenant app" "$t/login" 200 '^content-security-policy: .*script-src .self.' '^x-content-type-options: nosniff' '^cross-origin-opener-policy: same-origin' '^cache-control: no-cache'
[ -z "$tenant" ] || body "tenant config" "$t/api/v1/tenant/config" "\"slug\":\"$tenant\""
check "unknown tenant" "$scheme://no-such-institution-smoke.$domain$suffix/api/v1/tenant/config" 404
check "verify page" "$scheme://verify.$domain$suffix/v" 200 '^referrer-policy: no-referrer' '^x-robots-tag: noindex'
check "marketing site" "$scheme://$domain$suffix/" 200 '^x-frame-options: DENY'
check "platform console" "$scheme://admin.$domain$suffix/login" 200
check "plans API" "$scheme://$domain$suffix/api/v1/plans" 200
check "metrics not public" "$t/metrics" 200 '^content-type: text/html'  # the SPA, never Prometheus text
if [ "$scheme" = https ]; then
  check "HSTS" "$t/login" 200 '^strict-transport-security: max-age='
fi

if [ "$failures" -gt 0 ]; then echo "$failures check(s) failed"; exit 1; fi
echo "smoke: all checks passed against $scheme://*.$domain$suffix"
