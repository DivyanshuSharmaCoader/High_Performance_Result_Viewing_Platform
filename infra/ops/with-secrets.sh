#!/usr/bin/env bash
# The only way ScoreCode's tooling reads the master secrets file. It never prints a value.
#
#   infra/ops/with-secrets.sh check [group ...]   names only: ok / MISSING / PLACEHOLDER (exit 1 if a
#                                                 required one isn't ok). Groups: dns server storage
#                                                 backup email alerts admin registry optional
#   infra/ops/with-secrets.sh run -- <command>    runs <command> with the variables in its environment
#
# The file (default ~/.scorecode/scorecode.env, or SCORECODE_SECRETS_FILE) is read literally, line by
# line: KEY=value, comments on their own lines. It is never sourced or evaluated, so a value can hold
# any character and nothing in it runs. The file must be mode 600 and its directory 700.
# Works with macOS's bash 3.2.
set -euo pipefail
set +x  # never trace: a traced line would show values
FILE=${SCORECODE_SECRETS_FILE:-$HOME/.scorecode/scorecode.env}

# group:NAME:required|optional
SPEC="
dns:SCORECODE_DOMAIN:required
dns:CLOUDFLARE_API_TOKEN:required
dns:CLOUDFLARE_ZONE_ID:required
server:DEPLOY_HOST:required
server:DEPLOY_SSH_USER:required
server:DEPLOY_SSH_PORT:optional
server:DEPLOY_SSH_KEY_FILE:required
storage:FILES_S3_ENDPOINT:required
storage:FILES_S3_BUCKET:required
storage:FILES_S3_ACCESS_KEY_ID:required
storage:FILES_S3_SECRET_ACCESS_KEY:required
storage:FILES_S3_REGION:optional
backup:BACKUP_S3_ENDPOINT:optional
backup:BACKUP_S3_BUCKET:required
backup:BACKUP_S3_REGION:required
backup:BACKUP_S3_ACCESS_KEY_ID:required
backup:BACKUP_S3_SECRET_ACCESS_KEY:required
backup:BACKUP_AGE_RECIPIENT:required
email:SMTP_HOST:required
email:SMTP_PORT:optional
email:SMTP_USERNAME:required
email:SMTP_PASSWORD:required
email:MAIL_FROM:required
alerts:ALERT_EMAIL_TO:required
alerts:TELEGRAM_BOT_TOKEN:optional
alerts:TELEGRAM_CHAT_ID:optional
admin:PLATFORM_ADMIN_EMAIL:required
admin:PLATFORM_ADMIN_NAME:required
admin:PLATFORM_ADMIN_PASSWORD:required
registry:GHCR_USERNAME:optional
registry:GHCR_READ_TOKEN:optional
optional:SENTRY_DSN:optional
"

die() { echo "with-secrets: $*" >&2; exit 2; }

mode_of() { stat -f %Lp "$1" 2>/dev/null || stat -c %a "$1"; }

guard() {
  [ -f "$FILE" ] || die "no secrets file at $FILE (template: infra/ops/secrets.env.example)"
  [ "$(mode_of "$FILE")" = 600 ] || die "$FILE must be readable by you only: chmod 600 $FILE"
  [ "$(mode_of "$(dirname "$FILE")")" = 700 ] || die "its directory must be private: chmod 700 $(dirname "$FILE")"
}

load() {
  local line trimmed key val n=0 seen=" "
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n + 1))
    line=${line%$'\r'}
    trimmed="${line#"${line%%[![:space:]]*}"}"
    case "$trimmed" in '' | '#'*) continue ;; esac
    case "$line" in *=*) ;; *) echo "with-secrets: line $n has no '=' (skipped)" >&2; continue ;; esac
    key=${line%%=*}
    val=${line#*=}
    case "$key" in '' | *[!A-Za-z0-9_]* | [0-9]*) echo "with-secrets: line $n has an invalid name (skipped)" >&2; continue ;; esac
    case "$seen" in *" $key "*) echo "with-secrets: line $n sets $key again (this later line wins)" >&2 ;; esac
    seen="$seen$key "
    case "$val" in
      \"*\") val=${val#\"}; val=${val%\"} ;;
      \'*\') val=${val#\'}; val=${val%\'} ;;
    esac
    export "$key=$val"
  done < "$FILE"
}

status_of() {  # the status of variable $1, never its value
  local name=$1 val
  val=$(printenv "$name" 2>/dev/null || true)
  if [ -z "$val" ]; then echo MISSING; return; fi
  case "$val" in
    *[Ff][Aa][Kk][Ee]* | *CHANGE-ME*) echo PLACEHOLDER; return ;;
    *' #'*) echo "CHECK (contains ' #': comments must be on their own line)"; return ;;
  esac
  case "$name" in
    *_FILE)
      if [ ! -f "$val" ]; then echo "CHECK (no such file)"; return; fi
      case "$(mode_of "$val")" in 600 | 400) ;; *) echo "CHECK (key file should be chmod 600)"; return ;; esac
      ;;
  esac
  echo ok
}

check() {
  local want=" $* " bad=0 entry group name need st
  for entry in $SPEC; do
    group=${entry%%:*}; name=${entry#*:}; name=${name%%:*}; need=${entry##*:}
    if [ "$want" != "  " ] && [[ "$want" != *" $group "* ]]; then continue; fi
    st=$(status_of "$name")
    printf '%-9s %-28s %-9s %s\n' "$group" "$name" "$need" "$st"
    if [ "$need" = required ] && [ "$st" != ok ]; then bad=1; fi
  done
  return $bad
}

cmd=${1:-}
shift || true
case "$cmd" in
  check) guard; load; check "$@" ;;
  run)
    [ "${1:-}" = "--" ] && shift
    [ $# -gt 0 ] || die "usage: with-secrets.sh run -- <command>"
    guard; load
    exec "$@"
    ;;
  *) die "usage: with-secrets.sh check [group ...] | run -- <command>" ;;
esac
