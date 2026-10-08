"""The public verification page on the verify host (docs/03 W13, docs/10 §10; P11.5).

Server-rendered HTML with no scripts. It is never indexed, never cached when a statement is found (its
status can change), and rate-limited per address, with lookups refused in a friendly page rather than JSON.
Unknown codes and publications that never went live look exactly the same.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import PackageLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from app.core.errors import RateLimited
from app.core.http import InfraDep, client_ip, public
from app.core.ratelimit import VERIFY_PER_IP
from app.core.tenant import Realm
from app.modules.verification.codes import normalize
from app.modules.verification.service import Verification, VerificationService

router = APIRouter(tags=["verification"], include_in_schema=False)

_env = SandboxedEnvironment(
    loader=PackageLoader("app.modules.verification", "templates"),
    autoescape=True,
    undefined=StrictUndefined,
)
HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "Referrer-Policy": "no-referrer",  # the code is in the address: never pass it on
}
NOT_FOUND_CACHE = "public, max-age=60"  # a CDN may absorb repeated bad lookups briefly (docs/10 §10)

# status → (tone, icon, title, message)
STATES: dict[str, tuple[str, str, str, str]] = {
    "valid": ("ok", "✓", "Valid", "This statement of marks was issued by {institution} and is current."),
    "superseded": (
        "warn",
        "!",
        "Superseded",
        "A revised result was issued{on}. Ask the student for the latest statement of marks.",
    ),
    "withdrawn": ("bad", "✕", "Withdrawn", "The institution withdrew these results{on}."),
    "revoked": ("bad", "✕", "Revoked", "The institution revoked this statement{on}. It is no longer valid."),
    "institution_left": (
        "neutral",
        "?",
        "Can't be checked here",
        "{institution} no longer issues results through ScoreCode. Contact the institution to check this "
        "statement.",
    ),
}


def _date(value: datetime | None, timezone: str) -> str | None:
    if value is None:
        return None
    local = value.astimezone(ZoneInfo(timezone))
    return f"{local.day} {local:%B %Y}"


def _page(status_code: int, cache: str, **context: Any) -> HTMLResponse:
    context.setdefault("v", None)
    context.setdefault("error", None)
    context.setdefault("typed", None)
    html = _env.get_template("verify.html.j2").render(**context)
    return HTMLResponse(html, status_code=status_code, headers={**HEADERS, "Cache-Control": cache})


def _not_found(typed: str | None = None) -> HTMLResponse:
    return _page(
        404,
        NOT_FOUND_CACHE,
        tone="neutral",
        icon="?",
        title="No statement found",
        message="Check the code and try again. It has 26 letters and digits, printed beside the QR code.",
        typed=typed,
    )


def _limited(exc: RateLimited) -> HTMLResponse:
    response = _page(
        429,
        "no-store",
        tone="warn",
        icon="!",
        title="Too many lookups",
        message="Please wait a minute and try again.",
    )
    response.headers["Retry-After"] = str(exc.retry_after_s)
    return response


def _found(v: Verification) -> HTMLResponse:
    tone, icon, title, message = STATES[v.status]
    on = _date(v.status_at, v.timezone)
    return _page(
        200,
        "no-store",
        v=v,
        tone=tone,
        icon=icon,
        title=title,
        message=message.format(institution=v.institution, on=f" on {on}" if on else ""),
        issued_on=_date(v.issued_at, v.timezone),
    )


@router.get("/", dependencies=[public(Realm.VERIFY)])
async def verify_home() -> RedirectResponse:
    return RedirectResponse("/v", status_code=308)


@router.get("/v", dependencies=[public(Realm.VERIFY)])
async def verify_form(request: Request, infra: InfraDep, code: str | None = None) -> Any:
    if code is None or not code.strip():
        return _page(
            200,
            "public, max-age=300",
            tone="neutral",
            icon="✓",
            title="Verify a statement of marks",
            message="Enter the verification code from the statement, or scan its QR code.",
        )
    normalized = normalize(code[:64])
    if normalized is None:
        return _page(
            422,
            "no-store",
            tone="neutral",
            icon="?",
            title="Verify a statement of marks",
            message="Enter the verification code from the statement, or scan its QR code.",
            error="That isn't a verification code. It has 26 letters and digits, like 7KQ3-M9XD-PA2F-…",
            typed=code[:40],
        )
    return RedirectResponse(f"/v/{normalized}", status_code=303)


@router.get("/v/{code}", dependencies=[public(Realm.VERIFY)])
async def verify_code(code: str, request: Request, infra: InfraDep) -> HTMLResponse:
    try:
        await infra.limiter.hit(VERIFY_PER_IP, client_ip(request))
    except RateLimited as exc:
        return _limited(exc)
    found = await VerificationService(infra).lookup(code[:64])
    return _found(found) if found is not None else _not_found()
