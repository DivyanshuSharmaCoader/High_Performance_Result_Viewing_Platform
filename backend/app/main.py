"""API entrypoint: application factory (composition root)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.container import Infra
from app.core.logging import configure_logging, get_logger
from app.jobs_registry import load_job_handlers
from app.models_registry import metadata as _all_models  # noqa: F401  (every table, so FKs resolve)
from app.modules.identity.authn import CookieAuthenticator
from app.modules.tenancy.service import TenantResolver
from app.web.errors import install_error_handlers
from app.web.middleware import ScoreCodeMiddleware
from app.web.routes import include_routers

log = get_logger("scorecode.app")


def _init_sentry(settings: Settings) -> None:
    if settings.sentry_dsn:

        def _scrub(event, _hint):  # type: ignore[no-untyped-def]
            request = event.get("request") or {}
            request.pop("cookies", None)
            request.pop("data", None)
            headers = request.get("headers") or {}
            for h in ("cookie", "authorization", "x-csrf-token"):
                headers.pop(h, None)
            return event

        sentry_sdk.init(
            dsn=settings.sentry_dsn.get_secret_value(),
            environment=settings.env.value,
            send_default_pii=False,
            traces_sample_rate=0.0,
            before_send=_scrub,
        )


def create_app(settings: Settings | None = None, infra: Infra | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json, settings.service_name)
    _init_sentry(settings)
    infra = infra or Infra.build(settings, app_name="scorecode-api")
    load_job_handlers()  # the API enqueues jobs, so every job kind must be known here too

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            async with infra.db.uow() as uow:
                await uow.session.execute(text("SELECT ensure_audit_partitions(3)"))
        except Exception:  # never block startup on housekeeping; readiness reports DB problems
            log.warning("audit_partition_check_failed")
        yield
        await infra.close()

    app = FastAPI(
        title="ScoreCode API",
        version="0.1.0",
        description="Multi-tenant examination and result infrastructure. The tenant is always implied by "
        "the request host; it is never a path or body parameter.",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.expose_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.expose_docs else None,
    )
    app.state.infra = infra
    app.state.authenticator = CookieAuthenticator(infra)
    app.add_middleware(ScoreCodeMiddleware, settings=settings, resolver=TenantResolver(infra))
    install_error_handlers(app)

    @app.get("/livez", include_in_schema=False)
    async def livez() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        try:
            async with asyncio.timeout(2):
                async with infra.db.uow() as uow:
                    await uow.session.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)
        return JSONResponse(
            {"status": "ok", "database": "up", "cache": "redis" if infra.cache.redis_available else "local"}
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        if not settings.metrics_enabled:
            return Response(status_code=404)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    include_routers(app)
    return app
