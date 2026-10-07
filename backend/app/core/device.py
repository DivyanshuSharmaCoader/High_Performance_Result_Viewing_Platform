"""A random, server-issued device id (one trial signal among several; docs/12 §6).

The cookie carries no personal data and nothing derived from the browser: just 32 random bytes. It is
scoped to the base domain, so the sign-up site and every ``<slug>.<base>`` portal see the same id — that's
how a second trial from the same browser is recognised. On a custom domain it is host-only. Anyone can
clear it, so it only ever *adds* to the other signals.
"""

from __future__ import annotations

import re
import secrets

from fastapi import Request, Response

from app.core.config import Settings

DEVICE_COOKIE = "sc_did"
DEVICE_MAX_AGE = 2 * 365 * 86_400
_VALID = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def device_id(request: Request) -> str | None:
    value = request.cookies.get(DEVICE_COOKIE)
    return value if value and _VALID.match(value) else None


def remember_device(request: Request, response: Response, settings: Settings) -> str:
    """The request's device id, issuing one (and setting the cookie) if it has none."""
    existing = device_id(request)
    if existing:
        return existing
    value = secrets.token_urlsafe(32)
    host = (request.headers.get("host") or "").split(":", 1)[0].lower()
    base = settings.base_domain.lower()
    shared = "." in base and (host == base or host.endswith(f".{base}"))
    response.set_cookie(
        DEVICE_COOKIE,
        value,
        max_age=DEVICE_MAX_AGE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        domain=base if shared else None,  # browsers refuse Domain= on single-label hosts like "localhost"
    )
    return value
