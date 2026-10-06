"""Onboarding step owned by the academics module (registered into the tenancy checklist)."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.db import UnitOfWork
from app.modules.academics.models import AcademicSession, Cohort, Course, Program
from app.modules.tenancy.onboarding import Step, StepResult, register_step


async def _structure(uow: UnitOfWork) -> StepResult:
    missing = []
    for label, model in (
        ("a session", AcademicSession),
        ("a program", Program),
        ("a cohort", Cohort),
        ("courses", Course),
    ):
        n = (
            await uow.session.execute(
                select(func.count()).select_from(model).where(model.archived_at.is_(None))
            )
        ).scalar_one()
        if n == 0:
            missing.append(label)
    if not missing:
        return StepResult(True)
    return StepResult(False, "Still to add: " + ", ".join(missing) + ".")


register_step(
    Step(
        "structure",
        "Set up your academic structure",
        "Sessions and terms, programs, cohorts (sections or batches) and courses.",
        "/admin/academics",
        True,
        40,
        _structure,
    )
)
