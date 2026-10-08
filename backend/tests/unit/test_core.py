from __future__ import annotations

import time
import uuid

import pytest

from app.core.config import DEV_SECRET, Environment, Settings
from app.core.ids import uuid7, uuid7_timestamp_ms
from app.core.logging import REDACTED, scrub_processor
from app.core.security import crockford_base32, human_code, normalise_human_code, password_problems
from app.core.tenant import Realm, classify_host

# ---- configuration (P1.2) -----------------------------------------------------------------------


def test_development_defaults_are_valid() -> None:
    s = Settings(env=Environment.DEVELOPMENT)
    assert s.session_cookie_name == "sc_session"
    assert s.platform_host == "admin.localhost"


def test_production_rejects_dev_secret_and_insecure_cookies() -> None:
    with pytest.raises(ValueError, match="Unsafe production configuration") as exc:
        Settings(env=Environment.PRODUCTION, secret_key=DEV_SECRET)
    message = str(exc.value)
    assert "SECRET_KEY" in message
    assert "COOKIE_SECURE" in message
    assert "development password" in message
    assert "EXPOSE_DOCS" in message  # no public API map in production


def test_production_accepts_safe_configuration() -> None:
    s = Settings(
        env=Environment.PRODUCTION,
        secret_key="x" * 48,
        abuse_signal_key="y" * 48,
        cookie_secure=True,
        public_scheme="https",
        expose_docs=False,
        s3_secret_key="prod-secret-value",
        database_url_app="postgresql+asyncpg://scorecode_app:Str0ng@db/scorecode",
        database_url_platform="postgresql+asyncpg://scorecode_platform:Str0ng@db/scorecode",
        database_url_migrator="postgresql+asyncpg://scorecode_migrator:Str0ng@db/scorecode",
    )
    assert s.session_cookie_name == "__Host-sc_session"
    assert s.csrf_cookie_name == "__Host-sc_csrf"


def test_short_secret_rejected_everywhere() -> None:
    with pytest.raises(ValueError):
        Settings(secret_key="short")


# ---- ids (P2.2) ---------------------------------------------------------------------------------


def test_uuid7_version_and_variant() -> None:
    u = uuid7()
    assert u.version == 7
    assert u.variant == uuid.RFC_4122


def test_uuid7_monotonic_within_process() -> None:
    ids = [uuid7() for _ in range(5000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_uuid7_timestamp_tracks_clock() -> None:
    before = time.time_ns() // 1_000_000
    u = uuid7()
    after = time.time_ns() // 1_000_000
    assert before <= uuid7_timestamp_ms(u) <= after + 1


# ---- log scrubbing (P2.11) ----------------------------------------------------------------------


def test_scrubber_removes_secrets_and_pii() -> None:
    event = {
        "event": "login",
        "password": "hunter2hunter2",
        "session_token": "abc",
        "headers": {"Authorization": "Bearer xyz", "accept": "json"},
        "student": {"full_name": "Asha Rao", "marks": {"INT": 35}},
        "note": "token=" + "A" * 50,
        "tenant_id": "t-1",
        "status": 200,
    }
    out = scrub_processor(None, "info", dict(event))
    assert out["password"] == REDACTED
    assert out["session_token"] == REDACTED
    assert out["headers"]["Authorization"] == REDACTED
    assert out["headers"]["accept"] == "json"
    assert out["student"]["full_name"] == REDACTED
    assert out["student"]["marks"] == REDACTED
    assert "A" * 50 not in out["note"]
    assert out["tenant_id"] == "t-1"
    assert out["status"] == 200


# ---- hosts (P2.4) -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "realm", "slug"),
    [
        ("thapar.localhost:8080", Realm.TENANT, "thapar"),
        ("THAPAR.localhost", Realm.TENANT, "thapar"),
        ("admin.localhost", Realm.PLATFORM, None),
        ("verify.localhost:8080", Realm.VERIFY, None),
        ("localhost:8080", Realm.SITE, None),
        ("www.localhost", Realm.SITE, None),
        ("results.abcschool.edu.in", Realm.TENANT, None),
    ],
)
def test_classify_host(host: str, realm: Realm, slug: str | None) -> None:
    info = classify_host(host, Settings())
    assert info is not None
    assert info.realm is realm
    assert info.slug == slug


@pytest.mark.parametrize(
    "host", [None, "", "a.b.localhost", "x.localhost", "-bad.localhost", "[::1]:80", "ev il.localhost"]
)
def test_classify_host_rejects_invalid(host: str | None) -> None:
    assert classify_host(host, Settings()) is None


# ---- small security helpers ---------------------------------------------------------------------


def test_human_codes_use_unambiguous_alphabet() -> None:
    for _ in range(200):
        code = human_code(10)
        assert len(code) == 10
        assert not set(code) & set("ILOU")


def test_normalise_human_code_maps_lookalikes() -> None:
    assert normalise_human_code(" ab-cd o1 il ") == "ABCD0111"


def test_crockford_base32_length() -> None:
    assert len(crockford_base32(bytes(16))) == 26


def test_password_rules() -> None:
    assert password_problems("short", min_length=10)
    assert password_problems("password123", min_length=10)
    assert password_problems("thapar-2025-secret", min_length=10, context=("thapar",))
    assert password_problems("a perfectly fine passphrase", min_length=10) == []
