"""Migrations apply from empty, downgrade to base and re-apply cleanly (P2.3, docs/14 §P)."""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import pytest
from alembic import command
from alembic.config import Config

from tests.conftest import PG_HOST, PG_PORT

pytestmark = pytest.mark.integration


def _cfg(url: str) -> Config:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "migrations"))
    os.environ["SCORECODE_MIGRATION_URL"] = url
    return cfg


async def _admin(sql: str) -> None:
    conn = await asyncpg.connect(
        host=PG_HOST,
        port=PG_PORT,
        user="scorecode_migrator",
        password="migrator-dev-pw",
        database="scorecode",
    )
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _tables(db: str) -> set[str]:
    conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user="scorecode_migrator", password="migrator-dev-pw", database=db
    )
    try:
        rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    finally:
        await conn.close()
    return {r["tablename"] for r in rows}


def test_upgrade_downgrade_upgrade_roundtrip(migrated_db: str) -> None:
    db = f"scorecode_migr_{uuid.uuid4().hex[:8]}"
    previous = os.environ.get("SCORECODE_MIGRATION_URL")
    asyncio.run(_admin(f'CREATE DATABASE "{db}"'))
    try:
        cfg = _cfg(f"postgresql+asyncpg://scorecode_migrator:migrator-dev-pw@{PG_HOST}:{PG_PORT}/{db}")
        command.upgrade(cfg, "head")
        head_tables = asyncio.run(_tables(db))
        assert {"tenants", "users", "audit_logs", "jobs"} <= head_tables
        command.downgrade(cfg, "base")
        assert asyncio.run(_tables(db)) <= {"alembic_version"}
        command.upgrade(cfg, "head")
        assert asyncio.run(_tables(db)) == head_tables
    finally:
        if previous is not None:
            os.environ["SCORECODE_MIGRATION_URL"] = previous
        asyncio.run(_admin(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
