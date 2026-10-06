"""Cookie → session → Principal. Installed as ``app.state.authenticator`` (see ``app.core.http``)."""

from __future__ import annotations

from fastapi import Request

from app.core.container import Infra
from app.core.http import Principal
from app.core.tenant import HostInfo, Realm, TenantContext
from app.modules.identity.sessions import SessionService

MAX_TOKEN_LENGTH = 100


class CookieAuthenticator:
    def __init__(self, infra: Infra) -> None:
        self.settings = infra.settings
        self.sessions = SessionService(infra)

    async def __call__(self, request: Request) -> Principal | None:
        token = request.cookies.get(self.settings.session_cookie_name)
        if not token or len(token) > MAX_TOKEN_LENGTH:
            return None
        host: HostInfo | None = getattr(request.state, "host_info", None)
        if host is None:
            return None
        if host.realm is Realm.TENANT:
            tenant: TenantContext | None = getattr(request.state, "tenant", None)
            if tenant is None:
                return None
            # The lookup runs under this host's tenant (RLS): a cookie from another tenant is not found.
            return await self.sessions.load(tenant.tenant_id, token)
        if host.realm is Realm.PLATFORM:
            return await self.sessions.load_platform(token)
        return None
