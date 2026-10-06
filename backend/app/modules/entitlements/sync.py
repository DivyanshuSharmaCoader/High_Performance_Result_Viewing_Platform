"""Idempotent sync of the feature/plan catalogue into the database (P4.1).

New features and plans are inserted; existing *plans* keep any values a platform admin changed — only
missing plan_feature rows are added. Feature descriptions/kinds/defaults always follow code.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.db import Database
from app.modules.entitlements.catalogue import FEATURES, PLANS
from app.modules.entitlements.models import Feature, Plan, PlanFeature


async def sync_catalogue(db: Database) -> dict[str, int]:
    added_plans = 0
    added_values = 0
    async with db.platform_uow() as uow:
        s = uow.session
        for f in FEATURES:
            stmt = insert(Feature).values(
                key=f.key, kind=f.kind, description=f.description, default_value=f.default
            )
            await s.execute(
                stmt.on_conflict_do_update(
                    index_elements=["key"],
                    set_={
                        "kind": f.kind,
                        "description": f.description,
                        "default_value": stmt.excluded.default_value,
                    },
                )
            )
        existing = {p.code: p for p in (await s.scalars(select(Plan))).all()}
        for pdef in PLANS:
            plan = existing.get(pdef.code)
            if plan is None:
                plan = Plan(
                    code=pdef.code,
                    name=pdef.name,
                    description=pdef.description,
                    price_paise_yearly=pdef.price_paise_yearly,
                    sort_order=pdef.sort_order,
                    is_public=pdef.is_public,
                )
                s.add(plan)
                await s.flush()
                added_plans += 1
            for f in FEATURES:
                value = pdef.values.get(f.key, f.default)
                result = await s.execute(
                    insert(PlanFeature)
                    .values(plan_id=plan.id, feature_key=f.key, value=value)
                    .on_conflict_do_nothing(index_elements=["plan_id", "feature_key"])
                )
                added_values += int(result.rowcount or 0)  # type: ignore[attr-defined]
    return {"plans_added": added_plans, "plan_values_added": added_values}
