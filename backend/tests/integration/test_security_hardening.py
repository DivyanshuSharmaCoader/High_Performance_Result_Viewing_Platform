"""Security tests completing P15.3 (docs/15 §4): enumeration, headers on every kind of response, secrets kept
out of logs, and production cookie flags. Upload attacks, CSRF and mass assignment have their own suites
(test_imports.py, test_auth.py)."""

from __future__ import annotations

import json

import pytest
from structlog.testing import capture_logs

from app.main import create_app
from tests.conftest import make_settings
from tests.helpers import DEFAULT_PASSWORD, Client, make_student, make_tenant

pytestmark = pytest.mark.integration

HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}


async def test_activation_never_says_whether_an_enrollment_number_exists(app, infra) -> None:
    t = await make_tenant(infra)
    await make_student(infra, t, enrollment_no="ENUM001")
    async with Client(app, t.host) as c:
        known = await c.post(
            "/api/v1/auth/activate",
            json={"enrollment_no": "ENUM001", "code": "AAAA-BBBB-CC", "password": "a-long-student-pass"},
        )
        unknown = await c.post(
            "/api/v1/auth/activate",
            json={"enrollment_no": "NOPE999", "code": "AAAA-BBBB-CC", "password": "a-long-student-pass"},
        )
    assert known.status_code == unknown.status_code == 422
    strip = lambda r: {k: v for k, v in r.json().items() if k != "request_id"}  # noqa: E731
    assert strip(known) == strip(unknown)


async def test_security_headers_are_on_errors_too(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        responses = {
            "ok": await c.get("/api/v1/tenant/config"),
            "401": await c.get("/api/v1/me"),
            "404 route": await c.get("/api/v1/no-such-thing"),
            "403 csrf": await c.http.post("/api/v1/auth/logout-all"),
            "422": await c.post("/api/v1/auth/login", json={}),
        }
    async with Client(app, "unknown-institution.localhost") as c:
        responses["404 host"] = await c.get("/api/v1/tenant/config")
    for name, r in responses.items():
        for header, value in HEADERS.items():
            assert r.headers.get(header) == value, (name, header, r.headers.get(header))
        assert "default-src 'none'" in r.headers["content-security-policy"], name
        if name != "ok":  # (tenant config is public and briefly cacheable by design)
            assert "no-store" in r.headers["cache-control"], name
        assert "server" not in {k.lower() for k in r.headers if r.headers[k].lower().startswith("uvicorn")}


async def test_passwords_tokens_and_codes_never_reach_the_logs(app, infra) -> None:
    t = await make_tenant(infra)
    secret_password = "Never-Log-This-Passw0rd"
    with capture_logs() as logs:
        async with Client(app, t.host) as c:
            await c.post("/api/v1/auth/login", json={"login_id": t.owner_email, "password": secret_password})
            await c.post("/api/v1/auth/login", json={"login_id": t.owner_email, "password": DEFAULT_PASSWORD})
            token = c.session_cookie()
            await c.post(
                "/api/v1/auth/activate",
                json={"enrollment_no": "X1", "code": "SECRETCODE99", "password": secret_password},
            )
    dumped = json.dumps(logs, default=str)
    assert token and token not in dumped
    for secret in (secret_password, DEFAULT_PASSWORD, "SECRETCODE99"):
        assert secret not in dumped, secret


async def test_production_cookies_carry_every_protection(migrated_db: str) -> None:
    import httpx

    from app.core.container import Infra

    settings = make_settings(cookie_secure=True, redis_url=None)
    infra = Infra.build(settings, app_name="scorecode-test-secure-cookies")  # app and services agree
    prod_like = create_app(settings, infra)
    t = await make_tenant(infra)
    # Secure cookies only travel over https, as in a browser.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=prod_like, client=("10.9.8.7", 1234)), base_url=f"https://{t.host}"
    ) as c:
        await c.get("/api/v1/auth/csrf")
        r = await c.post(
            "/api/v1/auth/login",
            json={"login_id": t.owner_email, "password": DEFAULT_PASSWORD},
            headers={"X-CSRF-Token": c.cookies.get("__Host-sc_csrf") or ""},
        )
    assert r.status_code == 200, r.text
    session = next(h for h in r.headers.get_list("set-cookie") if h.startswith("__Host-sc_session="))
    flags = {part.strip().lower() for part in session.split(";")[1:]}
    assert {"httponly", "secure", "path=/", "samesite=lax"} <= flags
    assert not any(f.startswith("domain=") for f in flags)  # __Host-: bound to this exact host
    assert r.headers["strict-transport-security"].startswith("max-age=31536000")
    await infra.close()
