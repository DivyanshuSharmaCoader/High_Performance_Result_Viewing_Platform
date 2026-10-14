"""Erasing an institution (migration 0021) covers every tenant table: a new one can't be forgotten."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.models_registry import metadata

MIGRATION = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0021_tenant_closure_and_erasure.py"
)


def _migration():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m0021", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_tenant_table_is_erased_or_deliberately_kept() -> None:
    m = _migration()
    tenant_tables = {name for name, t in metadata.tables.items() if "tenant_id" in t.c}
    erased, kept = set(m.ERASE_ORDER), set(m.KEPT)
    assert not erased & kept
    assert erased | kept == tenant_tables, (
        f"add to ERASE_ORDER (children first) or KEPT: {sorted(tenant_tables - erased - kept)}; "
        f"no longer tenant tables: {sorted((erased | kept) - tenant_tables)}"
    )


def test_children_are_erased_before_their_parents() -> None:
    order = list(_migration().ERASE_ORDER)
    position = {name: i for i, name in enumerate(order)}
    for name in order:
        for fk in metadata.tables[name].foreign_keys:
            parent = fk.column.table.name
            if parent in position and parent != name:
                assert position[name] < position[parent], f"{name} must be erased before {parent}"
