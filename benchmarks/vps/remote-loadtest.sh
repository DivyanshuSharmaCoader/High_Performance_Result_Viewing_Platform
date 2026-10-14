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
# (The pid file's path is absolute: "cd x && cmd & echo $!" backgrounds the whole list, so a relative
# path landed in the home directory, and "no pid file" read as "finished".)
ssh_ "cd $dir || exit 1; RUNS='${RUNS:-B:cold:1 B:preauth:1}' VUS=${VUS:-1000} HOLD=${HOLD:-5m} STUDENTS=${STUDENTS:-8000} nohup bash benchmarks/vps/run-on-vps.sh > $dir/run.log 2>&1 < /dev/null & echo \$! > $dir/run.pid; echo started"
ssh_ "test -s $dir/run.pid" || { echo "no pid file: not polling" >&2; exit 1; }
# Finished only when the server says so: an unreachable server (or a missing pid file) is not "done".
while :; do
  state=$(ssh_ "if [ ! -s $dir/run.pid ]; then echo nopid; elif kill -0 \$(cat $dir/run.pid) 2>/dev/null; then echo running; else echo done; fi" 2>/dev/null || echo unreachable)
  [ "$state" = done ] && break
  [ "$state" = nopid ] && { echo "pid file vanished; not removing anything" >&2; exit 1; }
  sleep 60; ssh_ "tail -1 $dir/run.log" 2>/dev/null || true
done
ssh_ "cat $dir/run.log" | tail -40
ssh_ "grep -q '== done' $dir/run.log" || status=1
mkdir -p benchmarks/results/runs-vps
ssh_ "tar cf - -C $dir/benchmarks/results runs" | tar xf - -C benchmarks/results/runs-vps
ssh_ "rm -rf $dir"
echo "results: benchmarks/results/runs-vps/runs (status ${status:-0})"
exit "${status:-0}"
