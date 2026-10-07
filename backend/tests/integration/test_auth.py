"""Authentication, sessions and CSRF (P3.3–P3.5, P3.9)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.modules.identity.models import User
from tests.helpers import DEFAULT_PASSWORD, Client, make_tenant, make_user, totp_now

pytestmark = pytest.mark.integration


async def test_login_me_logout_roundtrip(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        r = await c.login(t.owner_email)
        assert r.json() == {"user_kind": "staff", "roles": ["institution_owner"]}
        cookie = r.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert "Domain=" not in cookie  # host-only: never shared with other tenants' subdomains
        me = await c.get("/api/v1/me")
        assert me.status_code == 200
        body = me.json()
        assert body["tenant"]["slug"] == t.slug
        assert "students.manage" in body["permissions"]
        assert body["plan"]["code"] == "free"
        assert (await c.post("/api/v1/auth/logout")).status_code == 200
        assert (await c.get("/api/v1/me")).status_code == 401


async def test_wrong_password_and_unknown_user_are_indistinguishable(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host, ip="198.51.100.1") as c:
        r1 = await c.post(
            "/api/v1/auth/login", json={"login_id": t.owner_email, "password": "wrong-password-1"}
        )
        r2 = await c.post("/api/v1/auth/login", json={"login_id": "nobody@example.com", "password": "x"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"]
    assert r1.json()["code"] == "invalid-credentials"


async def test_login_on_another_tenant_host_fails(app, infra) -> None:
    a = await make_tenant(infra)
    b = await make_tenant(infra)
    async with Client(app, b.host, ip="198.51.100.2") as c:
        r = await c.post("/api/v1/auth/login", json={"login_id": a.owner_email, "password": DEFAULT_PASSWORD})
    assert r.status_code == 401


async def test_session_cookie_replayed_on_other_tenant_host_is_rejected(app, infra) -> None:
    a = await make_tenant(infra)
    b = await make_tenant(infra)
    async with Client(app, a.host) as ca:
        await ca.login(a.owner_email)
        token = ca.session_cookie()
        assert token
    async with Client(app, b.host) as cb:
        r = await cb.get("/api/v1/me", headers={"Cookie": f"sc_session={token}"})
    assert r.status_code == 401


async def test_unsafe_request_without_csrf_token_is_rejected(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.ensure_csrf()
        r = await c.http.post(
            "/api/v1/auth/login", json={"login_id": t.owner_email, "password": DEFAULT_PASSWORD}
        )
        assert r.status_code == 403
        assert r.json()["code"] == "csrf-failed"
        r = await c.http.post(
            "/api/v1/auth/login",
            json={"login_id": t.owner_email, "password": DEFAULT_PASSWORD},
            headers={"X-CSRF-Token": "forged-value"},
        )
        assert r.status_code == 403


async def test_lockout_after_repeated_failures(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host, ip="198.51.100.3") as c:
        for _ in range(infra.settings.login_max_failures):
            r = await c.post(
                "/api/v1/auth/login", json={"login_id": t.owner_email, "password": "nope-nope-nope"}
            )
            assert r.status_code == 401
        # Correct password is refused while locked, with the same generic error.
        r = await c.post("/api/v1/auth/login", json={"login_id": t.owner_email, "password": DEFAULT_PASSWORD})
        assert r.status_code == 401
    async with infra.db.uow(t.id) as uow:
        user = (await uow.session.scalars(select(User).where(User.login_id == t.owner_email))).one()
        assert user.locked_until is not None
        actions = (
            (
                await uow.session.execute(
                    text("SELECT action FROM audit_logs WHERE action = 'user.login_locked'")
                )
            )
            .scalars()
            .all()
        )
        assert actions == ["user.login_locked"]


async def test_expired_and_revoked_sessions_are_rejected(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        assert (await c.get("/api/v1/me")).status_code == 200
        async with infra.db.uow(t.id) as uow:
            await uow.session.execute(text("UPDATE sessions SET expires_at = now() - interval '1 minute'"))
        await infra.cache.local.delete(*[k for k in list(infra.cache.local._data) if k.startswith("sess:")])
        if infra.cache.redis is not None:
            keys = await infra.cache.redis.keys("sess:*")
            if keys:
                await infra.cache.redis.delete(*keys)
        assert (await c.get("/api/v1/me")).status_code == 401
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        r = await c.post("/api/v1/auth/logout-all")
        assert r.status_code == 200 and r.json()["revoked"] >= 1
        assert (await c.get("/api/v1/me")).status_code == 401


async def test_failed_sign_ins_from_one_address_are_rate_limited_with_retry_after(app, infra) -> None:
    t = await make_tenant(infra)
    ip = f"198.51.100.{uuid.uuid4().int % 200 + 20}"
    async with Client(app, t.host, ip=ip) as c:
        responses = [
            await c.post("/api/v1/auth/login", json={"login_id": f"user{i}@x.com", "password": "nope"})
            for i in range(65)  # failures have a 60-attempt burst per address
        ]
        limited = [r for r in responses if r.status_code == 429]
        assert limited, [r.status_code for r in responses]
        assert int(limited[0].headers["retry-after"]) >= 1
        assert limited[0].json()["code"] == "rate-limited"
        # Once an address has failed this often, even a correct password waits.
        r = await c.post("/api/v1/auth/login", json={"login_id": t.owner_email, "password": DEFAULT_PASSWORD})
        assert r.status_code == 429


async def test_a_whole_class_signing_in_from_one_address_is_not_rate_limited(app, infra) -> None:
    """Result day: a school lab, or thousands of phones behind one mobile carrier's NAT, share an address.
    Successful sign-ins must not be throttled the way failures are."""
    t = await make_tenant(infra)
    logins = [(await make_user(infra, t, "student"))[1] for _ in range(80)]
    ip = f"198.51.100.{uuid.uuid4().int % 200 + 20}"
    codes = []
    for login in logins:
        async with Client(app, t.host, ip=ip) as c:
            r = await c.post("/api/v1/auth/login", json={"login_id": login, "password": DEFAULT_PASSWORD})
            codes.append(r.status_code)
    assert codes == [200] * 80


async def test_unknown_host_and_suspended_tenant(app, infra) -> None:
    async with Client(app, "doesnotexist1.localhost") as c:
        r = await c.get("/api/v1/tenant/config")
        assert r.status_code == 404
    t = await make_tenant(infra)
    async with infra.db.platform_uow() as uow:
        await uow.session.execute(
            text("UPDATE tenants SET status = 'suspended' WHERE id = :id"), {"id": t.id}
        )
    from app.modules.tenancy.service import TenantResolver

    await TenantResolver(infra).invalidate(t.slug)
    async with Client(app, t.host) as c:
        r = await c.get("/api/v1/tenant/config")
        assert r.status_code == 403
        assert r.json()["code"] == "tenant-unavailable"


async def test_platform_login_requires_totp_and_platform_host(app, infra) -> None:
    from app.modules.platform.bootstrap import create_platform_user

    email = f"ops-{totp_now('JBSWY3DPEHPK3PXP')}-{id(app)}@ops.example.com"
    created = await create_platform_user(infra, email, "Ops Person", "platform-pass-12345")
    t = await make_tenant(infra)
    # Platform endpoints don't exist on tenant hosts.
    async with Client(app, t.host) as c:
        r = await c.post(
            "/api/v1/platform/auth/login",
            json={
                "email": email,
                "password": "platform-pass-12345",
                "totp_code": totp_now(created.totp_secret),
            },
        )
        assert r.status_code == 404
    async with Client(app, "admin.localhost", ip="198.51.100.9") as c:
        r = await c.post(
            "/api/v1/platform/auth/login",
            json={"email": email, "password": "platform-pass-12345", "totp_code": "000000"},
        )
        assert r.status_code == 401
        r = await c.post(
            "/api/v1/platform/auth/login",
            json={
                "email": email,
                "password": "platform-pass-12345",
                "totp_code": totp_now(created.totp_secret),
            },
        )
        assert r.status_code == 200, r.text
        me = await c.get("/api/v1/platform/me")
        assert me.status_code == 200
        assert "platform.tenants.manage" in me.json()["permissions"]
        platform_cookie = c.session_cookie()
    # A platform session cookie is meaningless on a tenant host.
    async with Client(app, t.host) as c:
        r = await c.get("/api/v1/me", headers={"Cookie": f"sc_session={platform_cookie}"})
        assert r.status_code == 401


async def test_security_headers_present(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        r = await c.get("/api/v1/tenant/config")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-request-id"]


async def test_mass_assignment_is_rejected(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        r = await c.post(
            "/api/v1/auth/login",
            json={"login_id": t.owner_email, "password": DEFAULT_PASSWORD, "role": "institution_owner"},
        )
    assert r.status_code == 422
    assert r.json()["errors"][0]["message"] == "Unexpected field"
