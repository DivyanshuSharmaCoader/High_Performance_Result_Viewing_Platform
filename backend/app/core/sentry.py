"""Error reports to Sentry, with nothing personal in them (P18.6, docs/10 §11).

Errors only: no performance traces, no profiles, no local variables, no source lines, no request bodies,
no cookies, no query strings, no user. Every event and breadcrumb passes through ``scrub_event`` / ``scrub_breadcrumb``,
which keep the shape of a stack trace (file, function, line) and remove what could identify a person or
open a door: email addresses, phone numbers, ids, long numbers (enrollment and roll numbers), marks and
other decimals, tokens and secrets. Headers are an allow-list. If the scrubber itself fails, the event is
dropped rather than sent unscrubbed.

Configured only from settings (``SCORECODE_SENTRY_DSN``; unset = off). ``scorecode sentry-test`` sends one
synthetic error to prove the path end to end (docs/runbooks/security-incident.md: disable or rotate).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import sentry_sdk

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "[id]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+"), r"\1 [secret]"),
    (
        re.compile(r"(?i)\b(password|passwd|secret|token|key|code|otp|dsn|session|csrf)(\s*[=:]\s*)\S+"),
        r"\1\2[secret]",
    ),
    (re.compile(r"(?:(?<=\D)|^)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?=\D|$)"), "[phone]"),
    (re.compile(r"\b[A-Za-z0-9_-]{24,}\b"), "[token]"),  # long opaque strings: tokens, keys, codes
    (re.compile(r"\b\d+\.\d+\b"), "[n]"),  # marks, percentages, amounts
    (re.compile(r"\b\d{5,}\b"), "[number]"),  # enrollment and roll numbers, phone fragments
)
SAFE_HEADERS = frozenset({"content-type", "content-length", "accept", "user-agent", "x-request-id"})
SAFE_TAGS = frozenset({"component", "environment", "release", "job_kind", "queue", "handled", "level"})


def scrub_text(value: str) -> str:
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _scrub(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "[deep]"
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, Mapping):
        return {k: _scrub(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v, depth + 1) for v in value]
    return value


def _url(url: str) -> str:
    """Path only (no query string, no fragment), with ids and long numbers replaced."""
    return scrub_text(url.split("?", 1)[0].split("#", 1)[0])


def _bare(frame: dict[str, Any]) -> None:
    """File, function and line only: no local variables, no source lines (both are off in the SDK too;
    never trust one switch)."""
    for key in ("vars", "pre_context", "context_line", "post_context"):
        frame.pop(key, None)


def scrub_event(event: Any, _hint: Any = None) -> Any:
    try:
        event.pop("user", None)
        event.pop("extra", None)
        if "breadcrumbs" in event and not isinstance(event["breadcrumbs"], Mapping):
            event.pop("breadcrumbs")
        request = event.get("request")
        if isinstance(request, dict):
            for key in ("cookies", "data", "query_string", "env"):
                request.pop(key, None)
            if "url" in request:
                request["url"] = _url(str(request["url"]))
            headers = request.get("headers") or {}
            request["headers"] = {k: _scrub(v) for k, v in headers.items() if str(k).lower() in SAFE_HEADERS}
        if "tags" in event and isinstance(event["tags"], Mapping):
            event["tags"] = {k: v for k, v in event["tags"].items() if k in SAFE_TAGS}
        if "message" in event and isinstance(event["message"], str):
            event["message"] = scrub_text(event["message"])
        if isinstance(event.get("logentry"), dict):
            entry = event["logentry"]
            entry["message"] = scrub_text(str(entry.get("message", "")))
            entry.pop("params", None)
            if "formatted" in entry:
                entry["formatted"] = scrub_text(str(entry["formatted"]))
        for exc in (event.get("exception") or {}).get("values", []) or []:
            if "value" in exc and exc["value"] is not None:
                exc["value"] = scrub_text(str(exc["value"]))
            for frame in (exc.get("stacktrace") or {}).get("frames", []) or []:
                _bare(frame)
        for thread in (event.get("threads") or {}).get("values", []) or []:
            for frame in (thread.get("stacktrace") or {}).get("frames", []) or []:
                _bare(frame)
        crumbs = event.get("breadcrumbs")
        if isinstance(crumbs, Mapping):
            event["breadcrumbs"] = {
                "values": [c for c in (scrub_breadcrumb(dict(b)) for b in crumbs.get("values", [])) if c]
            }
        return event
    except Exception:  # never let a scrubbing bug send raw data
        log.warning("sentry_scrub_failed_event_dropped")
        return None


def scrub_breadcrumb(crumb: Any, _hint: Any = None) -> Any:
    try:
        if "message" in crumb and crumb["message"] is not None:
            crumb["message"] = scrub_text(str(crumb["message"]))
        data = crumb.get("data")
        if isinstance(data, Mapping):
            kept: dict[str, Any] = {}
            for k in ("method", "status_code", "reason", "level"):
                if k in data:
                    kept[k] = data[k]
            if "url" in data:
                kept["url"] = _url(str(data["url"]))
            crumb["data"] = kept
        return crumb
    except Exception:
        return None


def init_sentry(settings: Settings, component: str) -> bool:
    """Starts error reporting when a DSN is configured. Returns whether it did."""
    if settings.sentry_dsn is None:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.env.value,
        release=settings.release,
        send_default_pii=False,
        include_local_variables=False,
        include_source_context=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        max_breadcrumbs=30,
        before_send=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
    )
    sentry_sdk.set_tag("component", component)
    return True
