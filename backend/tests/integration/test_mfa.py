"""Two-step sign-in for staff (P15.5; ASVS V2.7, V2.8)."""

from __future__ import annotations

import re
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
from sqlalchemy import select

from app.core import clock
from app.modules.identity.models import User
from tests.helpers import DEFAULT_PASSWORD, Client, make_tenant, make_user

pytestmark = pytest.mark.integration


def _shift(monkeypatch: pytest.MonkeyPatch, seconds: int) -> None:
    """Move the server's clock forward (each authenticator code works once, so tests need fresh steps)."""
    real = clock.utcnow.__wrapped__ if hasattr(clock.utcnow, "__wrapped__") else clock.utcnow

    def later():  # type: ignore[no-untyped-def]
        return real() + timedelta(seconds=seconds)

    for module in ("app.modules.identity.service", "app.modules.identity.mfa"):
        monkeypatch.setattr(f"{module}.utcnow", later)


def _code(secret: str, seconds: int = 0) -> str:
    return pyotp.TOTP(secret).at(clock.utcnow() + timedelta(seconds=seconds))


async def _login(c: Client, login: str, code: str | None = None):  # type: ignore[no-untyped-def]
    body = {"login_id": login, "password": DEFAULT_PASSWORD}
    if code is not None:
        body["totp_code"] = code
    return await c.post("/api/v1/auth/login", json=body)


async def _failures(infra, tenant_id, email: str) -> int:  # type: ignore[no-untyped-def]
    async with infra.db.uow(tenant_id) as uow:
        return (
            await uow.session.scalars(select(User.failed_login_count).where(User.login_id == email))
        ).one()


async def _notices(infra, tenant_id) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    """Security notices queued for sending (ASVS 2.2.3), oldest first: (to, what happened)."""
    from sqlalchemy import text

    async with infra.db.uow(tenant_id) as uow:
        rows = (
            await uow.session.execute(
                text(
                    "SELECT payload->'params'->>'to' AS to_, payload->'params'->>'what' AS what FROM jobs"
                    " WHERE kind = 'notifications.send_email' AND payload->>'template' = 'security_notice'"
                    " ORDER BY created_at, id"
                )
            )
        ).all()
    return [(r.to_, r.what) for r in rows]


async def test_turning_on_two_step_sign_in_then_signing_in_with_codes(app, infra, monkeypatch) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        assert (await c.get("/api/v1/me")).json()["mfa_enabled"] is False
        setup = await c.post("/api/v1/me/mfa/setup")
        assert setup.status_code == 200 and setup.headers["cache-control"] == "private, no-store"
        s = setup.json()
        uri = urlparse(s["uri"])
        assert uri.scheme == "otpauth" and parse_qs(uri.query)["secret"] == [s["secret"]]
        assert parse_qs(uri.query)["issuer"] == ["ScoreCode"]
        assert s["qr_svg"].startswith("data:image/svg+xml")
        assert (await c.post("/api/v1/me/mfa/enable", json={"code": "000000"})).status_code == 422
        enabled = await c.post("/api/v1/me/mfa/enable", json={"code": _code(s["secret"])})
        assert enabled.status_code == 200, enabled.text
        codes = enabled.json()["recovery_codes"]
        assert len(codes) == 10 and all(
            re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{5}-[0-9A-HJKMNP-TV-Z]{5}", x) for x in codes
        )
        assert (await c.get("/api/v1/me")).json()["mfa_enabled"] is True
        assert (await c.get("/api/v1/me/mfa")).json()["recovery_codes_left"] == 10
        audit = (await c.get("/api/v1/admin/audit-logs", params={"action": "user.mfa_"})).json()["items"]
        assert [i["action"] for i in audit] == ["user.mfa_enabled"]
        assert s["secret"] not in str(audit)

    async with Client(app, t.host) as c:
        # The right password alone: asked for the code, and it isn't a failed attempt.
        r = await _login(c, t.owner_email)
        assert r.status_code == 401 and r.json()["code"] == "totp-required"
        assert c.session_cookie() is None
        assert await _failures(infra, t.id, t.owner_email) == 0
        # A wrong code is a failed sign-in.
        r = await _login(c, t.owner_email, "123456")
        assert r.status_code == 401 and r.json()["code"] == "invalid-credentials"
        assert await _failures(infra, t.id, t.owner_email) == 1
        # The next step's code works (the current one was used to turn it on)...
        _shift(monkeypatch, 30)
        good = _code(s["secret"], 30)
        assert (await _login(c, t.owner_email, good)).status_code == 200
        assert await _failures(infra, t.id, t.owner_email) == 0
    async with Client(app, t.host) as c:
        # ...once: replaying it is refused.
        assert (await _login(c, t.owner_email, good)).status_code == 401
        # A recovery code works once, typed any old way, and leaves a trail.
        assert (await _login(c, t.owner_email, codes[0].lower().replace("-", " "))).status_code == 200
    async with Client(app, t.host) as c:
        assert (await _login(c, t.owner_email, codes[0])).status_code == 401
        _shift(monkeypatch, 60)
        assert (await _login(c, t.owner_email, _code(s["secret"], 60))).status_code == 200
        assert (await c.get("/api/v1/me/mfa")).json()["recovery_codes_left"] == 9
        audit = (await c.get("/api/v1/admin/audit-logs", params={"action": "auth.recovery"})).json()["items"]
        assert audit[0]["after"] == {"recovery_codes_left": 9}

        # Confirming identity for a sensitive action asks for both factors again.
        r = await c.post("/api/v1/auth/reauth", json={"password": DEFAULT_PASSWORD})
        assert r.status_code == 401 and r.json()["code"] == "totp-required"
        _shift(monkeypatch, 90)
        r = await c.post(
            "/api/v1/auth/reauth", json={"password": DEFAULT_PASSWORD, "totp_code": _code(s["secret"], 90)}
        )
        assert r.status_code == 200, r.text

        # New recovery codes replace the old ones; turning it off needs a code too.
        _shift(monkeypatch, 120)
        fresh = (await c.post("/api/v1/me/mfa/recovery-codes", json={"code": _code(s["secret"], 120)})).json()
        assert len(fresh["recovery_codes"]) == 10 and not set(fresh["recovery_codes"]) & set(codes)
        assert (await c.post("/api/v1/me/mfa/disable", json={"code": codes[1]})).status_code == 422  # old set
        assert (
            await c.post("/api/v1/me/mfa/disable", json={"code": fresh["recovery_codes"][0]})
        ).status_code == 200
        assert (await c.get("/api/v1/me")).json()["mfa_enabled"] is False
    async with Client(app, t.host) as c:
        assert (await _login(c, t.owner_email)).status_code == 200  # password alone again
    # The owner heard about every change, by email; the refused attempts (a wrong code) sent nothing.
    assert await _notices(infra, t.id) == [
        (t.owner_email, "Two-step sign-in was turned on"),
        (t.owner_email, "A recovery code was used to sign in (9 left)"),
        (t.owner_email, "New recovery codes were created, and the old ones no longer work"),
        (t.owner_email, "Two-step sign-in was turned off"),
    ]


