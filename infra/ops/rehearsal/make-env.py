"""Fill in infra/ops/env/*.example for the deploy rehearsal (release.yml): random secrets that agree across
files, local object storage and mail, a self-signed certificate for *.scorecode.test. Writes env/ and
certs/ in the current directory. Rehearsal only: a real server gets its values from the operator."""

from __future__ import annotations

import re
import secrets
import subprocess
from pathlib import Path

DOMAIN = "scorecode.test"
Value = str | None
pw = {role: secrets.token_urlsafe(24) for role in ("postgres", "migrator", "app", "platform", "backup", "monitor")}
values: dict[str, Value] = {
    "BASE_DOMAIN": DOMAIN,
    "TRUSTED_PROXIES": "private_ranges",
    "PDF_PROCESSES": "1",
    "REGISTRY": "rehearsal",
    "SCORECODE_BASE_DOMAIN": DOMAIN,
    "SCORECODE_SECRET_KEY": secrets.token_urlsafe(48),
    "SCORECODE_ABUSE_SIGNAL_KEY": secrets.token_urlsafe(48),
    "SCORECODE_DATABASE_URL_APP": f"postgresql+asyncpg://scorecode_app:{pw['app']}@postgres:5432/scorecode",
    "SCORECODE_DATABASE_URL_PLATFORM": f"postgresql+asyncpg://scorecode_platform:{pw['platform']}@postgres:5432/scorecode",
    "SCORECODE_DATABASE_URL_MIGRATOR": f"postgresql+asyncpg://scorecode_migrator:{pw['migrator']}@postgres:5432/scorecode",
    "SCORECODE_S3_ENDPOINT_URL": "http://s3:8333",
    "SCORECODE_S3_PUBLIC_ENDPOINT_URL": f"https://files.{DOMAIN}",
    "SCORECODE_S3_ACCESS_KEY": "rehearsal",
    "SCORECODE_S3_SECRET_KEY": "rehearsal-object-storage-secret-0123456789",
    "SCORECODE_SMTP_HOST": "mailpit",
    "SCORECODE_SMTP_PORT": "1025",
    "SCORECODE_SMTP_STARTTLS": "false",
    "SCORECODE_SMTP_USERNAME": None,  # None: the line is left out (an empty value would mean "log in as ''")
    "SCORECODE_SMTP_PASSWORD": None,
    "SCORECODE_MAIL_FROM": f"results@{DOMAIN}",
    "POSTGRES_PASSWORD": pw["postgres"],
    "SCORECODE_MIGRATOR_PASSWORD": pw["migrator"],
    "SCORECODE_APP_PASSWORD": pw["app"],
    "SCORECODE_PLATFORM_PASSWORD": pw["platform"],
    "SCORECODE_BACKUP_PASSWORD": pw["backup"],
    "SCORECODE_MONITOR_PASSWORD": pw["monitor"],
    "PGPASSWORD": pw["backup"],
    "BACKUP_S3_URI": "s3://scorecode-backups/rehearsal",
    "BACKUP_S3_ENDPOINT": "http://s3:8333",
    "BACKUP_FILES_S3_URI": "s3://scorecode-files",
    "AWS_ACCESS_KEY_ID": "rehearsal",
    "AWS_SECRET_ACCESS_KEY": "rehearsal-object-storage-secret-0123456789",
    "AWS_DEFAULT_REGION": "us-east-1",
    "DATA_SOURCE_NAME": f"postgresql://scorecode_monitor:{pw['monitor']}@postgres:5432/scorecode?sslmode=disable",
}


def fill(template: str, extra: dict[str, str]) -> str:
    known: dict[str, Value] = {**values, **extra}
    out = []
    for line in template.splitlines():
        m = re.match(r"^([A-Z_0-9]+)=", line)
        if m and m[1] in known:
            if known[m[1]] is None:
                continue
            line = f"{m[1]}={known[m[1]]}"
        out.append(line)
    return "\n".join(out) + "\n"


def main() -> None:
    env = Path("env")
    env.mkdir(mode=0o700, exist_ok=True)
    key = subprocess.run(  # noqa: S603 - fixed arguments
        ["docker", "run", "--rm", "--entrypoint", "age-keygen", "rehearsal/scorecode-backup:rehearsal-1"],  # noqa: S607
        capture_output=True, text=True, check=True,
    ).stdout
    Path("age-key.txt").write_text(key)
    recipient = re.search(r"age1[0-9a-z]+", key)
    assert recipient
    for template in sorted(Path("infra/ops/env").glob("*.env.example")):
        target = env / template.name.removesuffix(".example")
        target.write_text(fill(template.read_text(), {"BACKUP_AGE_RECIPIENT": recipient[0], "REGISTRY": "rehearsal"}))
        target.chmod(0o600)
    with (env / "deploy.env").open("a") as f:
        f.write("REGISTRY=rehearsal\n")
    certs = Path("certs")
    certs.mkdir(exist_ok=True)
    subprocess.run(  # noqa: S603 - fixed arguments
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", f"/CN={DOMAIN}",  # noqa: S607
         "-addext", f"subjectAltName=DNS:{DOMAIN},DNS:*.{DOMAIN}",
         "-keyout", str(certs / "origin-key.pem"), "-out", str(certs / "origin.pem")],
        check=True, capture_output=True,
    )
    (certs / "origin-key.pem").chmod(0o644)  # the proxy container's user must read it in this rehearsal
    print("rehearsal env/ and certs/ written")


if __name__ == "__main__":
    main()
