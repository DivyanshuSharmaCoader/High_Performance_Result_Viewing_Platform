"""Staff management, invites & password reset by email, settings, subscription, sign-up and the platform
console (P3.8, P4.4, P4.7, P6.3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.conftest import unique_slug
from tests.helpers import (
    DEFAULT_PASSWORD,
    Client,
    drain_jobs,
    link_token,
    mailpit_latest,
    make_tenant,
    platform_client,
)

pytestmark = pytest.mark.integration

NEW_PASSWORD = "a-brand-new-passphrase-42"


async def _reauth(c: Client, password: str = DEFAULT_PASSWORD) -> None:
    assert (await c.post("/api/v1/auth/reauth", json={"password": password})).status_code == 200


# ---- staff & invites ----------------------------------------------------------------------------


async def test_invite_faculty_accept_by_email_and_sign_in(app, infra) -> None:
    t = await make_tenant(infra, plan="starter")
    email = f"teacher@{t.slug}.example.com"
    async with Client(app, t.host) as admin:
        await admin.login(t.owner_email)
        r = await admin.post(
            "/api/v1/admin/staff", json={"email": email, "full_name": "Meera Iyer", "role": "faculty"}
        )
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "invited"
    await drain_jobs(infra, ["notifications"])
    mail = await mailpit_latest(email)
    assert t.name in mail["subject"]
    token = link_token(mail["text"])
    assert f"{t.slug}.localhost" in mail["text"]  # links use the tenant's own host
    async with Client(app, t.host) as faculty:
        peek = await faculty.get(f"/api/v1/auth/invitations/{token}")
        assert peek.status_code == 200 and peek.json()["full_name"] == "Meera Iyer"
        r = await faculty.post(
            "/api/v1/auth/invitations/accept", json={"token": token, "password": NEW_PASSWORD}
        )
        assert r.status_code == 200, r.text
        assert r.json()["roles"] == ["faculty"]
        me = (await faculty.get("/api/v1/me")).json()
        assert "marks.enter_assigned" in me["permissions"]
        assert "students.manage" not in me["permissions"]
        # The invitation cannot be reused.
        again = await faculty.post(
            "/api/v1/auth/invitations/accept", json={"token": token, "password": NEW_PASSWORD}
        )
        assert again.status_code == 422
    # The invite email's job payload no longer contains the link (scrubbed after sending).
    async with infra.db.uow(t.id) as uow:
        payloads = (
            (
                await uow.session.execute(
                    text(
                        "SELECT payload::text FROM jobs WHERE kind = 'notifications.send_email' AND status = 'succeeded'"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert payloads and all(token not in p for p in payloads)


async def test_faculty_cannot_manage_staff(app, infra) -> None:
    t = await make_tenant(infra, plan="starter")
    email = f"f2@{t.slug}.example.com"
    async with Client(app, t.host) as admin:
        await admin.login(t.owner_email)
        await admin.post(
            "/api/v1/admin/staff", json={"email": email, "full_name": "Ravi K", "role": "faculty"}
        )
    await drain_jobs(infra, ["notifications"])
    token = link_token((await mailpit_latest(email))["text"])
    async with Client(app, t.host) as faculty:
        await faculty.post("/api/v1/auth/invitations/accept", json={"token": token, "password": NEW_PASSWORD})
        assert (await faculty.get("/api/v1/admin/staff")).status_code == 403
        r = await faculty.post(
            "/api/v1/admin/staff", json={"email": "x@y.com", "full_name": "Nope", "role": "faculty"}
        )
        assert r.status_code == 403
        assert (await faculty.get("/api/v1/admin/settings")).status_code == 403


async def test_admin_seat_limit_and_release_on_disable(app, infra) -> None:
    # Free plan: max_admins = 2 (the owner + one), max_staff = 5.
    t = await make_tenant(infra, plan="free")
    async with Client(app, t.host) as owner:
        await owner.login(t.owner_email)
        r = await owner.post(
            "/api/v1/admin/staff",
            json={
                "email": f"a@{t.slug}.example.com",
                "full_name": "Second Admin",
                "role": "institution_admin",
            },
        )
        assert r.status_code == 201, r.text
        r = await owner.post(
            "/api/v1/admin/staff",
            json={
                "email": f"b@{t.slug}.example.com",
                "full_name": "Third Admin",
                "role": "institution_admin",
            },
        )
        assert r.status_code == 402
        body = r.json()
        assert body["code"] == "limit-exceeded" and body["limit"] == "max_admins" and body["max"] == 2
        ids = []
        for i in range(3):
            r = await owner.post(
                "/api/v1/admin/staff",
                json={"email": f"f{i}@{t.slug}.example.com", "full_name": f"Faculty {i}", "role": "faculty"},
            )
            assert r.status_code == 201
            ids.append(r.json()["id"])
        r = await owner.post(
            "/api/v1/admin/staff",
            json={"email": f"f9@{t.slug}.example.com", "full_name": "One Too Many", "role": "faculty"},
        )
        assert r.status_code == 402 and r.json()["limit"] == "max_staff"
        assert (
            await owner.put(f"/api/v1/admin/staff/{ids[0]}/status", json={"disabled": True})
        ).status_code == 200
        r = await owner.post(
            "/api/v1/admin/staff",
            json={"email": f"f9@{t.slug}.example.com", "full_name": "Now Fits", "role": "faculty"},
        )
        assert r.status_code == 201
        sub = (await owner.get("/api/v1/admin/subscription")).json()
        staff_limit = next(x for x in sub["limits"] if x["key"] == "max_staff")
        assert staff_limit == {
            "key": "max_staff",
            "description": staff_limit["description"],
            "limit": 5,
            "used": 5,
        }


async def test_role_change_requires_recent_password_confirmation(app, infra) -> None:
    t = await make_tenant(infra, plan="growth")
    async with Client(app, t.host) as owner:
        await owner.login(t.owner_email)
        r = await owner.post(
            "/api/v1/admin/staff",
            json={"email": f"x@{t.slug}.example.com", "full_name": "Promote Me", "role": "faculty"},
        )
        uid = r.json()["id"]
        # Re-auth window: login counts as recent auth; simulate an old session by clearing it.
        async with infra.db.uow(t.id) as uow:
            await uow.session.execute(
                text("UPDATE sessions SET reauthenticated_at = now() - interval '1 hour'")
            )
        await infra.cache.local.delete(*[k for k in list(infra.cache.local._data) if k.startswith("sess:")])
        if infra.cache.redis is not None:
            keys = await infra.cache.redis.keys("sess:*")
            if keys:
                await infra.cache.redis.delete(*keys)
        r = await owner.put(f"/api/v1/admin/staff/{uid}/role", json={"role": "institution_admin"})
        assert r.status_code == 401 and r.json()["code"] == "reauth-required"
        assert (
            await owner.post("/api/v1/auth/reauth", json={"password": "wrong-password-x"})
        ).status_code == 401
        await _reauth(owner)
        r = await owner.put(f"/api/v1/admin/staff/{uid}/role", json={"role": "institution_admin"})
        assert r.status_code == 200, r.text
        staff = (await owner.get("/api/v1/admin/staff")).json()
        assert next(s for s in staff if s["id"] == uid)["role"] == "institution_admin"
        me_id = (await owner.get("/api/v1/me")).json()["id"]
        r = await owner.put(f"/api/v1/admin/staff/{me_id}/role", json={"role": "faculty"})
        assert r.status_code == 403


async def test_password_reset_by_email_revokes_sessions(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as old_session:
        await old_session.login(t.owner_email)
        async with Client(app, t.host) as c:
            r = await c.post("/api/v1/auth/password/forgot", json={"identifier": t.owner_email})
            assert r.status_code == 202
            unknown = await c.post(
                "/api/v1/auth/password/forgot", json={"identifier": "ghost@nowhere.example.com"}
            )
            assert unknown.status_code == 202 and unknown.json() == r.json()  # no account enumeration
            await drain_jobs(infra, ["notifications"])
            token = link_token((await mailpit_latest(t.owner_email))["text"])
            weak = await c.post("/api/v1/auth/password/reset", json={"token": token, "password": "short"})
            assert weak.status_code == 422
            ok = await c.post("/api/v1/auth/password/reset", json={"token": token, "password": NEW_PASSWORD})
            assert ok.status_code == 200
            reuse = await c.post(
                "/api/v1/auth/password/reset", json={"token": token, "password": NEW_PASSWORD + "x"}
            )
            assert reuse.status_code == 422
            await c.login(t.owner_email, NEW_PASSWORD)
        await infra.cache.local.delete(*[k for k in list(infra.cache.local._data) if k.startswith("sess:")])
        if infra.cache.redis is not None:
            keys = await infra.cache.redis.keys("sess:*")
            if keys:
                await infra.cache.redis.delete(*keys)
        assert (await old_session.get("/api/v1/me")).status_code == 401


# ---- settings & subscription --------------------------------------------------------------------


async def test_settings_update_is_versioned_audited_and_entitlement_gated(app, infra) -> None:
    t = await make_tenant(infra, plan="free")
    async with Client(app, t.host) as owner:
        await owner.login(t.owner_email)
        s = (await owner.get("/api/v1/admin/settings")).json()
        payload = {**{k: s[k] for k in s if k not in ("special_codes", "version")}, "version": s["version"]}
        payload.update({"official_name": "Sunrise Public School", "address": "12 MG Road, Patiala"})
        r = await owner.put("/api/v1/admin/settings", json=payload)
        assert r.status_code == 200 and r.json()["version"] == s["version"] + 1
        stale = await owner.put("/api/v1/admin/settings", json=payload)
        assert stale.status_code == 409
        gated = await owner.put(
            "/api/v1/admin/settings",
            json={**payload, "version": s["version"] + 1, "approval_mode": "maker_checker"},
        )
        assert gated.status_code == 402 and gated.json()["feature"] == "maker_checker_approval"
        audit = (await owner.get("/api/v1/admin/audit-logs", params={"action": "settings."})).json()
        assert audit["items"][0]["after"]["official_name"] == "Sunrise Public School"
        assert audit["items"][0]["before"]["official_name"] == t.name


async def test_audit_viewer_paginates(app, infra) -> None:
    t = await make_tenant(infra, plan="starter")
    async with Client(app, t.host) as owner:
        await owner.login(t.owner_email)
        for i in range(5):
            await owner.post(
                "/api/v1/admin/staff",
                json={"email": f"p{i}@{t.slug}.example.com", "full_name": f"P {i}", "role": "faculty"},
            )
        page1 = (await owner.get("/api/v1/admin/audit-logs", params={"limit": 3})).json()
        assert len(page1["items"]) == 3 and page1["next_cursor"]
        page2 = (
            await owner.get("/api/v1/admin/audit-logs", params={"limit": 3, "cursor": page1["next_cursor"]})
        ).json()
        ids1 = {i["id"] for i in page1["items"]}
        assert ids1.isdisjoint({i["id"] for i in page2["items"]})
        bad = await owner.get("/api/v1/admin/audit-logs", params={"cursor": "%%%"})
        assert bad.status_code == 422


# ---- sign-up ------------------------------------------------------------------------------------


async def test_self_serve_signup_end_to_end(app, infra) -> None:
    slug = unique_slug("s")
    email = f"principal@{slug}.example.com"
    async with Client(app, "localhost", ip="203.0.113.200") as site:
        avail = (await site.get("/api/v1/signup/slug-availability", params={"slug": slug})).json()
        assert avail["available"] is True and avail["host"] == f"{slug}.localhost"
        reserved = (await site.get("/api/v1/signup/slug-availability", params={"slug": "admin"})).json()
        assert reserved["available"] is False
        r = await site.post(
            "/api/v1/signup",
            json={
                "email": email,
                "full_name": "Anita Desai",
                "institution_name": "Sunrise Coaching Centre",
                "institution_type": "coaching",
                "slug": slug,
                "password": NEW_PASSWORD,
            },
        )
        assert r.status_code == 202, r.text
        # Nothing exists until the email is verified.
        assert (await site.get("/api/v1/signup/slug-availability", params={"slug": slug})).json()["available"]
        await drain_jobs(infra, ["notifications"])
        token = link_token((await mailpit_latest(email))["text"])
        v = await site.post("/api/v1/signup/verify", json={"token": token})
        assert v.status_code == 200, v.text
        handoff = link_token(v.json()["handoff_url"], "handoff")
        assert (await site.post("/api/v1/signup/verify", json={"token": token})).status_code == 422
        # Sign-up endpoints don't exist on tenant hosts, and tenant auth doesn't exist on the site host.
        assert (await site.post("/api/v1/auth/handoff", json={"token": handoff})).status_code == 404
    async with Client(app, f"{slug}.localhost") as tenant:
        r = await tenant.post("/api/v1/auth/handoff", json={"token": handoff})
        assert r.status_code == 200, r.text
        me = (await tenant.get("/api/v1/me")).json()
        assert me["roles"] == ["institution_owner"] and me["plan"]["code"] == "free"
        assert me["tenant"]["name"] == "Sunrise Coaching Centre"
        assert (await tenant.post("/api/v1/auth/handoff", json={"token": handoff})).status_code == 422
    async with Client(app, f"{slug}.localhost") as tenant:
        await tenant.login(email, NEW_PASSWORD)


async def test_signup_validation(app, infra) -> None:
    async with Client(app, "localhost", ip="203.0.113.201") as site:
        base = {
            "email": "x@mailinator.com",
            "full_name": "Test Person",
            "institution_name": "Some School",
            "institution_type": "school",
            "slug": unique_slug("v"),
            "password": NEW_PASSWORD,
        }
        assert (await site.post("/api/v1/signup", json=base)).json()["field"] == "email"
        r = await site.post("/api/v1/signup", json={**base, "email": "ok@school.example.com", "slug": "www"})
        assert r.status_code == 422 and r.json()["field"] == "slug"
        r = await site.post(
            "/api/v1/signup", json={**base, "email": "ok@school.example.com", "password": "password123"}
        )
        assert r.status_code == 422 and r.json()["field"] == "password"


async def test_signup_bots_that_fill_the_hidden_field_get_a_normal_answer_and_nothing_else(
    app, infra
) -> None:
    from sqlalchemy import func, select, text

    from app.modules.identity.models import SignupRequest

    slug = unique_slug("bot")
    email = f"bot-{uuid.uuid4().hex[:8]}@school.example.com"
    async with Client(app, "localhost", ip="203.0.113.202") as site:
        r = await site.post(
            "/api/v1/signup",
            json={
                "email": email,
                "full_name": "Bot Person",
                "institution_name": "Bot School",
                "institution_type": "school",
                "slug": slug,
                "password": NEW_PASSWORD,
                "website": "http://spam.example",
            },
        )
        assert r.status_code == 202 and r.json() == {"email": email}  # indistinguishable from a real one
    async with infra.db.platform_uow() as uow:
        stored = await uow.session.scalar(
            select(func.count()).select_from(SignupRequest).where(SignupRequest.slug == slug)
        )
        mails = await uow.session.scalar(
            text("SELECT count(*) FROM jobs WHERE payload->'params'->>'to' = :to"), {"to": email}
        )
    assert (stored, mails) == (0, 0)


# ---- platform console ---------------------------------------------------------------------------


async def test_platform_suspend_reactivate_and_plan_change(app, infra) -> None:
    t = await make_tenant(infra, plan="free", name="Kendriya Test School")
    async with Client(app, t.host) as tenant_user:
        await tenant_user.login(t.owner_email)
        assert (await tenant_user.get("/api/v1/me")).json()["plan"]["code"] == "free"
        console = await platform_client(app, infra)
        async with console:
            listing = (await console.get("/api/v1/platform/tenants", params={"q": t.slug})).json()
            assert listing["total"] == 1 and listing["items"][0]["plan_code"] == "free"
            detail = (await console.get(f"/api/v1/platform/tenants/{t.id}")).json()
            assert detail["users"]["staff"] == 1
            r = await console.put(
                f"/api/v1/platform/tenants/{t.id}/plan",
                json={
                    "plan_code": "growth",
                    "reason": "Annual invoice INV-001 paid",
                    "billing_ref": "INV-001",
                },
            )
            assert r.status_code == 200, r.text
            assert (await tenant_user.get("/api/v1/me")).json()["plan"]["code"] == "growth"
            r = await console.put(
                f"/api/v1/platform/tenants/{t.id}/overrides/max_students",
                json={"value": 2500, "reason": "Admission season boost"},
            )
            assert r.status_code == 200
            sub = (await tenant_user.get("/api/v1/admin/subscription")).json()
            assert next(x for x in sub["limits"] if x["key"] == "max_students")["limit"] == 2500
            bad = await console.put(
                f"/api/v1/platform/tenants/{t.id}/overrides/max_students",
                json={"value": True, "reason": "oops"},
            )
            assert bad.status_code == 422
            r = await console.post(f"/api/v1/platform/tenants/{t.id}/suspend", json={"reason": "Non-payment"})
            assert r.status_code == 200
            blocked = await tenant_user.get("/api/v1/me")
            assert blocked.status_code == 403 and blocked.json()["code"] == "tenant-unavailable"
            r = await console.post(f"/api/v1/platform/tenants/{t.id}/reactivate", json={"reason": "Paid"})
            assert r.status_code == 200
            # Suspension revoked all sessions: the user must sign in again.
            assert (await tenant_user.get("/api/v1/me")).status_code == 401
            await tenant_user.login(t.owner_email)
            audit = (await tenant_user.get("/api/v1/admin/audit-logs", params={"action": "tenant."})).json()
            actions = {i["action"] for i in audit["items"]}
            assert {"tenant.suspended", "tenant.reactivated", "tenant.plan_changed"} <= actions
            paudit = (
                await console.get("/api/v1/platform/audit-logs", params={"tenant_id": str(t.id)})
            ).json()
            assert {i["action"] for i in paudit["items"]} >= {
                "tenant.suspended",
                "tenant.plan_changed",
                "tenant.override_set",
            }
            overview = (await console.get("/api/v1/platform/metrics/overview")).json()
            assert overview["tenants"]["by_status"]["active"] >= 1
            health = (await console.get("/api/v1/platform/health/deep")).json()
            assert {c["name"]: c["status"] for c in health["checks"]}["database"] == "up"


async def test_readonly_platform_role_cannot_manage(app, infra) -> None:
    t = await make_tenant(infra)
    console = await platform_client(app, infra, role="readonly")
    async with console:
        assert (await console.get("/api/v1/platform/tenants")).status_code == 200
        r = await console.post(f"/api/v1/platform/tenants/{t.id}/suspend", json={"reason": "should fail"})
        assert r.status_code == 403
        assert (await console.get("/api/v1/platform/audit-logs")).status_code == 403


async def test_platform_api_is_unreachable_from_tenant_hosts_and_anonymous(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        assert (await c.get("/api/v1/platform/tenants")).status_code == 404
    async with Client(app, "admin.localhost") as anon:
        assert (await anon.get("/api/v1/platform/tenants")).status_code == 401


async def test_onboarding_checklist_reflects_data(app, infra) -> None:
    t = await make_tenant(infra, plan="starter")
    async with Client(app, t.host) as owner:
        await owner.login(t.owner_email)
        data = (await owner.get("/api/v1/admin/onboarding")).json()
        keys = [s["key"] for s in data["steps"]]
        assert keys[:4] == ["profile", "logo", "staff", "structure"]
        assert data["completed"] == 0 and not data["dismissed"]
        s = (await owner.get("/api/v1/admin/settings")).json()
        payload = {k: s[k] for k in s if k not in ("special_codes", "version")}
        payload.update(version=s["version"], address="1 College Road", contact_email="office@example.com")
        assert (await owner.put("/api/v1/admin/settings", json=payload)).status_code == 200
        await owner.post(
            "/api/v1/admin/staff",
            json={"email": f"t@{t.slug}.example.com", "full_name": "T T", "role": "faculty"},
        )
        data = (await owner.get("/api/v1/admin/onboarding")).json()
        done = {s["key"]: s["done"] for s in data["steps"]}
        assert done["profile"] and done["staff"] and not done["logo"]
        dismissed = (await owner.put("/api/v1/admin/onboarding", json={"dismissed": True})).json()
        assert dismissed["dismissed"] is True


async def test_platform_user_rejects_invalid_totp_secret(infra) -> None:
    from app.core.errors import ValidationFailed
    from app.modules.platform.bootstrap import create_platform_user

    with pytest.raises(ValidationFailed):
        await create_platform_user(
            infra,
            "bad-totp@ops.example.com",
            "Bad Secret",
            "platform-pass-12345",
            totp_secret="NOT-BASE32-0189",
        )


async def test_demo_seed_platform_secret_is_usable(app, infra) -> None:
    """The documented demo console account must actually be able to sign in."""
    from app.seed import DEMO_PASSWORD, DEMO_PLATFORM_EMAIL, DEMO_PLATFORM_TOTP, seed_platform_user
    from tests.helpers import totp_now

    await seed_platform_user(infra)
    async with Client(app, "admin.localhost") as c:
        r = await c.post(
            "/api/v1/platform/auth/login",
            json={
                "email": DEMO_PLATFORM_EMAIL,
                "password": DEMO_PASSWORD,
                "totp_code": totp_now(DEMO_PLATFORM_TOTP),
            },
        )
        assert r.status_code == 200, r.text
