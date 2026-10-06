"""Onboarding step owned by the directory module (registered into the tenancy checklist)."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.db import UnitOfWork
from app.modules.directory.models import Student
from app.modules.tenancy.onboarding import Step, StepResult, register_step


async def _students(uow: UnitOfWork) -> StepResult:
    n = (
        await uow.session.execute(select(func.count()).select_from(Student).where(Student.status == "active"))
    ).scalar_one()
    return StepResult(
        n > 0,
        f"{n:,} active student{'s' if n != 1 else ''}"
        if n
        else "Import a spreadsheet or add students one by one.",
    )


register_step(
    Step(
        "students",
        "Add your students",
        "Import your class lists from Excel or CSV; enrollment numbers become student logins.",
        "/admin/imports",
        True,
        45,
        _students,
    )
)
