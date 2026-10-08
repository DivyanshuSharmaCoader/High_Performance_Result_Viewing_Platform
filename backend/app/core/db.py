"""Database engines, sessions and the Unit of Work (docs/06 §2–3, docs/08 §4).

Two runtime engines:

* ``app`` — role ``scorecode_app`` (NOBYPASSRLS). Every transaction of a unit of work bound to a tenant
  starts with ``set_config('app.tenant_id', :tid, true)`` (transaction-local, PgBouncer-safe). Policies
  use ``current_setting('app.tenant_id')`` *without* ``missing_ok`` so a query that forgot the context
  fails closed. The transaction, and with it ``set_config``, starts at the first statement, so a request
  answered entirely from cache never checks out a connection (P14.3).
* ``platform`` — role ``scorecode_platform`` (BYPASSRLS). Only the platform module may use it.

Independently of RLS, the ORM adds ``tenant_id = :ctx`` to every statement on ``TenantScoped`` models
(isolation layer L3), so a forgotten filter is caught twice.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Connection, event, text
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import ORMExecuteState, Session, SessionTransaction, with_loader_criteria

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.models import TenantScoped

log = get_logger(__name__)

AfterCommit = Callable[[], Awaitable[None]]
_SET_TENANT = text("SELECT set_config('app.tenant_id', :tid, true)")


def _engine(url: str, settings: Settings, app_name: str, pool_size: int | None = None) -> AsyncEngine:
    engine = create_async_engine(
        url,
        pool_size=pool_size or settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_s,
        pool_recycle=1800,
        connect_args={
            "statement_cache_size": settings.db_statement_cache_size,
            "server_settings": {"application_name": app_name},
            "timeout": 5,
        },
    )
    _ping_if_idle(engine, settings.db_ping_after_idle_s)
    return engine


def _ping_if_idle(engine: AsyncEngine, idle_s: float) -> None:
    """Check a pooled connection before use only if it has sat idle (P14.3).

    SQLAlchemy's ``pool_pre_ping`` pings on every checkout, and with asyncpg a ping is three round trips
    (BEGIN, ``;``, ROLLBACK): under scenario B that was half the statements Postgres ran and 2.6% of API
    CPU. A connection returned moments ago was alive moments ago, so only one idle for longer than
    ``idle_s`` (when a restart or an idle timeout could have closed it unseen) is pinged. A dead one is
    replaced before the request uses it. One that dies mid-burst fails its request with a retryable 503,
    and SQLAlchemy then invalidates the rest of the pool (test_outages.py).
    """

    @event.listens_for(engine.sync_engine, "checkin")
    def _returned(dbapi_connection: Any, record: Any) -> None:
        record.info["returned_at"] = time.monotonic()

    @event.listens_for(engine.sync_engine, "checkout")
    def _check(dbapi_connection: Any, record: Any, proxy: Any) -> None:
        returned = record.info.get("returned_at")
        if returned is None or time.monotonic() - returned < idle_s:
            return  # new, or busy: no round trips
        try:
            dbapi_connection.ping()
        except Exception as exc:
            raise DisconnectionError("pooled connection was closed while idle") from exc  # pool retries


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


@event.listens_for(Session, "after_begin")
def _bind_tenant(session: Session, transaction: SessionTransaction, connection: Connection) -> None:
    """Isolation layer L2: the RLS variable, set as the transaction's first statement."""
    tenant_id = session.info.get("tenant_id")
    if tenant_id is not None and not transaction.nested:
        connection.execute(_SET_TENANT, {"tid": str(tenant_id)})


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
        """Bind this unit of work to a tenant: RLS variable + ORM criteria.

        Before the transaction has begun, ``_bind_tenant`` sets the variable when it does; once it has
        (e.g. sign-up looked up the slug first), it is set here and now."""
        if self.tenant_id is not None and self.tenant_id != tenant_id:
            raise RuntimeError("Unit of work is already bound to a different tenant")
        self.tenant_id = tenant_id
        self.session.info["tenant_id"] = tenant_id
        if self.session.in_transaction():
            await self.session.execute(_SET_TENANT, {"tid": str(tenant_id)})

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


def is_connectivity_error(exc: BaseException) -> bool:
    """True when ``exc`` means "the database can't be reached", not "this query is wrong".

    Covers SQLAlchemy's operational/interface errors, driver errors that invalidated the connection, asyncpg's
    connection errors, and OS-level errors (refused, reset, DNS) raised while the pool was connecting. An
    OSError from anywhere else (object storage, say) is *not* one of these.
    """
    import traceback

    import asyncpg
    from sqlalchemy import exc as sa_exc

    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, sa_exc.OperationalError | sa_exc.InterfaceError):
            return True
        if isinstance(current, sa_exc.DBAPIError) and current.connection_invalidated:
            return True
        if isinstance(current, asyncpg.PostgresConnectionError | asyncpg.CannotConnectNowError):
            return True
        if isinstance(current, asyncpg.InterfaceError) and "connection" in str(current).lower():
            return True
        if isinstance(current, OSError):
            frames = traceback.extract_tb(current.__traceback__)
            if any("asyncpg" in f.filename or "sqlalchemy" in f.filename for f in frames):
                return True
        current = current.__cause__ or current.__context__
    return False
