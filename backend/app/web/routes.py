"""Router registry: every module's HTTP surface is mounted here (and nowhere else)."""

from __future__ import annotations

from fastapi import FastAPI

from app.modules.academics.router import router as academics_router
from app.modules.audit.router import router as audit_router
from app.modules.branding.router import router as branding_router
from app.modules.identity.router import platform_router as platform_auth_router
from app.modules.identity.router import router as identity_router
from app.modules.identity.staff_router import router as staff_router
from app.modules.platform.router import router as platform_router
from app.modules.tenancy.router import router as settings_router
from app.modules.tenancy.signup_router import router as signup_router
from app.web.jobs_router import router as jobs_router


def include_routers(app: FastAPI) -> None:
    for router in (
        identity_router,
        platform_auth_router,
        branding_router,
        staff_router,
        settings_router,
        signup_router,
        audit_router,
        jobs_router,
        platform_router,
        academics_router,
    ):
        app.include_router(router)
