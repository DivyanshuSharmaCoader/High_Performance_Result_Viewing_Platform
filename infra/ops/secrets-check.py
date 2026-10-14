#!/usr/bin/env python3
"""Check the master secrets file without ever printing a value.

    infra/ops/with-secrets.sh run -- backend/.venv/bin/python infra/ops/secrets-check.py [--connect]

Prints one line per variable: ``NAME: SET``, ``MISSING``, ``INVALID FORMAT`` or ``CONNECTION FAILED``.
With ``--connect`` it also tries each service with its credentials and prints one sanitised line per
check (the kind of failure, never the server's message, which can echo a value back):

- Cloudflare: the token verifies and the zone's name is SCORECODE_DOMAIN.
- SSH: the key logs in to DEPLOY_HOST (BatchMode, strict host key checking against known_hosts).
- File storage (R2): write, read and delete one object under ``_healthcheck/``.
- Backup storage (S3): the same, in the backup bucket.
- SMTP: connect, STARTTLS and log in. No email is sent.
- GHCR: the read token is granted pull on the backend image.
- Sentry: the DSN's host answers HTTPS (no event is sent).

Exit status 1 if a required variable isn't SET or a connection check failed.
"""

from __future__ import annotations

import base64
import json
import os
import re
import smtplib
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass

EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
AGE = re.compile(r"^age1[02-9ac-hj-np-z]{58}$")


def _email_or_named(v: str) -> bool:  # "Name <a@b.c>" or "a@b.c"
    m = re.match(r"^[^<>]*<([^<>]+)>$", v)
    return bool(EMAIL.match(m.group(1) if m else v))


def _host_or_ip(v: str) -> bool:
    try:
        socket.inet_aton(v)
        return True
    except OSError:
        return bool(DOMAIN.match(v.lower()))


def _https_url(v: str) -> bool:
    p = urllib.parse.urlparse(v)
    return p.scheme == "https" and bool(p.netloc) and " " not in v


def _key_file(v: str) -> bool:
    return os.path.isfile(v) and (os.stat(v).st_mode & 0o077) == 0


def _sentry_dsn(v: str) -> bool:
    p = urllib.parse.urlparse(v)
    return p.scheme == "https" and bool(p.username) and bool(p.hostname) and p.path.strip("/").isdigit()


@dataclass(frozen=True)
class Var:
    name: str
    required: bool
    valid: Callable[[str], bool] = lambda v: bool(v.strip())


