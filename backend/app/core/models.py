"""SQLAlchemy declarative base, conventions and mixins shared by all modules (docs/07 §1).

* UUIDv7 primary keys generated in the app.
* Every tenant-owned table carries ``tenant_id`` + ``UNIQUE (tenant_id, id)`` so children can use
  composite foreign keys (cross-tenant references become impossible at the schema level).
* Constraint names follow ``ix_/uq_/fk_/ck_/pk_`` so migrations are predictable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s__%(column_0_N_name)s",
    "uq": "uq_%(table_name)s__%(column_0_N_name)s",
    "ck": "ck_%(table_name)s__%(constraint_name)s",
    "fk": "fk_%(table_name)s__%(column_0_N_name)s__%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Marks = Numeric(7, 2)
"""Exact decimal for marks (half marks are common). Never float."""


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        uuid.UUID: UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
        Decimal: Numeric(7, 2),
    }


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Versioned:
    """Optimistic locking column (docs/07 §1). Services compare and bump it explicitly."""

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class TenantScoped:
    """Marks a model as tenant-owned.

    The ORM session adds ``tenant_id = :ctx`` to every SELECT/UPDATE/DELETE on these models (L3), and
    PostgreSQL RLS enforces the same rule independently (L4). See ``app.core.db``.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    __tenant_scoped__ = True


def tenant_unique_id(table: str) -> UniqueConstraint:
    """``UNIQUE (tenant_id, id)`` — the target of composite foreign keys."""
    return UniqueConstraint("tenant_id", "id", name=f"uq_{table}__tenant_id_id")


def tenant_fk(
    column: str | list[str],
    parent: str,
    *,
    parent_column: str | list[str] = "id",
    ondelete: str = "RESTRICT",
    name: str | None = None,
) -> ForeignKeyConstraint:
    """Composite FK ``(tenant_id, column) -> parent (tenant_id, parent_column)``."""
    cols = [column] if isinstance(column, str) else column
    pcols = [parent_column] if isinstance(parent_column, str) else parent_column
    return ForeignKeyConstraint(
        ["tenant_id", *cols],
        [f"{parent}.tenant_id", *[f"{parent}.{c}" for c in pcols]],
        ondelete=ondelete,
        name=name,  # None → naming convention fk_<table>__tenant_id_<cols>__<parent>
    )
