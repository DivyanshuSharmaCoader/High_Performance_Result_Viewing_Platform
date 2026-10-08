"""Request pipeline (docs/08 §4) as one pure-ASGI middleware:

1. request id (accepted from the proxy or generated) bound to the logger
2. client IP (the proxy's ``X-Real-IP`` only when ``trust_proxy_headers``)
3. host → realm → tenant context (L1); unknown host 404, unavailable tenant 403
4. CSRF double-submit check for state-changing API calls; CSRF cookie issued when missing
5. security headers and RED metrics on every response
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import structlog
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import CsrfFailed, DomainError, NotFound, Overloaded, TenantUnavailable
from app.core.ids import uuid7
from app.core.logging import get_logger
from app.core.metrics import DB_POOL_EXHAUSTED, HTTP_LATENCY, HTTP_REQUESTS, route_class
from app.core.security import constant_time_equals, new_token
from app.core.tenant import Realm, classify_host
from app.modules.tenancy.service import TenantResolver

log = get_logger("scorecode.http")

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
UNSCOPED_PATHS = ("/livez", "/readyz", "/metrics")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._\-]{8,64}$")

API_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"x-frame-options", b"DENY"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"cross-origin-opener-policy", b"same-origin"),
]
API_CSP = b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def _problem_body(err: DomainError, request_id: str, path: str) -> bytes:
    return json.dumps(err.to_problem(instance=path, request_id=request_id)).encode()


class ScoreCodeMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings, resolver: TenantResolver) -> None:
        self.app = app
        self.settings = settings
        self.resolver = resolver

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        incoming_id = headers.get("x-request-id", "")
        request_id = incoming_id if _REQUEST_ID_RE.match(incoming_id) else uuid7().hex
        path: str = scope["path"]
        method: str = scope["method"]
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["client_ip"] = self._client_ip(scope, headers)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_holder = {"status": 500}
        csrf_cookie = _read_cookie(headers.get("cookie", ""), self.settings.csrf_cookie_name)
        issue_csrf = path.startswith("/api/") and not csrf_cookie

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                raw = list(message.get("headers", []))
                existing = {k.lower() for k, _ in raw}
                raw.append((b"x-request-id", request_id.encode()))
                for k, v in API_SECURITY_HEADERS:
                    if k not in existing:
                        raw.append((k, v))
                if b"content-security-policy" not in existing:
                    raw.append((b"content-security-policy", API_CSP))
                if self.settings.cookie_secure:
                    raw.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                if b"cache-control" not in existing and path.startswith("/api/"):
                    raw.append((b"cache-control", b"no-store"))
                if issue_csrf:
                    raw.append((b"set-cookie", self._csrf_cookie(new_token(24)).encode()))
                message["headers"] = raw
            await send(message)

        try:
            if not path.startswith(UNSCOPED_PATHS):
                try:
                    error: DomainError | None = await self._resolve(scope, state, headers)
                except PoolTimeout:  # a host-lookup cache miss found no free connection: retryable
                    DB_POOL_EXHAUSTED.inc()
                    error = Overloaded()
                if error is None and path.startswith("/api/") and method not in SAFE_METHODS:
                    error = self._check_csrf(headers, csrf_cookie)
                if error is not None:
                    await self._send_problem(send_wrapper, error, request_id, path)
                    return
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - started
            klass = route_class(path)
            HTTP_REQUESTS.labels(klass, method, str(status_holder["status"])).inc()
            HTTP_LATENCY.labels(klass).observe(elapsed)
            if not path.startswith(UNSCOPED_PATHS):
                tenant = state.get("tenant")
                log.info(
                    "request",
                    method=method,
                    path=path,
                    status=status_holder["status"],
                    duration_ms=round(elapsed * 1000, 1),
                    tenant_id=str(tenant.tenant_id) if tenant else None,
                    realm=state["host_info"].realm.value if state.get("host_info") else None,
                )
            structlog.contextvars.unbind_contextvars("request_id")

    def _client_ip(self, scope: Scope, headers: dict[str, str]) -> str:
        # Our Caddy works out the client address (walking X-Forwarded-For from the right past its own
        # trusted proxies, e.g. a CDN) and *overwrites* X-Real-IP with it, so a client cannot choose
        # it. The right-most X-Forwarded-For entry is not the client: behind a CDN it is the CDN edge,
        # which would put every student of a city in one rate-limit bucket on result day.
        if self.settings.trust_proxy_headers:
            real = headers.get("x-real-ip", "").strip()
            if real:
                return real[:64]
        client = scope.get("client")
        return str(client[0]) if client else "unknown"

    async def _resolve(
        self, scope: Scope, state: dict[str, Any], headers: dict[str, str]
    ) -> DomainError | None:
        host_info = classify_host(headers.get("host"), self.settings)
        if host_info is None:
            return NotFound("Unknown address")
        state["host_info"] = host_info
        if host_info.realm is not Realm.TENANT:
            return None
        resolved = await self.resolver.resolve(host_info)
        if resolved is None:
            return NotFound("There's no institution portal at this address.")
        state["tenant"] = resolved.context
        state["tenant_config_version"] = resolved.config_version
        if resolved.context.status != "active":
            return TenantUnavailable(
                "This institution's results portal is temporarily unavailable. Please check back later.",
                institution=resolved.context.name,
            )
        structlog.contextvars.bind_contextvars(tenant_id=str(resolved.context.tenant_id))
        return None

    def _check_csrf(self, headers: dict[str, str], cookie: str | None) -> DomainError | None:
        header = headers.get("x-csrf-token", "")
        if not cookie or not header or not constant_time_equals(cookie, header):
            return CsrfFailed()
        return None

    def _csrf_cookie(self, value: str) -> str:
        parts = [f"{self.settings.csrf_cookie_name}={value}", "Path=/", "SameSite=Lax", "Max-Age=31536000"]
        if self.settings.cookie_secure:
            parts.append("Secure")
        return "; ".join(parts)

    async def _send_problem(self, send: Any, err: DomainError, request_id: str, path: str) -> None:
        body = _problem_body(err, request_id, path)
        headers = [
            (b"content-type", b"application/problem+json"),
            (b"content-length", str(len(body)).encode()),
        ]
        retry_after = getattr(err, "retry_after_s", None)
        if retry_after:
            headers.append((b"retry-after", str(retry_after).encode()))
        await send({"type": "http.response.start", "status": err.status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def _read_cookie(header: str, name: str) -> str | None:
    for part in header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name and value:
            return value
    return None
