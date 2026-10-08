"""Outages answered as outages (P14.5, docs/15 §6): when the database can't be reached, clients get a quick,
retryable 503 problem response, not a 500 or a hang, both in routes and in the tenant lookup that runs
before them.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql.asyncpg import AsyncAdapt_asyncpg_connection
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.container import Infra
from app.core.db import is_connectivity_error
from app.main import create_app
from tests.conftest import PG_HOST, PG_PORT, TEST_DB, make_settings
from tests.helpers import Client

pytestmark = pytest.mark.integration

DEAD = "postgresql+asyncpg://scorecode_app:x@127.0.0.1:1/scorecode"


async def test_an_unreachable_database_answers_503_quickly_everywhere(migrated_db: str) -> None:
    settings = make_settings(
        database_url_app=DEAD, database_url_platform=DEAD, redis_url=None, db_pool_timeout_s=1.0
    )
    infra = Infra.build(settings, app_name="scorecode-test-dead-db")
    try:
        app = create_app(settings, infra)
        for host, path in (
            ("localhost", "/api/v1/plans"),  # a route's own unit of work
            ("thapar.localhost", "/api/v1/tenant/config"),  # the tenant lookup in the middleware
        ):
            async with Client(app, host) as c:
                started = time.perf_counter()
                r = await c.get(path)
                elapsed = time.perf_counter() - started
            assert r.status_code == 503, (host, r.status_code, r.text)
            assert r.headers["retry-after"] == "5"
            assert r.json()["code"] == "service-unavailable" and r.json()["retry_after"] == 5
            assert elapsed < 5, elapsed  # refused connections fail fast; nothing hangs
    finally:
        await infra.close()


def test_only_connectivity_failures_count_as_outages() -> None:
    assert is_connectivity_error(OperationalError("SELECT 1", {}, ConnectionRefusedError()))
    assert not is_connectivity_error(IntegrityError("INSERT", {}, Exception("duplicate key")))
    try:
        raise ConnectionResetError("object storage hung up")  # an OSError, but not from the database
    except OSError as exc:
        assert not is_connectivity_error(exc)
    assert not is_connectivity_error(ValueError("nope"))


# ---- connections that die in the pool (P14.3: ping only after idling) ------------------------------------


@contextmanager
def counted_pings() -> Iterator[list[int]]:
    calls: list[int] = []
    original = AsyncAdapt_asyncpg_connection.ping

    def ping(self: AsyncAdapt_asyncpg_connection) -> None:
        calls.append(1)
        original(self)

    AsyncAdapt_asyncpg_connection.ping = ping  # type: ignore[method-assign]
    try:
        yield calls
    finally:
        AsyncAdapt_asyncpg_connection.ping = original  # type: ignore[method-assign]


async def _backend_pid(infra: Infra) -> int:
    async with infra.db.uow() as uow:
        return int((await uow.session.execute(text("SELECT pg_backend_pid()"))).scalar_one())


async def _terminate(pid: int) -> None:
    """As the app role, which may end its own sessions: what a restart or an idle timeout does."""
    conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user="scorecode_app", password="app-dev-pw", database=TEST_DB
    )
    try:
        assert await conn.fetchval("SELECT pg_terminate_backend($1)", pid)
    finally:
        await conn.close()


def _one_connection(**overrides: object) -> Infra:
    settings = make_settings(db_pool_size=1, db_max_overflow=0, redis_url=None, **overrides)
    return Infra.build(settings, app_name="scorecode-test-dead-connection")


async def test_a_busy_pool_sends_no_pings_and_an_idle_connection_gets_one(migrated_db: str) -> None:
    infra = _one_connection(db_ping_after_idle_s=0.2)
    try:
        with counted_pings() as pings:
            for _ in range(5):
                await _backend_pid(infra)  # returned and taken again at once
            assert pings == []
            await asyncio.sleep(0.3)
            await _backend_pid(infra)
            assert len(pings) == 1
    finally:
        await infra.close()


async def test_a_connection_closed_while_idle_is_replaced_before_use(migrated_db: str) -> None:
    infra = _one_connection(db_ping_after_idle_s=0.05)
    try:
        pid = await _backend_pid(infra)
        await _terminate(pid)
        await asyncio.sleep(0.1)
        assert await _backend_pid(infra) != pid  # no error: the ping found it dead first
    finally:
        await infra.close()


async def test_a_connection_closed_mid_burst_fails_one_request_retryably_then_recovers(
    migrated_db: str,
) -> None:
    """Not pinged (it was just used), so its request fails, as a connectivity error: a 503 with Retry-After
    (test_an_unreachable_database_answers_503_quickly_everywhere). The next request gets a new connection."""
    infra = _one_connection(db_ping_after_idle_s=3600)
    try:
        pid = await _backend_pid(infra)
        await _terminate(pid)
        with pytest.raises(Exception) as failed:
            await _backend_pid(infra)
        assert is_connectivity_error(failed.value), repr(failed.value)
        assert await _backend_pid(infra) != pid
    finally:
        await infra.close()
