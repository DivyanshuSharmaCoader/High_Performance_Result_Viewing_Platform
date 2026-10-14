#!/usr/bin/env bash
# Run a server step over SSH, with the host, port and key from the secrets loader (P18.8).
#
#   infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh root inspect      # read-only
#   infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh root apply        # the baseline
#   infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh root add-key < key.pub
#   infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh root firewall-on  # gate (a)
#   infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh root harden-ssh   # gate (a), then confirm-ssh
#   infra/ops/with-secrets.sh run -- infra/ops/server/remote.sh deploy ctl status # sudo scorecode-ctl status
#
# Root steps copy infra/ops/server and the env templates to a private temporary directory on the
# server and run bootstrap.sh there. Host keys are checked strictly against known_hosts.
set -euo pipefail
who=${1:?root|deploy}; shift
: "${DEPLOY_HOST:?run under infra/ops/with-secrets.sh}" "${DEPLOY_SSH_KEY_FILE:?}"
port=${DEPLOY_SSH_PORT:-22}
cd "$(dirname "$0")/../../.."
ssh_() {
  ssh -i "$DEPLOY_SSH_KEY_FILE" -p "$port" -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=yes \
    -o ServerAliveInterval=20 "$1@$DEPLOY_HOST" "${@:2}"
}
# macOS's bsdtar adds extended attributes that GNU tar on the server warns about; leave them out.
pack() {
  if tar --version 2>/dev/null | grep -q bsdtar; then COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -cf - "$@"
  else tar cf - "$@"; fi
}
# The deploy account has its own key (never root's), when there is one.
deploy_key=${DEPLOY_USER_KEY_FILE:-$HOME/.ssh/scorecode_deploy}
case "$who" in
  root)
    mode=${1:?inspect|apply|add-key|firewall-on|harden-ssh|confirm-ssh}
    [[ $mode =~ ^(inspect|apply|add-key|firewall-on|harden-ssh|confirm-ssh)$ ]] || exit 2
    if [ "$mode" = add-key ]; then
      key=$(cat)
      pack infra/ops/server | ssh_ root "d=\$(mktemp -d) && tar xf - -C \$d && printf '%s\n' '$key' | bash \$d/infra/ops/server/bootstrap.sh add-key; rm -rf \$d"
    else
      pack infra/ops/server infra/ops/env | ssh_ root "d=\$(mktemp -d) && tar xf - -C \$d && cd \$d && bash infra/ops/server/bootstrap.sh $mode; rc=\$?; rm -rf \$d; exit \$rc"
    fi
    ;;
  deploy)
    [ "${1:-}" = ctl ] || exit 2; shift
    [ -f "$deploy_key" ] && DEPLOY_SSH_KEY_FILE=$deploy_key
    ssh_ deploy sudo /usr/local/sbin/scorecode-ctl "$@"
    ;;
  *) exit 2 ;;
esac
