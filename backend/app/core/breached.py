"""Breached-password check (ASVS V2.1.7, NIST 800-63B §5.1.1.2) through Have I Been Pwned's range API.

k-anonymity: only the first five hex characters of the password's SHA-1 leave the server, and the response
is padded so its size reveals nothing either. If the service can't be reached in time the password is
**allowed** (fail open) and the miss is counted. Signing up must never depend on a third party being up.
The local common-password list and the length rules still apply.
"""

from __future__ import annotations

import hashlib
import urllib.request

import anyio

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.metrics import BREACH_CHECKS
from app.core.security import password_problems

log = get_logger(__name__)
RANGE_API = "https://api.pwnedpasswords.com/range/"
TIMEOUT_S = 2.0


def _fetch(prefix: str, timeout: float) -> str:
    request = urllib.request.Request(  # noqa: S310 - fixed https URL
        RANGE_API + prefix, headers={"Add-Padding": "true", "User-Agent": "ScoreCode password check"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return str(response.read().decode())


async def times_breached(password: str) -> int | None:
    """How often the password appears in known breaches; ``None`` when the check couldn't run."""
    digest = hashlib.sha1(password.encode()).hexdigest().upper()  # noqa: S324 - the API's format, not storage
    prefix, suffix = digest[:5], digest[5:]
    try:
        with anyio.fail_after(TIMEOUT_S + 0.5):
            body = await anyio.to_thread.run_sync(_fetch, prefix, TIMEOUT_S)
    except Exception as exc:
        BREACH_CHECKS.labels("unavailable").inc()
        log.warning("breach_check_unavailable", error_code=type(exc).__name__)
        return None
    for line in body.splitlines():
        candidate, _, count = line.strip().partition(":")
        if candidate == suffix:
            n = int(count or 0)  # padding lines have a count of 0
            BREACH_CHECKS.labels("breached" if n else "clean").inc()
            return n
    BREACH_CHECKS.labels("clean").inc()
    return 0


async def password_issues(
    password: str, *, min_length: int, context: tuple[str, ...], settings: Settings
) -> list[str]:
    """Every reason to refuse this password, local rules first (no network call if they already fail)."""
    problems = password_problems(password, min_length=min_length, context=context)
    if problems or not settings.breached_password_check:
        return problems
    n = await times_breached(password)
    if n:
        return [
            "This password has appeared in data breaches elsewhere, so attackers try it first. "
            "Choose one you haven't used before."
        ]
    return []
