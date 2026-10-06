"""Central mapping of exceptions to RFC 9457 problem responses (docs/08 §9)."""

from __future__ import annotations

from typing import Any

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import PROBLEM_BASE, DomainError, RateLimited
from app.core.logging import get_logger

log = get_logger("scorecode.errors")
PROBLEM_JSON = "application/problem+json"


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _field_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    out = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        msg = str(err.get("msg", "Invalid value"))
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        if err.get("type") == "extra_forbidden":
            msg = "Unexpected field"
        out.append({"field": ".".join(loc) or None, "message": msg, "type": err.get("type")})
    return out


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimited):
            headers["Retry-After"] = str(exc.retry_after_s)
        if exc.status >= 500:
            log.warning("domain_error", error_code=exc.code, status=exc.status)
        return JSONResponse(
            exc.to_problem(instance=request.url.path, request_id=_request_id(request)),
            status_code=exc.status,
            media_type=PROBLEM_JSON,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = _field_errors(exc)
        detail = errors[0]["message"] if len(errors) == 1 else "Some fields need attention."
        return JSONResponse(
            {
                "type": PROBLEM_BASE + "validation-failed",
                "title": "Some fields need attention",
                "status": 422,
                "detail": detail,
                "code": "validation-failed",
                "errors": errors,
                "instance": request.url.path,
                "request_id": _request_id(request),
            },
            status_code=422,
            media_type=PROBLEM_JSON,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not-found", 405: "method-not-allowed"}.get(exc.status_code, "http-error")
        return JSONResponse(
            {
                "type": PROBLEM_BASE + code,
                "title": str(exc.detail) if exc.status_code != 404 else "Not found",
                "status": exc.status_code,
                "detail": str(exc.detail),
                "code": code,
                "instance": request.url.path,
                "request_id": _request_id(request),
            },
            status_code=exc.status_code,
            media_type=PROBLEM_JSON,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", error_code=type(exc).__name__)
        sentry_sdk.capture_exception(exc)
        return JSONResponse(
            {
                "type": PROBLEM_BASE + "internal-error",
                "title": "Something went wrong on our side",
                "status": 500,
                "detail": "An unexpected error occurred. It has been logged; please try again.",
                "code": "internal-error",
                "request_id": _request_id(request),
            },
            status_code=500,
            media_type=PROBLEM_JSON,
        )
