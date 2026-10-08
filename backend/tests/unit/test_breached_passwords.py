"""Breached-password check (ASVS V2.1.7): k-anonymity range lookup, padding, failing open."""

from __future__ import annotations

import hashlib

import pytest

from app.core import breached
from tests.conftest import make_settings

PASSWORD = "correct horse battery staple"
DIGEST = hashlib.sha1(PASSWORD.encode()).hexdigest().upper()  # noqa: S324 - the API's format


def _serve(monkeypatch: pytest.MonkeyPatch, body: str, seen: list[str]) -> None:
    def fetch(prefix: str, timeout: float) -> str:
        seen.append(prefix)
        return body

    monkeypatch.setattr(breached, "_fetch", fetch)


async def test_only_five_characters_of_the_hash_leave_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    _serve(monkeypatch, f"0018A45C4D1DEF81644B54AB7F969B88D65:3\r\n{DIGEST[5:]}:3861493\r\n", seen)
    assert await breached.times_breached(PASSWORD) == 3861493
    assert seen == [DIGEST[:5]] and len(seen[0]) == 5


async def test_padding_lines_and_unknown_passwords_count_as_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, f"{DIGEST[5:]}:0\r\nABCDEF0123456789ABCDEF0123456789ABC:12\r\n", [])
    assert await breached.times_breached(PASSWORD) == 0
    _serve(monkeypatch, "ABCDEF0123456789ABCDEF0123456789ABC:12\r\n", [])
    assert await breached.times_breached(PASSWORD) == 0


async def test_an_unreachable_service_lets_the_password_through(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(prefix: str, timeout: float) -> str:
        raise TimeoutError("no route")

    monkeypatch.setattr(breached, "_fetch", down)
    assert await breached.times_breached(PASSWORD) is None
    on = make_settings(breached_password_check=True)
    assert await breached.password_issues(PASSWORD, min_length=12, context=(), settings=on) == []


async def test_password_issues_refuses_breached_passwords_and_skips_the_lookup_for_bad_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    _serve(monkeypatch, f"{DIGEST[5:]}:42\r\n", seen)
    on = make_settings(breached_password_check=True)
    issues = await breached.password_issues(PASSWORD, min_length=12, context=(), settings=on)
    assert len(issues) == 1 and "data breaches" in issues[0]
    assert await breached.password_issues("short", min_length=12, context=(), settings=on) == [
        "Use at least 12 characters."
    ]
    assert seen == [DIGEST[:5]]  # the short one never left the server
    off = make_settings(breached_password_check=False)
    assert await breached.password_issues(PASSWORD, min_length=12, context=(), settings=off) == []
