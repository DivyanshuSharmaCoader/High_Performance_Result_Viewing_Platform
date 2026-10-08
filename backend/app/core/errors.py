"""Typed domain errors mapped centrally to RFC 9457 ``application/problem+json`` (docs/08 §9).

Services raise these; the HTTP layer never builds ad-hoc error bodies. Unexpected exceptions become a
generic 500 with the request id and no internals.
"""

from __future__ import annotations

from typing import Any

PROBLEM_BASE = "https://scorecode.dev/problems/"


class DomainError(Exception):
    status: int = 400
    code: str = "bad-request"
    title: str = "Bad request"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.extra = extra

    def to_problem(self, instance: str | None = None, request_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": PROBLEM_BASE + self.code,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "code": self.code,
        }
        if instance:
            body["instance"] = instance
        if request_id:
            body["request_id"] = request_id
        body.update(self.extra)
        return body


class ValidationFailed(DomainError):
    status = 422
    code = "validation-failed"
    title = "Some fields need attention"


class NotAuthenticated(DomainError):
    status = 401
    code = "not-authenticated"
    title = "Please sign in"


class InvalidCredentials(DomainError):
    status = 401
    code = "invalid-credentials"
    title = "Incorrect login details"


class ReauthRequired(DomainError):
    status = 401
    code = "reauth-required"
    title = "Please confirm your password to continue"


class PermissionDenied(DomainError):
    status = 403
    code = "permission-denied"
    title = "You don't have permission to do this"


class CsrfFailed(DomainError):
    status = 403
    code = "csrf-failed"
    title = "Your session token is missing or out of date. Refresh the page and try again."


class TenantUnavailable(DomainError):
    status = 403
    code = "tenant-unavailable"
    title = "This institution's portal is temporarily unavailable"


class FeatureNotInPlan(DomainError):
    status = 402
    code = "feature-not-in-plan"
    title = "This feature isn't included in your plan"


class LimitExceeded(DomainError):
    status = 402
    code = "limit-exceeded"
    title = "Plan limit reached"


class NotFound(DomainError):
    status = 404
    code = "not-found"
    title = "Not found"


class Conflict(DomainError):
    status = 409
    code = "conflict"
    title = "This was changed by someone else"


class InvalidState(DomainError):
    status = 409
    code = "invalid-state"
    title = "This action isn't allowed right now"


class IdempotencyMismatch(DomainError):
    status = 422
    code = "idempotency-key-reused"
    title = "Idempotency-Key was already used with a different request"


class PayloadTooLarge(DomainError):
    status = 413
    code = "payload-too-large"
    title = "File is too large"


class UnsupportedMedia(DomainError):
    status = 415
    code = "unsupported-media-type"
    title = "Unsupported file type"


class RateLimited(DomainError):
    status = 429
    code = "rate-limited"
    title = "Too many requests"

    def __init__(self, retry_after_s: int, detail: str | None = None) -> None:
        super().__init__(detail or "Too many requests. Please wait a moment and try again.")
        self.retry_after_s = max(1, int(retry_after_s))
        self.extra["retry_after"] = self.retry_after_s


class ServiceUnavailable(DomainError):
    status = 503
    code = "service-unavailable"
    title = "Service temporarily unavailable"


class Overloaded(ServiceUnavailable):
    """The process is saturated (e.g. every pooled database connection stayed busy). Retryable."""

    code = "overloaded"
    title = "Busy right now"

    def __init__(self, retry_after_s: int = 2) -> None:
        super().__init__("We're handling a lot of requests right now. Please try again in a moment.")
        self.retry_after_s = retry_after_s
        self.extra["retry_after"] = retry_after_s
