"""Request-scoped FastAPI dependencies shared by every module.

Authentication is injected (``app.state.authenticator``) so the kernel does not depend on the identity
module. Every route must declare an access policy — ``require(...)``, ``require_platform(...)`` or
``public()`` — and a test enumerates all routes to enforce default-deny (docs/10 §3).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol

from fastapi import Depends, Request

from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import NotAuthenticated, NotFound, PermissionDenied
from app.core.ratelimit import API_PER_SESSION, Bucket
from app.core.tenant import HostInfo, Realm, TenantContext


@dataclass(frozen=True, slots=True)
class Principal:
    kind: Literal["user", "platform"]
    user_id: uuid.UUID
    tenant_id: uuid.UUID | None
    roles: frozenset[str]
    permissions: frozenset[str]
    session_hash: bytes
    user_kind: str  # staff | student | platform
    display_name: str
    reauthenticated_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def has(self, permission: str) -> bool:
        return permission in self.permissions


class Authenticator(Protocol):
    async def __call__(self, request: Request) -> Principal | None: ...


def get_infra(request: Request) -> Infra:
    infra: Infra = request.app.state.infra
    return infra


def get_host(request: Request) -> HostInfo:
    host: HostInfo | None = getattr(request.state, "host_info", None)
    if host is None:
        raise NotFound("Unknown host")
    return host


def get_tenant(request: Request) -> TenantContext:
    tenant: TenantContext | None = getattr(request.state, "tenant", None)
    if tenant is None:
        raise NotFound("This page belongs to an institution portal")
    return tenant


def request_meta(request: Request) -> dict[str, Any]:
    return {
        "request_id": getattr(request.state, "request_id", None),
        "ip": client_ip(request),
        "user_agent": (request.headers.get("user-agent") or "")[:300],
    }


def client_ip(request: Request) -> str:
    ip: str | None = getattr(request.state, "client_ip", None)
    if ip:
        return ip
    return request.client.host if request.client else "unknown"


async def _uow(request: Request) -> AsyncIterator[UnitOfWork]:
    """One transaction per request; bound to the request's tenant when there is one.

    The principal is resolved *before* this transaction checks out a connection: authentication may
    need its own short transaction (session lookup on a cache miss), and holding two pooled connections
    per request deadlocks the pool under concurrency (tests/integration/test_connection_usage.py).
    """
    infra = get_infra(request)
    await get_principal_optional(request)
    tenant: TenantContext | None = getattr(request.state, "tenant", None)
    async with infra.db.uow(tenant.tenant_id if tenant else None, **request_meta(request)) as uow:
        request.state.uow = uow
        yield uow


async def _platform_uow(request: Request) -> AsyncIterator[UnitOfWork]:
    infra = get_infra(request)
    await get_principal_optional(request)  # same single-connection rule as _uow
    async with infra.db.platform_uow(**request_meta(request)) as uow:
        yield uow


UoW = Annotated[UnitOfWork, Depends(_uow, scope="function")]
PlatformUoW = Annotated[UnitOfWork, Depends(_platform_uow, scope="function")]
InfraDep = Annotated[Infra, Depends(get_infra)]
TenantDep = Annotated[TenantContext, Depends(get_tenant)]


async def get_principal_optional(request: Request) -> Principal | None:
    if hasattr(request.state, "principal"):
        cached: Principal | None = request.state.principal
        return cached
    authenticator: Authenticator = request.app.state.authenticator
    principal = await authenticator(request)
    request.state.principal = principal
    return principal


async def get_principal(request: Request) -> Principal:
    principal = await get_principal_optional(request)
    if principal is None:
        raise NotAuthenticated()
    return principal


# ---- Access policies (each route declares exactly one) -------------------------------------------

ACCESS_POLICY_ATTR = "__scorecode_access_policy__"


def _mark(fn: Callable[..., Awaitable[Any]], policy: str) -> Callable[..., Awaitable[Any]]:
    setattr(fn, ACCESS_POLICY_ATTR, policy)
    return fn


def require(*permissions: str) -> Any:
    """Tenant-realm route: authenticated user of *this host's* tenant holding all ``permissions``."""

    async def dependency(request: Request) -> Principal:
        if getattr(request.state, "tenant", None) is None:
            raise NotFound()
        principal = await get_principal(request)
        if principal.kind != "user":
            raise NotAuthenticated()
        missing = [p for p in permissions if not principal.has(p)]
        if missing:
            raise PermissionDenied()
        # Fairness per session (docs/10 §7): generous for humans, stops runaway scripts.
        infra = get_infra(request)
        bucket = Bucket.per_minute(
            API_PER_SESSION.name,
            infra.settings.api_session_per_minute,
            burst=infra.settings.api_session_burst,
        )
        await infra.limiter.hit(bucket, principal.session_hash.hex())
        return principal

    _mark(dependency, "tenant:" + ",".join(permissions))
    return Depends(dependency)


def require_platform(*permissions: str) -> Any:
    async def dependency(request: Request) -> Principal:
        host: HostInfo | None = getattr(request.state, "host_info", None)
        if host is None or host.realm is not Realm.PLATFORM:
            raise NotFound()
        principal = await get_principal(request)
        if principal.kind != "platform":
            raise NotAuthenticated()
        if any(not principal.has(p) for p in permissions):
            raise PermissionDenied()
        return principal

    _mark(dependency, "platform:" + ",".join(permissions))
    return Depends(dependency)


def public(*realms: Realm) -> Any:
    """Explicitly anonymous route, optionally restricted to certain realms."""

    async def dependency(request: Request) -> None:
        if realms:
            host: HostInfo | None = getattr(request.state, "host_info", None)
            if host is None or host.realm not in realms:
                raise NotFound()

    _mark(dependency, "public:" + ",".join(r.value for r in realms))
    return Depends(dependency)


PrincipalDep = Annotated[Principal, Depends(get_principal)]
