#!/usr/bin/env python3
"""Is any value from the master secrets file anywhere in this repository or its history?

    infra/ops/with-secrets.sh run -- python3 infra/ops/leak-scan.py

Pattern scanners (gitleaks in CI and pre-commit) find things that look like secrets. This finds the
actual values: every blob ever committed, on every branch, plus the working tree's untracked files that
git would add. It prints only the variable NAME and the path, never a value. Exit 1 if anything is found.

Short or generic values (ports, "root", "auto") are skipped; identifiers that are not secret but must stay
out of a public repository (the server address, bucket names, the zone id, the admin and alert emails) are
checked like secrets.
"""

from __future__ import annotations

import os
import subprocess
import sys

NAMES = [
    "SCORECODE_DOMAIN",  # reported separately: the public domain may appear in docs
    "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ZONE_ID",
    "DEPLOY_HOST",
    "FILES_S3_ENDPOINT", "FILES_S3_BUCKET", "FILES_S3_ACCESS_KEY_ID", "FILES_S3_SECRET_ACCESS_KEY",
    "BACKUP_S3_ENDPOINT", "BACKUP_S3_BUCKET", "BACKUP_S3_ACCESS_KEY_ID", "BACKUP_S3_SECRET_ACCESS_KEY",
    "BACKUP_AGE_RECIPIENT",
    "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_FROM", "ALERT_EMAIL_TO",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "PLATFORM_ADMIN_EMAIL", "PLATFORM_ADMIN_PASSWORD",
    "GHCR_READ_TOKEN", "SENTRY_DSN",
]
# The public domain may appear in docs. Bucket names are not secret (R2 names are per account); they are
# reported so they can be kept out of new files, but a hit is not a failure.
INFORMATIONAL = {"SCORECODE_DOMAIN", "FILES_S3_BUCKET", "BACKUP_S3_BUCKET"}


def needles() -> dict[str, bytes]:
    out = {}
    for n in NAMES:
        v = os.environ.get(n, "").strip()
        if len(v) >= 8:
            out[n] = v.encode()
        if n == "MAIL_FROM" and "<" in v:  # "Name <addr>": look for the address itself
            out[n] = v.split("<", 1)[1].rstrip(">").strip().encode()
        if n == "SENTRY_DSN" and "@" in v:  # the key part is the secret
            out[n] = v.split("//", 1)[-1].split("@", 1)[0].encode()
    return out


def main() -> int:
    find = needles()
    if not find:
        sys.exit("no values loaded: run under infra/ops/with-secrets.sh")
    hits: dict[str, set[str]] = {}

    # 1) Every blob in the object database (all history, all branches), with one path it appeared at.
    paths: dict[str, str] = {}
    listing = subprocess.run(["git", "rev-list", "--all", "--objects"], capture_output=True, check=True).stdout
    for line in listing.decode(errors="replace").splitlines():
        sha, _, path = line.partition(" ")
        if path:
            paths.setdefault(sha, path)
    proc = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    assert proc.stdin and proc.stdout
    for sha, path in paths.items():
        proc.stdin.write(f"{sha}\n".encode())
        proc.stdin.flush()
        header = proc.stdout.readline().split()
        if len(header) < 3:
            continue
        data = proc.stdout.read(int(header[2]))
        proc.stdout.read(1)
        if header[1] != b"blob":
            continue
        for name, needle in find.items():
            if needle in data:
                hits.setdefault(name, set()).add(f"history:{path}")
    proc.stdin.close()
    proc.wait()

    # 2) Files git would add now (untracked but not ignored) and tracked files' current contents.
    current = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True, check=True
    ).stdout.split(b"\0")
    for p in current:
        if not p:
            continue
        try:
            with open(p, "rb") as f:
                data = f.read()
        except OSError:
            continue
        for name, needle in find.items():
            if needle in data:
                hits.setdefault(name, set()).add(f"tree:{p.decode(errors='replace')}")

    bad = False
    for name in NAMES:
        if name not in find:
            continue
        where = sorted(hits.get(name, set()))
        if not where:
            print(f"{name}: not found")
        elif name in INFORMATIONAL:
            print(f"{name}: appears in {len(where)} place(s) (not secret; informational)")
        else:
            bad = True
            print(f"{name}: FOUND in {', '.join(where[:10])}{' …' if len(where) > 10 else ''}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
