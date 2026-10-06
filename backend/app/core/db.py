"""Database engines, sessions and the Unit of Work (docs/06 §2–3, docs/08 §4).

Two runtime engines:

* ``app`` — role ``scorecode_app`` (NOBYPASSRLS). Every transaction that touches tenant data first
  runs ``set_config('app.tenant_id', :tid, true)`` (transaction-local, PgBouncer-safe). Policies use
  ``current_setting('app.tenant_id')`` *without* ``missing_ok`` so a query that forgot the context
  fails closed.
* ``platform`` — role ``scorecode_platform`` (BYPASSRLS). Only the platform module may use it.

Independently of RLS, the ORM adds ``tenant_id = :ctx`` to every statement on ``TenantScoped`` models
(isolation layer L3), so a forgotten filter is caught twice.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.models import TenantScoped

log = get_logger(__name__)

AfterCommit = Callable[[], Awaitable[None]]


def _engine(url: str, settings: Settings, app_name: str, pool_size: int | None = None) -> AsyncEngine:
    return create_async_engine(
        url,
        pool_size=pool_size or settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_s,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={
            "statement_cache_size": settings.db_statement_cache_size,
            "server_settings": {"application_name": app_name},
            "timeout": 5,
        },
    )


@event.listens_for(Session, "do_orm_execute")
def _tenant_criteria(state: ORMExecuteState) -> None:
    """Isolation layer L3: scope every ORM statement on tenant models to the session's tenant."""
    if state.is_column_load or state.is_relationship_load:
        return
    if not (state.is_select or state.is_update or state.is_delete):
        return
    tenant_id = state.session.info.get("tenant_id")
    if tenant_id is None:
        return
    state.statement = state.statement.options(
        with_loader_criteria(
            TenantScoped,
            lambda cls: cls.tenant_id == tenant_id,
            include_aliases=True,
        )
    )


class Database:
    def __init__(self, settings: Settings, *, app_name: str = "scorecode") -> None:
        self.settings = settings
        self.app_engine = _engine(settings.database_url_app, settings, f"{app_name}-app")
        self.platform_engine = _engine(
            settings.database_url_platform, settings, f"{app_name}-platform", pool_size=3
        )
        self._app_sessions = async_sessionmaker(self.app_engine, expire_on_commit=False, autoflush=True)
        self._platform_sessions = async_sessionmaker(
            self.platform_engine, expire_on_commit=False, autoflush=True
        )

    async def dispose(self) -> None:
        await self.app_engine.dispose()
        await self.platform_engine.dispose()

    @asynccontextmanager
    async def uow(self, tenant_id: uuid.UUID | None = None, **meta: Any) -> AsyncIterator[UnitOfWork]:
        """One transaction on the app role. Commits on success, rolls back on any exception."""
        async with self._app_sessions() as session:
            uow = UnitOfWork(session=session, tenant_id=None, meta=dict(meta))
            try:
                if tenant_id is not None:
                    await uow.set_tenant(tenant_id)
                yield uow
                await uow.commit()
            except BaseException:
                await session.rollback()
                raise
        await uow.run_after_commit()

    @asynccontextmanager
    async def platform_uow(self, **meta: Any) -> AsyncIterator[UnitOfWork]:
        """Transaction on the BYPASSRLS platform role — for the platform module only."""
        async with self._platform_sessions() as session:
            uow = UnitOfWork(session=session, tenant_id=None, meta=dict(meta), platform=True)
            try:
                yield uow
                await uow.commit()
            except BaseException:
                await session.rollback()
                raise
        await uow.run_after_commit()


@dataclass
class UnitOfWork:
    session: AsyncSession
    tenant_id: uuid.UUID | None
    meta: dict[str, Any] = field(default_factory=dict)
    platform: bool = False
    _after_commit: list[AfterCommit] = field(default_factory=list)
    _committed: bool = False

    async def set_tenant(self, tenant_id: uuid.UUID) -> None:
        """Bind this transaction to a tenant: RLS variable + ORM criteria."""
        if self.tenant_id is not None and self.tenant_id != tenant_id:
            raise RuntimeError("Unit of work is already bound to a different tenant")
        await self.session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
        )
        self.tenant_id = tenant_id
        self.session.info["tenant_id"] = tenant_id

    def require_tenant(self) -> uuid.UUID:
        if self.tenant_id is None:
            raise RuntimeError("Tenant context required for this operation")
        return self.tenant_id

    def after_commit(self, fn: AfterCommit) -> None:
        """Register a side effect that must only happen if the transaction commits."""
        self._after_commit.append(fn)

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()
        self._committed = True
        self.session.info.pop("tenant_id", None)

    async def run_after_commit(self) -> None:
        if not self._committed:
            return
        callbacks, self._after_commit = self._after_commit, []
        for fn in callbacks:
            try:
                await fn()
            except Exception:  # side effects are best-effort (cache invalidation etc.)
                log.exception("after_commit_hook_failed")
