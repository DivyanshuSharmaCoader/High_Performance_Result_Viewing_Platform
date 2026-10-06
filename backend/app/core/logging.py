"""Structured JSON logging with request context and PII/secret scrubbing (docs/14 §Q, docs/08 §9).

Rule: no passwords, tokens, marks or names in logs. The scrubber redacts known-sensitive keys
recursively; services must still avoid logging payloads.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

SENSITIVE_KEY_PATTERN = re.compile(
    r"(pass(word)?|secret|token|authorization|cookie|session|csrf|api[_-]?key|totp|otp|"
    r"activation[_-]?code|code_hash|password_hash|marks?|components|full_name|name|dob|date_of_birth|"
    r"email|phone|guardian)",
    re.IGNORECASE,
)
SAFE_KEYS = frozenset(
    {
        "event",
        "level",
        "timestamp",
        "logger",
        "request_id",
        "tenant_id",
        "user_id",
        "route",
        "method",
        "status",
        "duration_ms",
        "job_id",
        "job_kind",
        "queue",
        "realm",
        "host",
        "path",
        "error_code",
        "exc_info",
        "exception",
        "service",
        "attempt",
        "session_kind",
        "name_of_queue",
    }
)
REDACTED = "[redacted]"
# Values that look like opaque bearer secrets even under innocuous keys.
TOKEN_VALUE_PATTERN = re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")


def _scrub(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return REDACTED
    if isinstance(value, Mapping):
        return {
            k: (REDACTED if _is_sensitive_key(str(k)) else _scrub(v, depth + 1)) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub(v, depth + 1) for v in value]
    if isinstance(value, str):
        return TOKEN_VALUE_PATTERN.sub(REDACTED, value)
    return value


def _is_sensitive_key(key: str) -> bool:
    return key not in SAFE_KEYS and bool(SENSITIVE_KEY_PATTERN.search(key))


def scrub_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict.keys()):
        if key in SAFE_KEYS:
            continue
        if _is_sensitive_key(key):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _scrub(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", json: bool = True, service: str = "scorecode") -> None:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        scrub_processor,
    ]
    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[*shared, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service)
    # Route stdlib logging (uvicorn, sqlalchemy warnings) through a plain handler at WARNING+.
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
