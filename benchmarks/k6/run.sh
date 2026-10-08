#!/usr/bin/env bash
# One k6 run of the result-day journey with container resource sampling (docs/11 §4, P10.6).
#
#   benchmarks/k6/run.sh <A|B|smoke> <preauth|cold> <run-number>
#
# Needs the container stack (`make stack`) and the synthetic data (backend/scripts/loadtest_data.py).
# Writes results/runs/<tag>.txt (summary), <tag>.json (k6 data) and <tag>.csv (docker stats every 5 s)
# under BENCH_DIR (default: this repo's benchmarks/; results/runs/ is git-ignored, so copy the runs a
# report relies on next to it). Docker Desktop may be unable to mount some
# folders (macOS privacy, e.g. ~/Desktop): then copy k6/ and data/ to a folder it can mount and set BENCH_DIR.
#
# Refuses to run on battery: macOS Low Power Mode cut scenario B's throughput by 32–44% on the same
# laptop (benchmarks/results/2026-10-08-k6-scenarios-A-B.md). FORCE=1 runs anyway, for a labelled control.
set -euo pipefail

scenario=${1:?scenario A, B or smoke}
variant=${2:?variant preauth or cold}
n=${3:?run number}
tag="$scenario-$variant-$n"
here=$(cd "$(dirname "$0")/.." && pwd)
bench=${BENCH_DIR:-$here}
network=${K6_NETWORK:-scorecode_default}

if command -v pmset >/dev/null && pmset -g batt | grep -q "Battery Power" && [ "${FORCE:-0}" != 1 ]; then
  echo "On battery power: results would not be comparable (set FORCE=1 to run a labelled control)." >&2
  exit 2
fi

runs="$bench/results/runs"
mkdir -p "$runs"
echo "== $tag $(date -u +%FT%TZ) power: $(pmset -g batt 2>/dev/null | head -1 | sed "s/.*'\(.*\)'.*/\1/" || echo n/a)"

(
  while true; do
    docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}}" 2>/dev/null \
      | grep scorecode | sed "s/^/$(date +%s),/" >> "$runs/$tag.csv"
    sleep 5
  done
) &
sampler=$!
trap 'kill $sampler 2>/dev/null || true' EXIT

docker run --rm --network "$network" -v "$bench:/bench" grafana/k6:latest run -q \
  -e SCENARIO="$scenario" -e VARIANT="$variant" -e VUS="${VUS:-1000}" -e SUMMARY="/bench/results/runs/$tag.json" \
  /bench/k6/student-journey.js | tee "$runs/$tag.txt"
