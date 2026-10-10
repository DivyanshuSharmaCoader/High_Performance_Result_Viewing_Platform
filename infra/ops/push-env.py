#!/usr/bin/env python3
"""Send the server the operator's values it needs, over SSH, and have it write its settings files.

    infra/ops/with-secrets.sh run -- python3 infra/ops/push-env.py

Only the names the server uses go (not the Cloudflare token, the SSH key path, the admin password or the
registry token). They travel on SSH's stdin, never on a command line, to the root-owned renderer
(`sudo scorecode-ctl render-env`), which writes env/*.env as the deploy user, mode 600. Prints only what
the server prints: file and setting names.
"""

from __future__ import annotations

import os
import subprocess
import sys

SEND = [
    "SCORECODE_DOMAIN",
    "FILES_S3_ENDPOINT", "FILES_S3_BUCKET", "FILES_S3_ACCESS_KEY_ID", "FILES_S3_SECRET_ACCESS_KEY", "FILES_S3_REGION",
    "BACKUP_S3_ENDPOINT", "BACKUP_S3_BUCKET", "BACKUP_S3_REGION", "BACKUP_S3_ACCESS_KEY_ID",
    "BACKUP_S3_SECRET_ACCESS_KEY", "BACKUP_AGE_RECIPIENT",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_FROM",
    "ALERT_EMAIL_TO", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "SENTRY_DSN",
]


def ssh(user: str, *args: str, stdin: bytes) -> subprocess.CompletedProcess[bytes]:
    host, key, port = os.environ["DEPLOY_HOST"], os.environ["DEPLOY_SSH_KEY_FILE"], os.environ.get("DEPLOY_SSH_PORT") or "22"
    return subprocess.run(  # noqa: S603 - fixed argv
        ["ssh", "-i", key, "-p", port, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
         f"{user}@{host}", *args],
        input=stdin, capture_output=True, check=False,
    )


def main() -> int:
    lines = []
    for name in SEND:
        value = os.environ.get(name, "").strip()
        if value:
            lines.append(f"{name}={value}")
    extra = [a for a in sys.argv[1:] if a.split("=", 1)[0] in ("API_WORKERS", "PDF_PROCESSES")]
    lines += extra
    r = ssh("deploy", "sudo", "/usr/local/sbin/scorecode-ctl", "render-env", stdin=("\n".join(lines) + "\n").encode())
    sys.stdout.write(r.stdout.decode(errors="replace"))
    sys.stderr.write(r.stderr.decode(errors="replace"))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
