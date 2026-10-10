"""Which students a new version of an exam's results changes (P18.3).

Shared by publishing (the audit record of a correction) and notifications (only those students are told),
so neither imports the other. A change is in what the student sees of their own result: the result and the
papers' marks, compared as JSON values, not the institution's name or the student's details.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.db import UnitOfWork
from app.modules.publishing.models import PublishedResult


async def changed_students(
    uow: UnitOfWork, publication_id: uuid.UUID, previous_id: uuid.UUID
) -> list[uuid.UUID]:
    """Students whose result or marks differ between two publications, or who are new in the first."""
    table = PublishedResult.__table__
    new, old = table.alias("new"), table.alias("old")
    rows = await uow.session.execute(
        select(new.c.student_id)
        .select_from(
            new.outerjoin(old, (old.c.publication_id == previous_id) & (old.c.student_id == new.c.student_id))
        )
        .where(
            new.c.publication_id == publication_id,
            (old.c.student_id.is_(None))
            | new.c.payload["result"].is_distinct_from(old.c.payload["result"])
            | new.c.payload["papers"].is_distinct_from(old.c.payload["papers"]),
        )
    )
    return [r[0] for r in rows.all()]
