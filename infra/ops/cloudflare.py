#!/usr/bin/env python3
"""Cloudflare operations for SCORECODE_DOMAIN, run under the secrets loader. Never prints the token.

    infra/ops/with-secrets.sh run -- python3 infra/ops/cloudflare.py dns-list
    infra/ops/with-secrets.sh run -- python3 infra/ops/cloudflare.py settings
    infra/ops/with-secrets.sh run -- python3 infra/ops/cloudflare.py dns-plan            # what go-live changes
    infra/ops/with-secrets.sh run -- python3 infra/ops/cloudflare.py dns-apply --yes     # gate (b): owner approves
    infra/ops/with-secrets.sh run -- python3 infra/ops/cloudflare.py origin-cert DIR     # writes DIR/origin.pem + key
    ... remote.sh deploy ctl make-csr | ... cloudflare.py sign-csr | ... remote.sh deploy ctl install-cert
                                     # the same certificate, with the key made on the server and kept there
    infra/ops/with-secrets.sh run -- python3 infra/ops/cloudflare.py ssl-strict --yes    # "Full (strict)" + HTTPS

Reads CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID, SCORECODE_DOMAIN and DEPLOY_HOST from the environment.
`dns-plan` prints the records ScoreCode needs (apex, wildcard for tenants, admin, verify) next to what
exists; nothing changes until `dns-apply --yes`. Records that point elsewhere are listed, never deleted.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"


def _env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"{name} is not set (run under infra/ops/with-secrets.sh)")
    return v


def _ctx() -> ssl.SSLContext:
    try:
        import certifi  # the python.org build has no system CA bundle

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {_env('CLOUDFLARE_API_TOKEN')}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=_ctx()) as r:  # noqa: S310 - fixed API host
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            errors = [x.get("message", "") for x in json.loads(e.read()).get("errors", [])]
        except Exception:
            errors = []
        sys.exit(f"Cloudflare API {method} {path.split('?')[0]}: HTTP {e.code} {'; '.join(errors)[:300]}")


def zone() -> str:
    return _env("CLOUDFLARE_ZONE_ID")


def records() -> list[dict]:
    out, page = [], 1
    while True:
        r = call("GET", f"/zones/{zone()}/dns_records?per_page=100&page={page}")
        out += r["result"]
        if page >= r["result_info"]["total_pages"]:
            return out
        page += 1


def wanted() -> list[dict]:
    domain, host = _env("SCORECODE_DOMAIN"), _env("DEPLOY_HOST")
    names = [domain, f"*.{domain}", f"admin.{domain}", f"verify.{domain}"]
    return [{"type": "A", "name": n, "content": host, "proxied": True, "ttl": 1} for n in names]


def dns_list() -> None:
    for r in sorted(records(), key=lambda r: (r["name"], r["type"])):
        print(f"{r['type']:6} {r['name']:40} {r['content'][:60]:60} proxied={r.get('proxied')}")


def dns_plan(apply: bool = False) -> None:
    existing = records()
    for w in wanted():
        same = [r for r in existing if r["name"] == w["name"] and r["type"] in ("A", "AAAA", "CNAME")]
        ok = [r for r in same if r["type"] == "A" and r["content"] == w["content"] and r.get("proxied")]
        if ok and len(same) == 1:
            print(f"ok      {w['name']}")
            continue
        others = [f"{r['type']} {r['content']}" for r in same if r not in ok]
        action = "update" if same else "create"
        print(f"{action:7} {w['name']} -> A (DEPLOY_HOST), proxied" + (f"   [now: {', '.join(others)}]" if others else ""))
        if apply:
            if len(same) == 1:
                call("PUT", f"/zones/{zone()}/dns_records/{same[0]['id']}", w)
            elif not same:
                call("POST", f"/zones/{zone()}/dns_records", w)
            else:
                print(f"        skipped: {len(same)} records share this name; resolve by hand")
                continue
            print("        done")


def settings() -> None:
    for key in ("ssl", "always_use_https", "min_tls_version", "tls_1_3", "automatic_https_rewrites"):
        r = call("GET", f"/zones/{zone()}/settings/{key}")
        print(f"{key:26} {r['result']['value']}")


def ssl_strict() -> None:
    call("PATCH", f"/zones/{zone()}/settings/ssl", {"value": "strict"})
    call("PATCH", f"/zones/{zone()}/settings/always_use_https", {"value": "on"})
    call("PATCH", f"/zones/{zone()}/settings/min_tls_version", {"value": "1.2"})
    settings()


def origin_cert(out_dir: str) -> None:
    """A 15-year Cloudflare Origin CA certificate for the apex and wildcard; the key never leaves DIR."""
    domain = _env("SCORECODE_DOMAIN")
    out = Path(out_dir)
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    key, cert = out / "origin-key.pem", out / "origin.pem"
    with tempfile.TemporaryDirectory() as tmp:
        csr = Path(tmp) / "req.csr"
        subprocess.run(  # noqa: S603 - fixed argv
            ["openssl", "req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
             "-keyout", str(key), "-out", str(csr), "-subj", f"/CN={domain}"],
            check=True, capture_output=True,
        )
        key.chmod(0o600)
        r = call("POST", "/certificates", {
            "hostnames": [domain, f"*.{domain}"],
            "requested_validity": 5475,
            "request_type": "origin-ecc",
            "csr": csr.read_text(),
        })
    cert.write_text(r["result"]["certificate"])
    cert.chmod(0o644)
    print(f"wrote {cert} and {key} (expires {r['result']['expires_on']})")


def sign_csr() -> None:
    """A CSR on stdin (from the server's `scorecode-ctl make-csr`), the Origin CA certificate on stdout.
    Only public material passes through here; the private key never leaves the server."""
    domain = _env("SCORECODE_DOMAIN")
    csr = sys.stdin.read(20000)
    if "BEGIN CERTIFICATE REQUEST" not in csr:
        sys.exit("cloudflare: no CSR on stdin")
    r = call("POST", "/certificates", {
        "hostnames": [domain, f"*.{domain}"],
        "requested_validity": 5475,
        "request_type": "origin-ecc",
        "csr": csr,
    })  # fmt: skip
    sys.stdout.write(r["result"]["certificate"].strip() + "\n")
    print(f"cloudflare: origin certificate issued (expires {r['result']['expires_on']})", file=sys.stderr)


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else ""
    if cmd == "dns-list":
        dns_list()
    elif cmd == "dns-plan":
        dns_plan()
    elif cmd == "dns-apply" and "--yes" in argv:
        dns_plan(apply=True)
    elif cmd == "settings":
        settings()
    elif cmd == "ssl-strict" and "--yes" in argv:
        ssl_strict()
    elif cmd == "sign-csr":
        sign_csr()
    elif cmd == "origin-cert" and len(argv) > 1:
        origin_cert(argv[1])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
