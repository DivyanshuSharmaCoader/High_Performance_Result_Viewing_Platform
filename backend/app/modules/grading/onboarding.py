"""Onboarding step owned by the grading module (registered into the tenancy checklist)."""

from __future__ import annotations

from sqlalchemy import select

from app.core.db import UnitOfWork
from app.modules.grading.models import GradingScheme
from app.modules.tenancy.models import TenantSettings
from app.modules.tenancy.onboarding import Step, StepResult, register_step


async def _grading(uow: UnitOfWork) -> StepResult:
    default_id = (await uow.session.scalars(select(TenantSettings.default_grading_scheme_id))).one_or_none()
    if default_id is None:
        return StepResult(False, "Pick a starter scheme and adjust the grade bands to your rules.")
    name = (await uow.session.scalars(select(GradingScheme.name).where(GradingScheme.id == default_id))).one()
    return StepResult(True, f"Default: {name}")


register_step(
    Step(
        "grading",
        "Choose how results are graded",
        "Grade bands, grade points and credits, or marks only — with your pass rules and rounding.",
        "/admin/grading",
        True,
        50,
        _grading,
    )
)