VARS = [
    Var("SCORECODE_DOMAIN", True, lambda v: bool(DOMAIN.match(v))),
    Var("CLOUDFLARE_API_TOKEN", True, lambda v: len(v) >= 30 and " " not in v),
    Var("CLOUDFLARE_ZONE_ID", True, lambda v: bool(HEX32.match(v))),
    Var("DEPLOY_HOST", True, _host_or_ip),
    Var("DEPLOY_SSH_USER", True, lambda v: bool(re.match(r"^[a-z_][a-z0-9_-]{0,31}$", v))),
    Var("DEPLOY_SSH_PORT", False, lambda v: v.isdigit() and 0 < int(v) < 65536),
    Var("DEPLOY_SSH_KEY_FILE", True, _key_file),
    Var("FILES_S3_ENDPOINT", True, _https_url),
    Var("FILES_S3_BUCKET", True, lambda v: bool(re.match(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", v))),
    Var("FILES_S3_ACCESS_KEY_ID", True, lambda v: len(v) >= 16 and " " not in v),
    Var("FILES_S3_SECRET_ACCESS_KEY", True, lambda v: len(v) >= 30 and " " not in v),
    Var("FILES_S3_REGION", False),
    Var("BACKUP_S3_ENDPOINT", False, _https_url),
    Var("BACKUP_S3_BUCKET", True, lambda v: bool(re.match(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", v))),
    Var("BACKUP_S3_REGION", True, lambda v: bool(re.match(r"^[a-z]{2}(-[a-z]+)+-\d$", v)) or v == "auto"),
    Var("BACKUP_S3_ACCESS_KEY_ID", True, lambda v: len(v) >= 16 and " " not in v),
    Var("BACKUP_S3_SECRET_ACCESS_KEY", True, lambda v: len(v) >= 30 and " " not in v),
    Var("BACKUP_AGE_RECIPIENT", True, lambda v: bool(AGE.match(v))),
    Var("SMTP_HOST", True, _host_or_ip),
    Var("SMTP_PORT", False, lambda v: v in {"25", "465", "587", "2525"}),
    Var("SMTP_USERNAME", True),
    Var("SMTP_PASSWORD", True, lambda v: len(v) >= 8),
    Var("MAIL_FROM", True, _email_or_named),
    Var("ALERT_EMAIL_TO", True, lambda v: bool(EMAIL.match(v))),
    Var("TELEGRAM_BOT_TOKEN", False, lambda v: bool(re.match(r"^\d+:[A-Za-z0-9_-]{30,}$", v))),
    Var("TELEGRAM_CHAT_ID", False, lambda v: bool(re.match(r"^-?\d+$", v))),
    Var("PLATFORM_ADMIN_EMAIL", True, lambda v: bool(EMAIL.match(v))),
    Var("PLATFORM_ADMIN_NAME", True),
    Var("PLATFORM_ADMIN_PASSWORD", True, lambda v: len(v) >= 12),
    Var("GHCR_USERNAME", False, lambda v: bool(re.match(r"^[A-Za-z0-9-]{1,39}$", v))),
    Var("GHCR_READ_TOKEN", False, lambda v: len(v) >= 30 and " " not in v),
    Var("SENTRY_DSN", False, _sentry_dsn),
]

# Values that are still the template's fake examples.
PLACEHOLDER = re.compile(r"FAKE|CHANGE-ME", re.IGNORECASE)
# Passwords chosen by the owner must not be guessable from this (once public) repository.
WEAK_IF_PUBLIC = ("PLATFORM_ADMIN_PASSWORD",)


def _public_text() -> bytes:
    """Every tracked file's text: a value found in it is public knowledge."""
    try:
        files = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout.split(b"\0")
    except (OSError, subprocess.CalledProcessError):
        return b""
    chunks = []
    for f in files:
        try:
            with open(f, "rb") as fh:
                chunks.append(fh.read())
        except OSError:
            pass
    return b"\n".join(chunks)


def env(name: str) -> str:
    return os.environ.get(name, "").strip()


class CheckFailed(Exception):
    """Carries a sanitised reason only."""


def _tls() -> ssl.SSLContext:
    """The python.org build has no CA bundle of its own: certifi if installed, else the system's, so a
    missing bundle can't show up as a failed connection."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        if not os.path.exists(ssl.get_default_verify_paths().openssl_cafile) and os.path.exists("/etc/ssl/cert.pem"):
            return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
        return ssl.create_default_context()


def _http(url: str, headers: dict[str, str] | None = None, timeout: float = 15) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_tls()) as r:  # noqa: S310 - fixed https URLs only
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise CheckFailed(f"unreachable ({type(e).__name__})") from None


def check_cloudflare() -> None:
    auth = {"Authorization": f"Bearer {env('CLOUDFLARE_API_TOKEN')}"}
    status, _ = _http("https://api.cloudflare.com/client/v4/user/tokens/verify", auth)
    if status != 200:
        raise CheckFailed(f"token rejected (HTTP {status})")
    status, body = _http(f"https://api.cloudflare.com/client/v4/zones/{env('CLOUDFLARE_ZONE_ID')}", auth)
    if status != 200:
        raise CheckFailed(f"zone not readable with this token (HTTP {status})")
    if json.loads(body)["result"]["name"] != env("SCORECODE_DOMAIN"):
        raise CheckFailed("the zone's name is not SCORECODE_DOMAIN")


def check_ssh() -> None:
    port = env("DEPLOY_SSH_PORT") or "22"
    try:
        socket.create_connection((env("DEPLOY_HOST"), int(port)), timeout=10).close()
    except OSError as e:
        raise CheckFailed(f"port {port} unreachable ({type(e).__name__})") from None
    r = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=yes",
         "-i", env("DEPLOY_SSH_KEY_FILE"), "-p", port, f"{env('DEPLOY_SSH_USER')}@{env('DEPLOY_HOST')}", "true"],
        capture_output=True, timeout=30, check=False,
    )
    if r.returncode != 0:
        err = r.stderr.decode(errors="replace")
        if "Host key verification failed" in err or "REMOTE HOST IDENTIFICATION" in err:
            raise CheckFailed("host key does not match known_hosts")
        if "Permission denied" in err:
            raise CheckFailed("key not accepted")
        raise CheckFailed(f"ssh exit {r.returncode}")


def _s3_roundtrip(prefix: str, endpoint: str | None, region: str | None) -> None:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint or None,
        region_name=region or None,
        aws_access_key_id=env(f"{prefix}_ACCESS_KEY_ID"),
        aws_secret_access_key=env(f"{prefix}_SECRET_ACCESS_KEY"),
        config=Config(connect_timeout=10, read_timeout=20, retries={"max_attempts": 2}),
    )
    bucket, key = env(f"{prefix}_BUCKET"), f"_healthcheck/{uuid.uuid4()}.txt"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=b"scorecode healthcheck")
        if s3.get_object(Bucket=bucket, Key=key)["Body"].read() != b"scorecode healthcheck":
            raise CheckFailed("read back different bytes")
        try:
            s3.delete_object(Bucket=bucket, Key=key)
        except ClientError as e:
            # The backup key should not be able to delete (docs/runbooks/backup-and-restore.md); the
            # bucket's lifecycle rule removes the health-check object instead.
            if prefix != "BACKUP_S3" or e.response.get("Error", {}).get("Code") != "AccessDenied":
                raise
    except ClientError as e:
        raise CheckFailed(f"{e.response.get('Error', {}).get('Code', 'error')}") from None
    except BotoCoreError as e:
        raise CheckFailed(type(e).__name__) from None


def check_files_s3() -> None:
    _s3_roundtrip("FILES_S3", env("FILES_S3_ENDPOINT"), env("FILES_S3_REGION") or "auto")


def check_backup_s3() -> None:
    _s3_roundtrip("BACKUP_S3", env("BACKUP_S3_ENDPOINT") or None, env("BACKUP_S3_REGION"))


def check_smtp() -> None:
    port = int(env("SMTP_PORT") or "587")
    try:
        if port == 465:
            client: smtplib.SMTP = smtplib.SMTP_SSL(env("SMTP_HOST"), port, timeout=15, context=_tls())
        else:
            client = smtplib.SMTP(env("SMTP_HOST"), port, timeout=15)
            client.starttls(context=_tls())
        client.login(env("SMTP_USERNAME"), env("SMTP_PASSWORD"))
        client.quit()
    except smtplib.SMTPAuthenticationError:
        raise CheckFailed("login rejected") from None
    except (smtplib.SMTPException, OSError) as e:
        raise CheckFailed(type(e).__name__) from None


def check_ghcr() -> None:
    owner = (env("GHCR_USERNAME") or "divyanshusharmacoader").lower()
    basic = base64.b64encode(f"{env('GHCR_USERNAME')}:{env('GHCR_READ_TOKEN')}".encode()).decode()
    status, body = _http(
        f"https://ghcr.io/token?scope=repository:{owner}/scorecode-backend:pull&service=ghcr.io",
        {"Authorization": f"Basic {basic}"},
    )
    if status != 200 or "token" not in json.loads(body or b"{}"):
        raise CheckFailed(f"pull not granted (HTTP {status})")


def check_sentry() -> None:
    host = urllib.parse.urlparse(env("SENTRY_DSN")).hostname or ""
    status, _ = _http(f"https://{host}/api/0/", timeout=10)
    if status >= 500:
        raise CheckFailed(f"HTTP {status}")


CONNECTIONS: list[tuple[str, list[str], Callable[[], None]]] = [
    ("cloudflare", ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ZONE_ID", "SCORECODE_DOMAIN"], check_cloudflare),
    ("ssh", ["DEPLOY_HOST", "DEPLOY_SSH_USER", "DEPLOY_SSH_KEY_FILE"], check_ssh),
    ("files-s3", ["FILES_S3_ENDPOINT", "FILES_S3_BUCKET", "FILES_S3_ACCESS_KEY_ID",
                  "FILES_S3_SECRET_ACCESS_KEY"], check_files_s3),
    ("backup-s3", ["BACKUP_S3_BUCKET", "BACKUP_S3_REGION", "BACKUP_S3_ACCESS_KEY_ID",
                   "BACKUP_S3_SECRET_ACCESS_KEY"], check_backup_s3),
    ("smtp", ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"], check_smtp),
    ("ghcr", ["GHCR_USERNAME", "GHCR_READ_TOKEN"], check_ghcr),
    ("sentry", ["SENTRY_DSN"], check_sentry),
]


def main(argv: list[str]) -> int:
    connect = "--connect" in argv
    only = {a for a in argv if not a.startswith("-")}  # optional: limit --connect to named checks
    status: dict[str, str] = {}
    public = _public_text()
    for v in VARS:
        val = env(v.name)
        if not val:
            status[v.name] = "MISSING"
        elif PLACEHOLDER.search(val) or not v.valid(val):
            status[v.name] = "INVALID FORMAT"
        elif v.name in WEAK_IF_PUBLIC and (val.encode() in public or "PASSWORD" in val.upper()):
            status[v.name] = "INVALID FORMAT (guessable: it appears in the repository's files)"
        else:
            status[v.name] = "SET"

    results: list[str] = []
    if connect:
        for name, needs, fn in CONNECTIONS:
            if only and name not in only:
                continue
            if any(status[n] != "SET" for n in needs):
                if all(status[n] == "MISSING" for n in needs) and not VARS[[x.name for x in VARS].index(needs[0])].required:
                    results.append(f"connection {name}: skipped (not configured)")
                else:
                    results.append(f"connection {name}: skipped (fix the variables above first)")
                continue
            try:
                fn()
                results.append(f"connection {name}: OK")
            except CheckFailed as e:
                results.append(f"connection {name}: CONNECTION FAILED ({e})")
                for n in needs:
                    status[n] = "CONNECTION FAILED"
            except Exception as e:  # never let a library message (which may echo a value) through
                results.append(f"connection {name}: CONNECTION FAILED ({type(e).__name__})")
                for n in needs:
                    status[n] = "CONNECTION FAILED"

    bad = False
    for v in VARS:
        st = status[v.name]
        optional_missing = st == "MISSING" and not v.required
        print(f"{v.name}: {st}{' (optional)' if optional_missing else ''}")
        bad |= st != "SET" and not optional_missing
    for line in results:
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
