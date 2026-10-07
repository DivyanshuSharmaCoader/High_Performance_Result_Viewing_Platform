"""The public plan catalogue, for the pricing page and the in-app plan comparison."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.core.http import InfraDep, public
from app.core.tenant import Realm
from app.modules.entitlements.catalogue import FEATURES, TRIAL_DAYS, TRIAL_PLAN_CODE
from app.modules.entitlements.models import Plan, PlanFeature

router = APIRouter(prefix="/api/v1", tags=["plans"])


class PublicPlan(BaseModel):
    code: str
    name: str
    description: str
    price_paise_yearly: int | None
    limits: dict[str, int | None]
    features: dict[str, Any]


class PlanCatalogue(BaseModel):
    plans: list[PublicPlan]
    trial: PublicPlan
    trial_days: int


@router.get("/plans", dependencies=[public(Realm.SITE, Realm.TENANT)])
async def plan_catalogue(response: Response, infra: InfraDep) -> PlanCatalogue:
    """Values as stored (a platform admin may have changed them), not as written in code."""
    kinds = {f.key: f.kind for f in FEATURES}
    async with infra.db.platform_uow() as uow:
        plans = (
            await uow.session.scalars(
                select(Plan)
                .where(Plan.active, (Plan.is_public) | (Plan.code == TRIAL_PLAN_CODE))
                .order_by(Plan.sort_order)
            )
        ).all()
        values: dict[Any, dict[str, Any]] = {}
        for pf in (await uow.session.scalars(select(PlanFeature))).all():
            values.setdefault(pf.plan_id, {})[pf.feature_key] = pf.value

    def out(p: Plan) -> PublicPlan:
        v = values.get(p.id, {})
        return PublicPlan(
            code=p.code,
            name=p.name,
            description=p.description,
            price_paise_yearly=p.price_paise_yearly,
            limits={k: v.get(k) for k, kind in kinds.items() if kind == "limit"},
            features={k: v.get(k) for k, kind in kinds.items() if kind != "limit"},
        )

    response.headers["Cache-Control"] = "public, max-age=300"
    trial = next(p for p in plans if p.code == TRIAL_PLAN_CODE)
    return PlanCatalogue(
        plans=[out(p) for p in plans if p.code != TRIAL_PLAN_CODE],
        trial=out(trial),
        trial_days=TRIAL_DAYS,
    )
