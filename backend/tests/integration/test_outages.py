"""Outages answered as outages (P14.5, docs/15 §6): when the database can't be reached, clients get a quick,
retryable 503 problem response, not a 500 or a hang, both in routes and in the tenant lookup that runs
before them.
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.container import Infra
from app.core.db import is_connectivity_error
from app.main import create_app
from tests.conftest import make_settings
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
