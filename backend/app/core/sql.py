"""Set-membership predicates that hold up at import scale.

``col IN (:p1, ..., :pN)`` binds one parameter per value, and asyncpg refuses a statement with more than
32,767. A row-value list ``(a, b) IN ((..), ..)`` is worse: Postgres rewrites it into nested ORs and runs out
of stack at around ten thousand rows (found by scripts/measure_import.py). These predicates bind one array
per column instead, so a 50,000-row file is one statement with one parameter per column.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import ARRAY, ColumnElement, any_, bindparam, func, select, tuple_


def in_values(column: Any, values: Iterable[Any]) -> ColumnElement[bool]:
    """``column = ANY(:array)``."""
    return column == any_(bindparam(None, list(values), type_=ARRAY(column.type)))  # type: ignore[no-any-return]


def in_rows(columns: Sequence[Any], rows: Iterable[Sequence[Any]]) -> ColumnElement[bool]:
    """``(c1, c2, ...) IN (SELECT * FROM unnest(:a1, :a2, ...))``."""
    rows = list(rows)
    arrays = [
        bindparam(None, [row[i] for row in rows], type_=ARRAY(col.type)) for i, col in enumerate(columns)
    ]
    table = func.unnest(*arrays).table_valued(*(f"c{i}" for i in range(len(columns)))).render_derived()
    return tuple_(*columns).in_(select(*table.c))