async def test_a_lost_phone_is_reset_by_an_administrator_but_never_the_owners(
    app, infra, monkeypatch
) -> None:
    t = await make_tenant(infra)
    admin_id, admin_login = await make_user(infra, t, "institution_admin")
    other_id, other_login = await make_user(infra, t, "institution_admin")

    async def turn_on(login: str) -> None:
        async with Client(app, t.host) as c:
            await c.login(login)
            secret = (await c.post("/api/v1/me/mfa/setup")).json()["secret"]
            assert (await c.post("/api/v1/me/mfa/enable", json={"code": _code(secret)})).status_code == 200

    await turn_on(other_login)
    await turn_on(t.owner_email)
    async with Client(app, t.host) as c:
        await c.login(admin_login)  # a fresh sign-in counts as recent confirmation
        r = await c.post(f"/api/v1/admin/staff/{other_id}/mfa/reset")
        assert r.status_code == 200, r.text
        async with infra.db.uow(t.id) as uow:
            owner_id = (
                await uow.session.scalars(select(User.id).where(User.login_id == t.owner_email))
            ).one()
        r = await c.post(f"/api/v1/admin/staff/{owner_id}/mfa/reset")
        assert r.status_code == 403
        assert (await c.post(f"/api/v1/admin/staff/{admin_id}/mfa/reset")).status_code == 409  # not your own
        audit = (await c.get("/api/v1/admin/audit-logs", params={"action": "user.mfa_reset"})).json()["items"]
        assert len(audit) == 1 and audit[0]["entity_id"] == str(other_id)
    async with Client(app, t.host) as c:
        assert (await _login(c, other_login)).status_code == 200  # back to a password; set it up again
    resets = [n for n in await _notices(infra, t.id) if "reset your two-step" in n[1]]
    assert len(resets) == 1 and resets[0][0] == other_login  # told, by email, who reset it


async def test_students_and_faculty_without_permission_get_no_two_step_controls(app, infra) -> None:
    t = await make_tenant(infra)
    _, student = await make_user(infra, t, "student")
    _, faculty = await make_user(infra, t, "faculty")
    async with Client(app, t.host) as c:
        await c.login(student)
        assert (await c.post("/api/v1/me/mfa/setup")).status_code == 403
    async with Client(app, t.host) as c:
        await c.login(faculty)
        assert (
            await c.post("/api/v1/me/mfa/setup")
        ).status_code == 200  # any staff member may protect themselves
        assert (await c.post(f"/api/v1/admin/staff/{faculty}/mfa/reset")).status_code in (403, 422)


async def test_reencrypting_after_a_secret_key_change_keeps_two_step_working(app, infra) -> None:
    """docs/runbooks/security-incident.md: rotate SCORECODE_SECRET_KEY without locking anyone out."""
    from sqlalchemy import text

    from app.core.security import FieldCipher
    from app.modules.identity.key_rotation import reencrypt_secrets

    old_key = "the-previous-secret-key-0123456789abcdef"
    t = await make_tenant(infra)
    async with infra.db.uow(t.id) as uow:
        user_id = (await uow.session.execute(text("SELECT id FROM users LIMIT 1"))).scalar_one()
        await uow.session.execute(
            text("UPDATE users SET totp_secret_enc = :v WHERE id = :id"),
            {"v": FieldCipher(old_key).encrypt("JBSWY3DPEHPK3PXP"), "id": user_id},
        )
    dry = await reencrypt_secrets(infra, old_key, dry_run=True)
    assert dry.reencrypted >= 1 and not dry.unreadable
    report = await reencrypt_secrets(infra, old_key)
    assert report.reencrypted == dry.reencrypted
    async with infra.db.uow(t.id) as uow:
        stored = (
            await uow.session.execute(
                text("SELECT totp_secret_enc FROM users WHERE id = :id"), {"id": user_id}
            )
        ).scalar_one()
    assert infra.cipher.decrypt(stored) == "JBSWY3DPEHPK3PXP"  # readable with the current key now
    again = await reencrypt_secrets(infra, old_key)
    assert again.reencrypted == 0 and again.already_new >= 1  # safe to run twice
