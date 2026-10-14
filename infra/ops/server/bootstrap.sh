#!/usr/bin/env bash
# One-time server baseline for ScoreCode on Ubuntu 24.04 (P18.8; docs/runbooks/server-setup.md). Run as
# root, from the operator's machine:
#
#   infra/ops/server/remote.sh root inspect     # read-only: OS, disk, memory, Docker, ports, firewall
#   infra/ops/server/remote.sh root apply       # the baseline below; idempotent, safe to run again
#
# `apply`:
#   - unattended security updates (no automatic reboot), time sync on
#   - Docker Engine + compose plugin from Docker's apt repository, on at boot, logs rotated
#   - a `deploy` user (key login only, no password), allowed to run exactly two root-owned commands:
#     scorecode-deploy (deploy a released version) and scorecode-ctl (a fixed set of operations)
#   - /opt/scorecode (root-owned code, deploy-owned env/ and secrets/)
#   - firewall rules for 22, 80 and 443 written to ufw but NOT enabled: enabling it is gate (a)
# It never changes sshd, never disables root or password login, and never upgrades the OS release.
#
# Gate (a), only after the owner approved:
#   remote.sh root firewall-on    # ufw on, with the rules above (refuses unless 22/tcp is allowed)
#   remote.sh root harden-ssh     # keys only: no passwords for anyone, root by key only. Reverts itself
#   remote.sh root confirm-ssh    # in 3 minutes unless a NEW key login confirms it within that time
set -euo pipefail
mode=${1:-inspect}
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 2; }
here=$(cd "$(dirname "$0")" && pwd)

inspect() {
  echo "== system";  . /etc/os-release; echo "$PRETTY_NAME, kernel $(uname -r), $(nproc) vCPU, up $(uptime -p)"
  echo "== memory";  free -m | sed -n 1,3p
  echo "== disk";    df -h / | tail -1
  echo "== docker";  if command -v docker >/dev/null; then docker --version; docker compose version 2>/dev/null || true
                       docker ps --format '{{.Names}}  {{.Image}}  {{.Status}}' 2>/dev/null | head -20; else echo "not installed"; fi
  echo "== listening TCP ports"; ss -tlnpH 2>/dev/null | awk '{print $4, $6}' | sort -u | head -30
  echo "== firewall"; (ufw status verbose 2>/dev/null || echo "ufw not installed") | head -20
  echo "             nftables rules: $(nft list ruleset 2>/dev/null | grep -c . || echo 0) lines"
  echo "== login users"; awk -F: '$7 !~ /(nologin|false)$/ {print $1, $6, $7}' /etc/passwd
  echo "== sshd";   sshd -T 2>/dev/null | grep -E '^(port|permitrootlogin|passwordauthentication|pubkeyauthentication) ' || true
  echo "== services (failed)"; systemctl --failed --no-legend 2>/dev/null | head -10 || true
  echo "== time";   timedatectl show -p NTPSynchronized -p Timezone 2>/dev/null || true
  echo "== unattended upgrades"; (apt-config dump 2>/dev/null | grep -E 'APT::Periodic::(Update-Package-Lists|Unattended-Upgrade) ') || echo "not configured"
}

