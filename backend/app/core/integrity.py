"""Translate database constraint violations into friendly domain errors.

The database is the final authority on uniqueness and references (docs/07 §4); services flush inside a
savepoint and map known constraint names to messages that say *which field* to fix.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.core.db import UnitOfWork
from app.core.errors import Conflict, InvalidState


@dataclass(frozen=True)
class ConstraintMessage:
    message: str
    field: str | None = None
    in_use: bool = False  # FK RESTRICT violations: the row is referenced elsewhere


def _constraint_name(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    for attr in ("constraint_name",):
        value = getattr(orig, attr, None) or getattr(getattr(orig, "__cause__", None), attr, None)
        if value:
            return str(value)
    text = str(orig)
    for token in text.replace('"', " ").split():
        if token.startswith(("uq_", "fk_", "ck_", "pk_")):
            return token
    return None


async def flush_checked(uow: UnitOfWork, messages: dict[str, ConstraintMessage]) -> None:
    """Flush pending changes in a savepoint; known constraint violations become 409s with guidance."""
    try:
        async with uow.session.begin_nested():
            await uow.session.flush()
    except IntegrityError as exc:
        name = _constraint_name(exc)
        if name and name in messages:
            m = messages[name]
            if m.in_use:
                raise InvalidState(m.message) from exc
            raise Conflict(m.message, field=m.field) from exc
        raise
