"""Alembic environment. Migrations always run as ``scorecode_migrator`` (schema owner), never as the
runtime app role (docs/06 §2)."""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.models_registry import metadata

config = context.config
target_metadata = metadata


def _url() -> str:
    return os.environ.get("SCORECODE_MIGRATION_URL") or get_settings().database_url_migrator


# Indexes written by hand in migrations (expression indexes with operator classes), invisible to models.
HAND_MANAGED_INDEXES = {"ix_students__name_trgm"}


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    # Monthly audit partitions are managed by migrations/maintenance, not by autogenerate.
    if type_ == "table" and name and name.startswith("audit_logs_p"):
        return False
    return not (type_ == "index" and name in HAND_MANAGED_INDEXES)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(), target_metadata=target_metadata, literal_binds=True, include_object=include_object
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