apply() {
  export DEBIAN_FRONTEND=noninteractive
  . /etc/os-release
  [ "${VERSION_ID:-}" = "24.04" ] || echo "warning: tested on Ubuntu 24.04, this is $PRETTY_NAME" >&2

  echo "== packages (security updates, time sync, firewall tool)"
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg unattended-upgrades ufw jq >/dev/null
  cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
  # Ubuntu's default 50unattended-upgrades takes the security pocket only; never reboot on our behalf.
  echo 'Unattended-Upgrade::Automatic-Reboot "false";' > /etc/apt/apt.conf.d/52scorecode-no-reboot
  # CERT-In directions (2022): clocks synchronised with NIC's or NPL's NTP servers (or ones traceable to
  # them); Ubuntu's pool stays as the fallback.
  install -d /etc/systemd/timesyncd.conf.d
  printf '[Time]\nNTP=samay1.nic.in samay2.nic.in time.nplindia.org\nFallbackNTP=ntp.ubuntu.com\n' \
    > /etc/systemd/timesyncd.conf.d/scorecode.conf
  timedatectl set-ntp true || echo "warning: could not switch on time sync" >&2
  systemctl restart systemd-timesyncd 2>/dev/null || true

  echo "== swap (2 GB; a memory spike slows the machine instead of freezing it)"
  # 2026-10-14: a load test beside production filled the 8 GB of RAM and, with no swap, the server stopped
  # answering for 20 minutes. Containers also have memory limits (compose.prod.yml).
  if ! swapon --show=NAME --noheadings | grep -q .; then
    fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
  echo 'vm.swappiness=10' > /etc/sysctl.d/60-scorecode-swap.conf && sysctl -q -p /etc/sysctl.d/60-scorecode-swap.conf

  echo "== Docker Engine"
  if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  fi
  mkdir -p /etc/docker
  want='{"log-driver":"json-file","log-opts":{"max-size":"20m","max-file":"5"},"live-restore":true}'
  if [ -f /etc/docker/daemon.json ]; then
    merged=$(jq -s '.[0] * .[1]' /etc/docker/daemon.json <(echo "$want"))
  else
    merged=$want
  fi
  if [ "$(jq -S . <<<"$merged")" != "$(jq -S . /etc/docker/daemon.json 2>/dev/null || true)" ]; then
    jq . <<<"$merged" > /etc/docker/daemon.json
    systemctl restart docker  # live-restore keeps running containers up across this restart
  fi
  systemctl enable --now containerd docker >/dev/null

  echo "== deploy user"
  id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
  passwd -l deploy >/dev/null  # no password: keys only
  install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
  touch /home/deploy/.ssh/authorized_keys
  # Public keys arrive on stdin of `remote.sh root add-key` (never a private key); see below.
  chown deploy:deploy /home/deploy/.ssh/authorized_keys
  chmod 600 /home/deploy/.ssh/authorized_keys
  gpasswd -d deploy docker >/dev/null 2>&1 || true  # the docker group is root in all but name

  echo "== /opt/scorecode"
  install -d -m 755 -o root -g root /opt/scorecode /opt/scorecode/releases /etc/scorecode
  install -d -m 700 -o deploy -g deploy /opt/scorecode/env
  install -d -m 750 -o root -g nogroup /opt/scorecode/secrets  # Alertmanager (nobody) reads its files here
  install -d -m 750 -o root -g root /opt/scorecode/certs
  install -m 755 -o root -g root "$here/scorecode-deploy" /usr/local/sbin/scorecode-deploy
  install -m 755 -o root -g root "$here/scorecode-ctl" /usr/local/sbin/scorecode-ctl
  install -d -m 755 -o root -g root /usr/local/lib/scorecode /usr/local/lib/scorecode/templates
  install -m 755 -o root -g root "$here/render-env.py" /usr/local/lib/scorecode/render-env.py
  install -m 644 -o root -g root "$here"/../env/*.env.example /usr/local/lib/scorecode/templates/
  # Cloudflare's Origin CA root (public): the smoke tests go straight to this machine and trust it.
  curl -fsSL https://developers.cloudflare.com/ssl/static/origin_ca_ecc_root.pem -o /opt/scorecode/certs/origin-ca.pem
  [ -f /etc/scorecode/registry ] || echo "ghcr.io/divyanshusharmacoader" > /etc/scorecode/registry
  cat > /etc/sudoers.d/scorecode <<'EOF'
# The deploy user may run exactly these two root-owned programs (P18.8). Nothing else, no shell.
deploy ALL=(root) NOPASSWD: /usr/local/sbin/scorecode-deploy, /usr/local/sbin/scorecode-ctl
Defaults:deploy !requiretty
EOF
  chmod 440 /etc/sudoers.d/scorecode
  visudo -cf /etc/sudoers.d/scorecode >/dev/null

  echo "== daily log archive (kept 365 days on this server)"
  printf '[Unit]\nDescription=Archive yesterday'"'"'s ScoreCode container logs\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/scorecode-ctl archive-logs\n' \
    > /etc/systemd/system/scorecode-logs.service
  printf '[Unit]\nDescription=Archive ScoreCode logs daily\n[Timer]\nOnCalendar=*-*-* 00:20:00 UTC\nPersistent=true\n[Install]\nWantedBy=timers.target\n' \
    > /etc/systemd/system/scorecode-logs.timer
  systemctl daemon-reload
  systemctl enable --now scorecode-logs.timer >/dev/null

  echo "== firewall rules (22, 80, 443; ufw is switched on separately, gate a)"
  if ! ufw status | grep -q "Status: active"; then  # an active firewall keeps its rules; we only add ours
    ufw default deny incoming >/dev/null
    ufw default allow outgoing >/dev/null
  fi
  ufw allow 22/tcp comment 'ssh' >/dev/null
  ufw allow 80/tcp comment 'http (Cloudflare redirects to https)' >/dev/null
  ufw allow 443/tcp comment 'https' >/dev/null
  ufw status verbose | head -3
  echo "   enable with: infra/ops/server/remote.sh root firewall-on   (gate a: needs the owner's approval)"

  echo "== done"
  inspect
}

add_key() {  # one public key from stdin into deploy's authorized_keys
  local key
  key=$(head -c 2000)
  [[ $key =~ ^(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa)\ [A-Za-z0-9+/=]+(\ .*)?$ ]] || { echo "not a public key" >&2; exit 2; }
  grep -qxF "$key" /home/deploy/.ssh/authorized_keys || echo "$key" >> /home/deploy/.ssh/authorized_keys
  echo "deploy now has $(grep -c . /home/deploy/.ssh/authorized_keys) key(s)"
}

firewall_on() {  # gate (a): only after the owner approved, and with SSH confirmed allowed
  # `ufw status` lists rules only while active; `show added` lists them either way.
  { ufw status | grep -qE '^22/tcp +ALLOW' || ufw show added | grep -qE 'allow 22/tcp'; } \
    || { echo "refusing: no rule allows 22/tcp" >&2; exit 2; }
  ufw --force enable
  ufw status verbose
}

HARDEN=/etc/ssh/sshd_config.d/00-scorecode.conf  # 00-: sshd takes the first value, before cloud-init's 50-

harden_ssh() {  # gate (a)
  for f in /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys; do
    grep -qE '^(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa) ' "$f" 2>/dev/null || { echo "refusing: no key in $f" >&2; exit 2; }
  done
  printf '%s\n' '# ScoreCode (gate a): keys only.' 'PasswordAuthentication no' 'KbdInteractiveAuthentication no' \
    'PermitRootLogin prohibit-password' 'PermitEmptyPasswords no' > "$HARDEN.new"
  mv "$HARDEN.new" "$HARDEN"
  sshd -t || { rm -f "$HARDEN"; echo "sshd rejected the settings; nothing changed" >&2; exit 2; }
  # The safety net: unless confirm-ssh runs within 3 minutes, the old settings come back.
  systemctl stop scorecode-ssh-revert.timer 2>/dev/null || true
  systemd-run --quiet --unit scorecode-ssh-revert --on-active=180 /bin/sh -c "rm -f $HARDEN && systemctl reload ssh"
  systemctl reload ssh
  sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin) '
  echo "applied; reverts at $(date -u -d '+3 min' +%T) UTC unless confirm-ssh runs from a new key login"
}

confirm_ssh() {
  [ -f "$HARDEN" ] || { echo "nothing to confirm: the settings were reverted" >&2; exit 2; }
  systemctl stop scorecode-ssh-revert.timer 2>/dev/null || true
  echo "kept: $(sshd -T | grep -E '^(passwordauthentication|permitrootlogin) ' | tr '\n' ' ')"
}

case "$mode" in
  inspect) inspect ;;
  apply) apply ;;
  add-key) add_key ;;
  firewall-on) firewall_on ;;
  harden-ssh) harden_ssh ;;
  confirm-ssh) confirm_ssh ;;
  *) echo "usage: bootstrap.sh inspect|apply|add-key|firewall-on|harden-ssh|confirm-ssh" >&2; exit 2 ;;
esac
