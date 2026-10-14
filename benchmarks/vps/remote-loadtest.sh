#!/usr/bin/env bash
# Copy this commit's source to the VPS and run benchmarks/vps/run-on-vps.sh there as root (P18.11); fetch
# the results back to benchmarks/results/runs-vps/ (git-ignored raw data). Through the secrets loader:
#
#   infra/ops/with-secrets.sh run -- benchmarks/vps/remote-loadtest.sh
set -euo pipefail
: "${DEPLOY_HOST:?run under infra/ops/with-secrets.sh}" "${DEPLOY_SSH_KEY_FILE:?}"
cd "$(dirname "$0")/../.."
ssh_() { ssh -i "$DEPLOY_SSH_KEY_FILE" -p "${DEPLOY_SSH_PORT:-22}" -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o ServerAliveInterval=30 "root@$DEPLOY_HOST" "$@"; }
dir=/opt/scorecode-perf
commit=$(git rev-parse --short HEAD)
{ git archive HEAD; } | ssh_ "rm -rf $dir && mkdir -p $dir && tar xf - -C $dir && echo $commit > $dir/.commit"
# Detached on the server (nohup), so a dropped SSH connection can't stop it half-way; polled until done.
ssh_ "cd $dir && RUNS='${RUNS:-B:cold:1 B:preauth:1}' VUS=${VUS:-1000} nohup bash benchmarks/vps/run-on-vps.sh > run.log 2>&1 < /dev/null & echo \$! > run.pid; echo started"
until ssh_ "! kill -0 \$(cat $dir/run.pid) 2>/dev/null" 2>/dev/null; do sleep 60; ssh_ "tail -1 $dir/run.log" 2>/dev/null || true; done
ssh_ "cat $dir/run.log" | tail -40
ssh_ "grep -q '== done' $dir/run.log" || status=1
mkdir -p benchmarks/results/runs-vps
ssh_ "tar cf - -C $dir/benchmarks/results runs" | tar xf - -C benchmarks/results/runs-vps
ssh_ "rm -rf $dir"
echo "results: benchmarks/results/runs-vps/runs (status ${status:-0})"
exit "${status:-0}"
