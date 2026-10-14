#!/usr/bin/env bash
# The result-day load test (perf.yml's journey) on the production VPS itself, beside production, without
# touching it (P18.11). Run as root from a source tree copied by benchmarks/vps/remote-loadtest.sh.
#
# Isolation: its own Compose project (scorecodeperf: own containers, network and volumes), every port bound
# to 127.0.0.1 (compose.yml), synthetic data only, and nothing addresses a container by name: production's
# containers are also called scorecode-*. Removed at the end: containers, volumes, the images it built and
# their build cache. Production's pulled images are untouched.
#
#   RUNS="B:cold:1 B:preauth:1" VUS=1000 bash benchmarks/vps/run-on-vps.sh
set -euo pipefail
export COMPOSE_PROJECT_NAME=scorecodeperf
cd "$(dirname "$0")/../.."
RUNS=${RUNS:-"B:cold:1 B:preauth:1"}
VUS=${VUS:-1000}
out=benchmarks/results/runs
mkdir -p "$out" benchmarks/data && chmod 777 "$out" benchmarks/data
# Memory limits for the test stack too (compose.yml has none), and a watchdog: on 2026-10-14 the first run,
# beside production on an 8 GB server without swap, starved the machine for 20 minutes.
cat > perf-limits.yml <<'YML'
services:
  api: { mem_limit: 1536m }
  worker: { mem_limit: 2g, cpus: 1.0, cpu_shares: 512 }
  postgres: { mem_limit: 1g }
  s3: { mem_limit: 512m }
  proxy: { mem_limit: 256m }
YML
dc() { docker compose -f compose.yml -f perf-limits.yml "$@"; }
(
  while sleep 5; do
    avail=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
    if [ "$avail" -lt 700 ]; then
      echo "WATCHDOG: only ${avail} MB available; stopping the test stack to protect production" | tee -a "$out/watchdog.txt"
      docker ps -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" | xargs -r docker kill >/dev/null
      docker ps -q --filter ancestor=grafana/k6:latest | xargs -r docker kill >/dev/null
      break
    fi
  done
) &
watchdog=$!
q() { dc exec -T postgres psql -U postgres -d scorecode -Atc "$1"; }
cleanup() {
  dc --profile app down -v --rmi local --remove-orphans >/dev/null 2>&1 || true
  docker builder prune -f >/dev/null 2>&1 || true
}
trap 'kill $watchdog 2>/dev/null || true; cleanup' EXIT

{
  echo "commit $(cat .commit 2>/dev/null || echo unknown)"
  echo "host $(hostname); $(nproc) vCPU; $(lscpu | grep 'Model name' | sed 's/  */ /g')"
  free -m | head -2
  echo "production containers running beside it: $(docker ps --filter label=com.docker.compose.project=scorecode -q | wc -l)"
} | tee "$out/machine.txt"

echo "== build and start (project $COMPOSE_PROJECT_NAME)"
dc --profile app up -d --build --wait --quiet-pull 2>&1 | tail -3
dc ps --format '{{.Service}} {{.Status}}'

echo "== synthetic data: 8,000 students, published"
dc --profile app run --rm -T -v "$PWD/backend/scripts:/scripts:ro" -v "$PWD/benchmarks/data:/data" \
  --entrypoint python api /scripts/loadtest_data.py --students 8000 --sessions "$(( VUS > 1000 ? VUS : 1000 ))" --out /data

echo "== background work (marksheets, notifications)"
started=$(date +%s)
until [ "$(q "SELECT count(*) FROM jobs WHERE status IN ('queued','running')")" = 0 ]; do
  [ $(( $(date +%s) - started )) -gt 3600 ] && { echo "background work still running after 60 min"; break; }
  sleep 10
done
{
  echo "background work after publishing 8,000 results: $(( $(date +%s) - started )) s"
  q "SELECT status, count(*) FROM marksheet_documents GROUP BY status"
  q "SELECT 'marksheet render span (s): ' || round(extract(epoch FROM max(rendered_at) - min(created_at))) FROM marksheet_documents"
  q "SELECT 'duplicate notifications: ' || count(*) FROM (SELECT user_id, dedupe_key FROM notifications GROUP BY 1, 2 HAVING count(*) > 1) d"
} | tee "$out/background.txt"
q "SELECT pg_stat_statements_reset()" >/dev/null

# Every 10 s: memory, swap, load, and the share of CPU time in the interval that the host withheld (steal).
( prev=$(awk '/^cpu / {t=0; for (i=2; i<=NF; i++) t+=$i; print t, $9}' /proc/stat)
  while sleep 10; do
    cur=$(awk '/^cpu / {t=0; for (i=2; i<=NF; i++) t+=$i; print t, $9}' /proc/stat)
    steal=$(echo "$prev $cur" | awk '{d=$3-$1; printf "%.0f", d>0 ? 100*($4-$2)/d : 0}')
    prev=$cur
    echo "$(date +%s) $(awk '/MemAvailable|SwapTotal|SwapFree/ {printf "%s=%dMB ", $1, $2/1024}' /proc/meminfo) load=$(cut -d' ' -f1 /proc/loadavg) steal=${steal}%"
  done ) > "$out/host-memory.txt" &
sampler=$!
network="${COMPOSE_PROJECT_NAME}_default"
for spec in $RUNS; do
  IFS=: read -r scenario variant times <<< "$spec"
  for i in $(seq 1 "$times"); do
    since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    FORCE=1 K6_NETWORK=$network BENCH_DIR="$PWD/benchmarks" VUS=$VUS HOLD=${HOLD:-5m} benchmarks/k6/run.sh "$scenario" "$variant" "$i"
    dc --profile app logs --no-log-prefix --since "$since" api 2>/dev/null > "$out/api-$scenario-$variant-$i.log" || true
    python3 benchmarks/k6/timeline.py --latency < "$out/api-$scenario-$variant-$i.log" > "$out/server-$scenario-$variant-$i.txt" || true
    python3 benchmarks/k6/timeline.py < "$out/api-$scenario-$variant-$i.log" > "$out/timeline-$scenario-$variant-$i.txt" || true
    rm -f "$out/api-$scenario-$variant-$i.log"
  done
done
q "SELECT calls, round(total_exec_time::numeric, 1) AS total_ms, round(mean_exec_time::numeric, 3) AS mean_ms, left(query, 120)
   FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 15" > "$out/pg_stat_statements.txt"
kill $sampler 2>/dev/null || true
echo "== done; results in $out"
