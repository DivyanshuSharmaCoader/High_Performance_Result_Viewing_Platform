#!/usr/bin/env python3
"""Create the first ScoreCode staff (platform console) account on the server, from the secrets file.

    infra/ops/with-secrets.sh run -- python3 infra/ops/create-admin.py

PLATFORM_ADMIN_EMAIL, _NAME and _PASSWORD go to the server on SSH's stdin. The two-step (TOTP) enrolment
that comes back is written straight to a private file for the owner (mode 600), never printed:

    ~/Desktop/ScoreCode-console-2FA.txt   (scan it into an authenticator app, then delete the file)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

OUT = Path(os.environ.get("ADMIN_TOTP_OUT", str(Path.home() / "Desktop" / "ScoreCode-console-2FA.txt")))


def main() -> int:
    host, key = os.environ["DEPLOY_HOST"], os.environ["DEPLOY_SSH_KEY_FILE"]
    port = os.environ.get("DEPLOY_SSH_PORT") or "22"
    payload = "\n".join(os.environ[n].strip() for n in ("PLATFORM_ADMIN_EMAIL", "PLATFORM_ADMIN_NAME", "PLATFORM_ADMIN_PASSWORD"))
    r = subprocess.run(  # noqa: S603 - fixed argv
        ["ssh", "-i", key, "-p", port, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
         f"deploy@{host}", "sudo", "/usr/local/sbin/scorecode-ctl", "create-platform-admin"],
        input=(payload + "\n").encode(), capture_output=True, check=False,
    )
    if r.returncode != 0:
        # The CLI's errors name the problem (e.g. "already exists", a weak password) without values.
        print(f"failed (exit {r.returncode}): {r.stderr.decode(errors='replace')[-400:]}", file=sys.stderr)
        return r.returncode
    fd = os.open(OUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(r.stdout)
    print(f"created; the two-step enrolment is in {OUT} (mode 600). Scan it, then delete the file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
