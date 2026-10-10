#!/usr/bin/env python3
"""Write the server's settings files from the operator's values (root-owned; P18.8, docs/configuration.md).

    infra/ops/with-secrets.sh run -- python3 infra/ops/push-env.py     # on the operator's machine
      → ssh deploy@server sudo scorecode-ctl render-env < KEY=VALUE lines

Reads ``KEY=VALUE`` lines on stdin: only the names in ``ALLOWED``, one per line, no control characters,
so a value can't smuggle in a second setting. Server-side secrets (database passwords, the app's keys) are
generated here once, kept in env/generated.env, and never leave the machine. Writes, from the templates
installed with this script:

    /opt/scorecode/env/{app,db,backup,deploy,monitoring}.env   deploy:deploy 0600
    /opt/scorecode/secrets/alertmanager.yml, alert_smtp_password   root:65534 0640 (Alertmanager runs as nobody)

and prints only the names of the files and settings it wrote, never a value.
"""

from __future__ import annotations

import grp
import os
import pwd
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(os.environ.get("SCORECODE_ROOT", "/opt/scorecode"))
TEMPLATES = Path(os.environ.get("SCORECODE_TEMPLATES", "/usr/local/lib/scorecode/templates"))
ALLOWED = {
    "SCORECODE_DOMAIN",
    "FILES_S3_ENDPOINT", "FILES_S3_BUCKET", "FILES_S3_ACCESS_KEY_ID", "FILES_S3_SECRET_ACCESS_KEY", "FILES_S3_REGION",
    "BACKUP_S3_ENDPOINT", "BACKUP_S3_BUCKET", "BACKUP_S3_REGION", "BACKUP_S3_ACCESS_KEY_ID",
    "BACKUP_S3_SECRET_ACCESS_KEY", "BACKUP_AGE_RECIPIENT",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_FROM",
    "ALERT_EMAIL_TO", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "SENTRY_DSN",
    "API_WORKERS", "PDF_PROCESSES",
}
REQUIRED = ALLOWED - {
    "BACKUP_S3_ENDPOINT", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SENTRY_DSN", "FILES_S3_REGION",
    "SMTP_PORT", "API_WORKERS", "PDF_PROCESSES",
}
GENERATED = (
    "POSTGRES_PASSWORD", "SCORECODE_MIGRATOR_PASSWORD", "SCORECODE_APP_PASSWORD", "SCORECODE_PLATFORM_PASSWORD",
    "SCORECODE_BACKUP_PASSWORD", "SCORECODE_MONITOR_PASSWORD", "SCORECODE_SECRET_KEY", "SCORECODE_ABUSE_SIGNAL_KEY",
)
# Cloudflare's published ranges (https://www.cloudflare.com/ips/), so the edge sees real client addresses.
CLOUDFLARE = (
    "173.245.48.0/20 103.21.244.0/22 103.22.200.0/22 103.31.4.0/22 141.101.64.0/18 108.162.192.0/18 "
    "190.93.240.0/20 188.114.96.0/20 197.234.240.0/22 198.41.128.0/17 162.158.0.0/15 104.16.0.0/13 "
    "104.24.0.0/14 172.64.0.0/13 131.0.72.0/22"
)


def die(msg: str) -> None:
    print(f"render-env: {msg}", file=sys.stderr)
    sys.exit(2)


def read_input() -> dict[str, str]:
    out: dict[str, str] = {}
    for n, line in enumerate(sys.stdin.read(200_000).split("\n"), 1):
        if not line.strip():
            continue
        key, sep, val = line.partition("=")
        if not sep or key not in ALLOWED:
            die(f"line {n}: not an accepted setting")
        if any(c in val for c in "\r\0") or any(ord(c) < 32 and c != "\t" for c in val):
            die(f"line {n} ({key}): control characters are not allowed")
        out[key] = val.strip()
    missing = sorted(k for k in REQUIRED if not out.get(k))
    if missing:
        die("missing: " + ", ".join(missing))
    return out


def generated(path: Path) -> dict[str, str]:
    have: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            k, _, v = line.partition("=")
            if k:
                have[k] = v
    new = [k for k in GENERATED if not have.get(k)]
    for k in new:
        have[k] = secrets.token_urlsafe(36)
    if new or not path.exists():
        write(path, "".join(f"{k}={have[k]}\n" for k in GENERATED), owner="root", group="root", mode=0o600)
        print(f"generated once and kept on this server: {', '.join(new) or '(none new)'}")
    return have


