"""What happens to computed results when a mark changes (FR-10.3, state diagram §1).

Called by every mark writer (the grid and the import commit) in the same transaction as the write. It
imports nothing from those modules, so marks can depend on results without a cycle.
"""

from __future__ import annotations

from sqlalchemy import update

from app.core.db import UnitOfWork
from app.modules.audit.service import Actor, record
from app.modules.examinations.models import Examination
from app.modules.examinations.states import ExamAction, ExamStatus, transition_for
from app.modules.results.models import ResultRun


async def marks_changed(uow: UnitOfWork, actor: Actor, exam: Examination) -> None:
    """Processed results no longer match the marks: mark them stale and move the exam back to
    "marks entry closed", so it has to be processed again before anyone can approve it."""
    if exam.status != ExamStatus.PROCESSED:
        return
    await uow.session.execute(
        update(ResultRun)
        .where(ResultRun.exam_id == exam.id, ResultRun.status == "completed")
        .values(status="stale")
    )
    t = transition_for(exam.status, ExamAction.MARK_STALE, None)
    exam.status = t.target.value
    exam.version += 1
    await uow.flush()
    await record(
        uow,
        actor,
        "results.stale",
        entity_type="exam",
        entity_id=exam.id,
        summary=f"Results for {exam.name} are out of date: marks changed after processing",
        before={"status": t.source.value},
        after={"status": t.target.value},
    )
