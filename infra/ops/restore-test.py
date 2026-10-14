#!/usr/bin/env python3
"""A real restore test of the newest production backup, with the age key staying on this machine (P18.10).

    infra/ops/with-secrets.sh run -- uv run --project backend python infra/ops/restore-test.py AGE_KEY_FILE

1. Downloads the newest encrypted dump under ``prod/db/`` in the backup bucket (still encrypted).
2. Decrypts it here with the private key file named on the command line (run by the owner; the key is
   never read by this script, only by ``age``).
3. Streams the plaintext over SSH to ``sudo scorecode-ctl restore-test`` on the server, which restores it
   into a throwaway database with no network, compares its fingerprint with the live database and
   removes it. The plaintext never touches this machine's disk.

Prints what the server prints: sizes, timings, and which fingerprint lines differ (names, counts and
checksums; never rows).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import boto3


def deploy_key() -> str:
    own = os.environ.get("DEPLOY_USER_KEY_FILE") or str(Path.home() / ".ssh" / "scorecode_deploy")
    return own if Path(own).is_file() else os.environ["DEPLOY_SSH_KEY_FILE"]


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not Path(argv[0]).is_file():
        sys.exit("usage: restore-test.py AGE_PRIVATE_KEY_FILE")
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
        sys.exit("no backups under prod/db/ yet: run `scorecode-ctl backup` on the server first")
    newest = max(objects, key=lambda o: o["LastModified"])
    print(f"newest backup: {newest['Key'].rsplit('/', 1)[-1]} ({newest['Size']} bytes, {newest['LastModified']:%Y-%m-%d %H:%M} UTC)")
    with tempfile.TemporaryDirectory() as tmp:
        encrypted = Path(tmp) / "db.dump.age"
        s3.download_file(bucket, newest["Key"], str(encrypted))
        port = os.environ.get("DEPLOY_SSH_PORT") or "22"
        ssh = subprocess.Popen(  # noqa: S603 - fixed argv
            ["ssh", "-i", deploy_key(), "-p", port, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
             f"deploy@{os.environ['DEPLOY_HOST']}", "sudo", "/usr/local/sbin/scorecode-ctl", "restore-test"],
            stdin=subprocess.PIPE,
        )  # fmt: skip
        age = subprocess.run(  # noqa: S603 - fixed argv
            ["age", "--decrypt", "--identity", argv[0], str(encrypted)], stdout=ssh.stdin, check=False  # noqa: S607
        )
        assert ssh.stdin is not None
        ssh.stdin.close()
        rc = ssh.wait()
    if age.returncode != 0:
        print("age could not decrypt the backup with that key", file=sys.stderr)
        return 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