def write(path: Path, text: str, *, owner: str, group: str, mode: int) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chown(tmp, pwd.getpwnam(owner).pw_uid, grp.getgrnam(group).gr_gid)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def fill(template: str, values: dict[str, str | None]) -> str:
    out = []
    for line in template.splitlines():
        m = re.match(r"^#?\s?([A-Z_0-9]+)=", line)
        if m and m[1] in values:
            if values[m[1]] is None:
                continue  # left out: an empty value can mean something (e.g. "log in as ''")
            line = f"{m[1]}={values[m[1]]}"
        out.append(line)
    return "\n".join(out) + "\n"


def address(mail_from: str) -> str:
    m = re.search(r"<([^>]+)>", mail_from)
    return m[1] if m else mail_from


def main() -> None:
    if os.geteuid() != 0:
        die("run as root (through sudo scorecode-ctl render-env)")
    v = read_input()
    env_dir, sec_dir = ROOT / "env", ROOT / "secrets"
    g = generated(env_dir / "generated.env")
    domain = v["SCORECODE_DOMAIN"]
    url = "postgresql+asyncpg://{role}:{pw}@postgres:5432/scorecode"
    smtp_port = v.get("SMTP_PORT") or "587"
    if smtp_port == "465":
        die("SMTP_PORT 465 (implicit TLS) is not supported; use 587 with STARTTLS")
    values: dict[str, str | None] = {
        # deploy.env (compose interpolation)
        "BASE_DOMAIN": domain,
        "TRUSTED_PROXIES": f"private_ranges {CLOUDFLARE}",
        "API_WORKERS": v.get("API_WORKERS") or "2",
        "PDF_PROCESSES": v.get("PDF_PROCESSES") or "1",
        # app.env
        "SCORECODE_BASE_DOMAIN": domain,
        "SCORECODE_SECRET_KEY": g["SCORECODE_SECRET_KEY"],
        "SCORECODE_ABUSE_SIGNAL_KEY": g["SCORECODE_ABUSE_SIGNAL_KEY"],
        "SCORECODE_DATABASE_URL_APP": url.format(role="scorecode_app", pw=g["SCORECODE_APP_PASSWORD"]),
        "SCORECODE_DATABASE_URL_PLATFORM": url.format(role="scorecode_platform", pw=g["SCORECODE_PLATFORM_PASSWORD"]),
        "SCORECODE_DATABASE_URL_MIGRATOR": url.format(role="scorecode_migrator", pw=g["SCORECODE_MIGRATOR_PASSWORD"]),
        "SCORECODE_S3_ENDPOINT_URL": v["FILES_S3_ENDPOINT"],
        "SCORECODE_S3_PUBLIC_ENDPOINT_URL": v["FILES_S3_ENDPOINT"],
        "SCORECODE_S3_REGION": v.get("FILES_S3_REGION") or "auto",
        "SCORECODE_S3_BUCKET": v["FILES_S3_BUCKET"],
        "SCORECODE_S3_ACCESS_KEY": v["FILES_S3_ACCESS_KEY_ID"],
        "SCORECODE_S3_SECRET_KEY": v["FILES_S3_SECRET_ACCESS_KEY"],
        "SCORECODE_SMTP_HOST": v["SMTP_HOST"],
        "SCORECODE_SMTP_PORT": smtp_port,
        # STARTTLS on the submission ports (Brevo: 587). Port 465 (implicit TLS) is not supported.
        "SCORECODE_SMTP_STARTTLS": "true" if smtp_port in ("587", "2525") else "false",
        "SCORECODE_SMTP_USERNAME": v["SMTP_USERNAME"],
        "SCORECODE_SMTP_PASSWORD": v["SMTP_PASSWORD"],
        "SCORECODE_MAIL_FROM": v["MAIL_FROM"],
        "SCORECODE_SENTRY_DSN": v.get("SENTRY_DSN") or None,
        # db.env
        "POSTGRES_USER": "postgres",
        **{k: g[k] for k in GENERATED if k.endswith("PASSWORD")},
        # backup.env: the database dump, encrypted, to the backup storage (AWS S3 when the endpoint is
        # empty: the region picks the endpoint), plus a copy of the files bucket (another provider, so it
        # uses the files bucket's own keys)
        "PGPASSWORD": g["SCORECODE_BACKUP_PASSWORD"],
        "BACKUP_AGE_RECIPIENT": v["BACKUP_AGE_RECIPIENT"],
        "BACKUP_S3_URI": f"s3://{v['BACKUP_S3_BUCKET']}/prod",
        "BACKUP_S3_ENDPOINT": v.get("BACKUP_S3_ENDPOINT") or "",
        "BACKUP_FILES_S3_URI": f"s3://{v['FILES_S3_BUCKET']}",
        "FILES_S3_ENDPOINT": v["FILES_S3_ENDPOINT"],
        "FILES_S3_REGION": v.get("FILES_S3_REGION") or "auto",
        "FILES_S3_ACCESS_KEY_ID": v["FILES_S3_ACCESS_KEY_ID"],
        "FILES_S3_SECRET_ACCESS_KEY": v["FILES_S3_SECRET_ACCESS_KEY"],
        "AWS_ACCESS_KEY_ID": v["BACKUP_S3_ACCESS_KEY_ID"],
        "AWS_SECRET_ACCESS_KEY": v["BACKUP_S3_SECRET_ACCESS_KEY"],
        "AWS_DEFAULT_REGION": v["BACKUP_S3_REGION"],
        # monitoring.env
        "DATA_SOURCE_NAME": (
            f"postgresql://scorecode_monitor:{g['SCORECODE_MONITOR_PASSWORD']}@postgres:5432/scorecode?sslmode=disable"
        ),
    }
    written = []
    for template in sorted(TEMPLATES.glob("*.env.example")):
        name = template.name.removesuffix(".example")
        write(env_dir / name, fill(template.read_text(), values), owner="deploy", group="deploy", mode=0o600)
        written.append(f"env/{name}")

    # Alertmanager: email to ALERT_EMAIL_TO, Telegram too when configured.
    telegram = bool(v.get("TELEGRAM_BOT_TOKEN") and v.get("TELEGRAM_CHAT_ID"))
    am = [
        "# Written by render-env.py; edit the operator's values instead.",
        "global:",
        f"  smtp_smarthost: '{v['SMTP_HOST']}:{smtp_port}'",
        f"  smtp_from: '{address(v['MAIL_FROM'])}'",
        f"  smtp_auth_username: '{v['SMTP_USERNAME']}'",
        "  smtp_auth_password_file: /run/secrets/alert_smtp_password",
        f"  smtp_require_tls: {'true' if smtp_port in ('587', '2525') else 'false'}",
        "route:",
        "  receiver: ops-email",
        "  group_by: [alertname]",
        "  group_wait: 30s",
        "  group_interval: 5m",
        "  repeat_interval: 4h",
        "  routes:",
        '    - matchers: [severity="page"]',
        "      receiver: ops-page",
        "      group_wait: 10s",
        "      repeat_interval: 1h",
        "receivers:",
        "  - name: ops-email",
        "    email_configs:",
        f"      - to: '{v['ALERT_EMAIL_TO']}'",
        "        send_resolved: true",
        "  - name: ops-page",
        "    email_configs:",
        f"      - to: '{v['ALERT_EMAIL_TO']}'",
        "        send_resolved: true",
    ]
    if telegram:
        am += [
            "    telegram_configs:",
            "      - bot_token_file: /run/secrets/alert_telegram_token",
            f"        chat_id: {int(v['TELEGRAM_CHAT_ID'])}",
            "        send_resolved: true",
        ]
    am += [
        "inhibit_rules:",
        '  - source_matchers: [alertname=~"ScoreCodeAPIDown|ScoreCodePostgresDown"]',
        '    target_matchers: [alertname=~"ScoreCodeHigh5xxRate|ScoreCodeStudentReadsSlow|ScoreCodeLoginsSlow|'
        'ScoreCodeDatabasePoolExhausted|ScoreCodeDatabaseUnreachableFromAPI"]',
    ]
    for q in ("SMTP_HOST", "SMTP_USERNAME", "MAIL_FROM", "ALERT_EMAIL_TO"):
        if "'" in v[q]:
            die(f"{q} may not contain a quote")
    write(sec_dir / "alertmanager.yml", "\n".join(am) + "\n", owner="root", group="nogroup", mode=0o640)
    write(sec_dir / "alert_smtp_password", v["SMTP_PASSWORD"], owner="root", group="nogroup", mode=0o640)
    written += ["secrets/alertmanager.yml", "secrets/alert_smtp_password"]
    if telegram:
        write(sec_dir / "alert_telegram_token", v["TELEGRAM_BOT_TOKEN"], owner="root", group="nogroup", mode=0o640)
        written.append("secrets/alert_telegram_token")
    print("wrote " + ", ".join(written))
    print("settings received: " + ", ".join(sorted(k for k in v if v[k])))


if __name__ == "__main__":
    main()
