"""Router registry: every module's HTTP surface is mounted here (and nowhere else)."""

from __future__ import annotations

from fastapi import FastAPI

from app.modules.branding.router import router as branding_router
from app.modules.identity.router import platform_router as platform_auth_router
from app.modules.identity.router import router as identity_router


def include_routers(app: FastAPI) -> None:
    for router in (identity_router, platform_auth_router, branding_router):
        app.include_router(router)
