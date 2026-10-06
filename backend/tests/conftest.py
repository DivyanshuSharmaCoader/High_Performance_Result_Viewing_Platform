"""Test harness.

Integration tests run against real services (docs/15 §3): a fresh PostgreSQL database per test run
(migrated with Alembic as the migrator role, then used through the *runtime* roles), Redis, S3-compatible
storage and Mailpit — all from ``compose.yml``. Unit tests need none of them.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
import pytest_asyncio

from app.core.config import Environment, Settings

PG_HOST = os.environ.get("SCORECODE_TEST_PG_HOST", "localhost")
PG_PORT = int(os.environ.get("SCORECODE_TEST_PG_PORT", "55432"))
TEST_DB = os.environ.get("SCORECODE_TEST_DB", f"scorecode_test_{os.getpid()}")
REDIS_URL = os.environ.get("SCORECODE_TEST_REDIS_URL", "redis://localhost:56379/15")
S3_URL = os.environ.get("SCORECODE_TEST_S3_URL", "http://localhost:59000")
SMTP_PORT = int(os.environ.get("SCORECODE_TEST_SMTP_PORT", "51025"))
MAILPIT_API = os.environ.get("SCORECODE_TEST_MAILPIT_API", "http://localhost:58025")


def _url(role: str, password: str, db: str = TEST_DB) -> str:
    return f"postgresql+asyncpg://{role}:{password}@{PG_HOST}:{PG_PORT}/{db}"


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "env": Environment.TEST,
        "log_json": False,
        "log_level": "WARNING",
        "base_domain": "localhost",
        "public_port": 8080,
        "database_url_app": _url("scorecode_app", "app-dev-pw"),
        "database_url_platform": _url("scorecode_platform", "platform-dev-pw"),
        "database_url_migrator": _url("scorecode_migrator", "migrator-dev-pw"),
        "db_pool_size": 5,
        "redis_url": REDIS_URL,
        "s3_endpoint_url": S3_URL,
        "s3_bucket": "scorecode-test",
        "smtp_port": SMTP_PORT,
        "argon2_time_cost": 1,
        "argon2_memory_kib": 1024,
        "argon2_max_concurrency": 8,
        "metrics_enabled": True,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


async def _recreate_database() -> None:
    conn = await asyncpg.connect(
        host=PG_HOST,
        port=PG_PORT,
        user="scorecode_migrator",
        password="migrator-dev-pw",
        database="scorecode",
    )
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await conn.close()


async def _drop_database() -> None:
    conn = await asyncpg.connect(
        host=PG_HOST,
        port=PG_PORT,
        user="scorecode_migrator",
        password="migrator-dev-pw",
        database="scorecode",
    )
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
    finally:
        await conn.close()


def _services_available() -> bool:
    async def probe() -> bool:
        try:
            c = await asyncpg.connect(
                host=PG_HOST,
                port=PG_PORT,
                user="scorecode_migrator",
                password="migrator-dev-pw",
                database="scorecode",
                timeout=2,
            )
            await c.close()
            return True
        except Exception:
            return False

    return asyncio.run(probe())


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[str]:
    if not _services_available():
        pytest.skip("PostgreSQL from compose.yml is not running (make up)")
    asyncio.run(_recreate_database())
    from alembic import command
    from alembic.config import Config

    os.environ["SCORECODE_MIGRATION_URL"] = _url("scorecode_migrator", "migrator-dev-pw")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "migrations"))
    command.upgrade(cfg, "head")
    yield TEST_DB
    if not os.environ.get("SCORECODE_KEEP_TEST_DB"):
        asyncio.run(_drop_database())


@pytest.fixture(scope="session")
def settings(migrated_db: str) -> Settings:
    return make_settings()


@pytest_asyncio.fixture(scope="session")
async def infra(settings: Settings) -> AsyncIterator[object]:
    from app.core.container import Infra
    from app.core.storage import S3ObjectStore
    from app.jobs_registry import load_job_handlers
    from app.modules.entitlements.sync import sync_catalogue

    load_job_handlers()
    infra = Infra.build(settings, app_name="scorecode-test")
    await sync_catalogue(infra.db)
    assert isinstance(infra.storage, S3ObjectStore)
    await infra.storage.ensure_bucket()
    if infra.cache.redis is not None:
        await infra.cache.redis.flushdb()
    yield infra
    await infra.close()


@pytest_asyncio.fixture(scope="session")
async def app(infra: object) -> object:
    from app.main import create_app

    return create_app(infra.settings, infra)  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _reset_rate_limits(request: pytest.FixtureRequest) -> Iterator[None]:
    """Rate-limit state must not leak between tests (each test uses unique tenants/IPs anyway)."""
    yield
    if "infra" in request.fixturenames:
        infra = request.getfixturevalue("infra")
        infra.limiter.reset_local()  # type: ignore[attr-defined]


def unique_slug(prefix: str = "t") -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"
