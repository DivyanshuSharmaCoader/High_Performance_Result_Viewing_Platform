#!/usr/bin/env python3
"""A real restore test of the newest production backup, with the age key staying on this machine (P18.10).

    infra/ops/with-secrets.sh run -- uv run --project backend python infra/ops/restore-test.py ~/.scorecode/backup-age-key.txt

Each step says what it checked, and stops with a plain reason at the first problem:

1. The key file: it exists, only you can read it, it is an age identity without a passphrase, and its
   public key is the one backups are encrypted to (BACKUP_AGE_RECIPIENT). `age-keygen -y` reads it here;
   nothing of it is printed, copied or sent anywhere.
2. The newest backup under ``prod/db/``: downloaded (still encrypted) and checked against the sha256 the
   backup job stored with it.
3. Decrypted here by ``age``; the first bytes must be a PostgreSQL dump (``PGDMP``) before anything is sent.
4. Streamed over SSH to ``sudo scorecode-ctl restore-test``: a throwaway database with no network, a
   fingerprint comparison with the live database, then everything removed. The plaintext never touches
   this machine's disk.

Each step has a time limit, so nothing waits forever.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import boto3

DOWNLOAD_TIMEOUT_S = 600
RESTORE_TIMEOUT_S = 1800


def deploy_key() -> str:
    own = os.environ.get("DEPLOY_USER_KEY_FILE") or str(Path.home() / ".ssh" / "scorecode_deploy")
    return own if Path(own).is_file() else os.environ["DEPLOY_SSH_KEY_FILE"]


def stop(msg: str) -> int:
    print(f"STOP: {msg}", file=sys.stderr)
    return 1


def check_key(path: Path) -> str | None:
    """Why the key can't be used (never its contents), or None."""
    if not path.is_file():
        return f"no file at {path} (check the path; ~ must be outside quotes)"
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        return f"{path} can be read by others (mode {mode:o}); run: chmod 600 {path}"
    head = path.read_bytes()[:200]
    if head.startswith(b"age-encryption.org/"):
        return "this key file is itself encrypted with a passphrase; decrypt it first or use the plain identity"
    if b"AGE-SECRET-KEY-1" not in path.read_bytes():
        return "this file doesn't contain an age identity (a line starting AGE-SECRET-KEY-1)"
    r = subprocess.run(["age-keygen", "-y", str(path)], capture_output=True, text=True, timeout=30, check=False)  # noqa: S603,S607
    if r.returncode != 0:
        return "age-keygen could not read the identity in this file"
    derived = {line.strip() for line in r.stdout.splitlines() if line.strip().startswith("age1")}
    if os.environ["BACKUP_AGE_RECIPIENT"].strip() not in derived:
        return (
            "this key's public key is not BACKUP_AGE_RECIPIENT, the key backups are encrypted to: "
            "it can't decrypt them (wrong key file?)"
        )
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        return stop("usage: restore-test.py AGE_PRIVATE_KEY_FILE")
    key = Path(os.path.expanduser(argv[0]))
    if (why := check_key(key)) is not None:
        return stop(why)
    print("1/4 key: an age identity, private to you, matching the backups' recipient")

    s3 = boto3.client(
        "s3",
        region_name=os.environ["BACKUP_S3_REGION"],
        endpoint_url=os.environ.get("BACKUP_S3_ENDPOINT") or None,
        aws_access_key_id=os.environ["BACKUP_S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["BACKUP_S3_SECRET_ACCESS_KEY"],
    )
    bucket = os.environ["BACKUP_S3_BUCKET"]
    objects = s3.list_objects_v2(Bucket=bucket, Prefix="prod/db/").get("Contents", [])
    if not objects:
        return stop("no backups under prod/db/ yet: run `scorecode-ctl backup` on the server first")
    newest = max(objects, key=lambda o: o["LastModified"])
    name = newest["Key"].rsplit("/", 1)[-1]
    with tempfile.TemporaryDirectory() as tmp:
        encrypted = Path(tmp) / "db.dump.age"
        started = time.monotonic()
        s3.download_file(bucket, newest["Key"], str(encrypted))
        if time.monotonic() - started > DOWNLOAD_TIMEOUT_S:
            return stop("the download took too long")
        want = (s3.head_object(Bucket=bucket, Key=newest["Key"]).get("Metadata") or {}).get("sha256")
        got = hashlib.sha256(encrypted.read_bytes()).hexdigest()
        if want and want != got:
            return stop(f"{name}: the download doesn't match the checksum stored with the backup")
        print(
            f"2/4 backup: {name}, {newest['Size']} bytes, {newest['LastModified']:%Y-%m-%d %H:%M} UTC, "
            f"sha256 {'matches' if want else 'not stored (older backup)'}"
        )

        age = subprocess.Popen(  # noqa: S603 - fixed argv
            ["age", "--decrypt", "--identity", str(key), str(encrypted)],  # noqa: S607
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )  # fmt: skip
        assert age.stdout is not None and age.stderr is not None
        first = age.stdout.read(5)
        if not first:  # age wrote nothing: it failed, and says why (never with key material)
            age.wait(timeout=60)
            err = age.stderr.read().decode(errors="replace").strip().splitlines()
            told = [line for line in err if "error:" in line] or err or ["age exited without output"]
            return stop(f"decryption failed: {told[0][:200]}")
        if first != b"PGDMP":
            age.kill()
            return stop("decrypted, but the content is not a PostgreSQL dump: not a ScoreCode database backup")
        print("3/4 decrypted here: a PostgreSQL dump (PGDMP); streaming it to the server")

        port = os.environ.get("DEPLOY_SSH_PORT") or "22"
        ssh = subprocess.Popen(  # noqa: S603 - fixed argv
            ["ssh", "-i", deploy_key(), "-p", port, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
             "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
             f"deploy@{os.environ['DEPLOY_HOST']}", "sudo", "/usr/local/sbin/scorecode-ctl", "restore-test"],
            stdin=subprocess.PIPE,
        )  # fmt: skip
        assert ssh.stdin is not None
        try:
            ssh.stdin.write(first)
            while chunk := age.stdout.read(1 << 20):
                ssh.stdin.write(chunk)
            ssh.stdin.close()
        except BrokenPipeError:
            pass
        age.wait(timeout=60)
        try:
            rc = ssh.wait(timeout=RESTORE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            ssh.kill()
            return stop(f"the server didn't finish within {RESTORE_TIMEOUT_S // 60} minutes")
    if age.returncode != 0:
        return stop("age stopped part-way through the backup")
    print(f"4/4 server: {'restore test finished' if rc == 0 else f'restore test FAILED (exit {rc})'}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
