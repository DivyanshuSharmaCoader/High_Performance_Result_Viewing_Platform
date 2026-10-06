"""Default grading scheme for each demo tenant, created from the starter templates (idempotent)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core.container import Infra
from app.modules.grading.models import GradingScheme
from app.modules.grading.service import GradingService
from app.modules.grading.templates import BY_KEY

SCHEMES = {
    "thapar": ("credit_10_point", "Undergraduate 10-point scale"),
    "demoschool": ("board_9_point", "Secondary school bands"),
    "democoaching": ("marks_with_ranks", "Test series (marks and ranks)"),
}


async def seed_grading(infra: Infra, tenant_id: uuid.UUID, slug: str) -> bool:
    spec = SCHEMES.get(slug)
    if spec is None:
        return False
    template = BY_KEY[spec[0]]
    async with infra.db.uow(tenant_id) as uow:
        exists = (
            await uow.session.scalars(
                select(GradingScheme.id).where(func.lower(GradingScheme.name) == spec[1].lower())
            )
        ).first()
        if exists:
            return False
        await GradingService(infra).create(
            uow, None, name=spec[1], description=template.description, config=template.config
        )
    return True
