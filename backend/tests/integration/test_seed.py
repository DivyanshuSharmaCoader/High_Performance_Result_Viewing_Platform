"""`scorecode seed` creates the demo tenants through the provisioning service and is idempotent (P4.8, P5.4)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.seed import DEMO_TENANTS, seed_platform_user, seed_tenants

pytestmark = pytest.mark.integration


async def _counts(infra) -> dict[str, tuple[int, ...]]:
    out = {}
    async with infra.db.platform_uow() as uow:
        for demo in DEMO_TENANTS:
            row = (
                await uow.session.execute(
                    text(
                        "SELECT (SELECT count(*) FROM academic_sessions s WHERE s.tenant_id = t.id),"
                        " (SELECT count(*) FROM terms x WHERE x.tenant_id = t.id),"
                        " (SELECT count(*) FROM programs x WHERE x.tenant_id = t.id),"
                        " (SELECT count(*) FROM cohorts x WHERE x.tenant_id = t.id),"
                        " (SELECT count(*) FROM courses x WHERE x.tenant_id = t.id),"
                        " (SELECT count(*) FROM users x WHERE x.tenant_id = t.id)"
                        " FROM tenants t WHERE t.slug = :s"
                    ),
                    {"s": demo.slug},
                )
            ).one()
            out[demo.slug] = tuple(row)
    return out


async def test_seed_is_idempotent_and_branded(infra) -> None:
    await seed_tenants(infra)
    await seed_platform_user(infra)
    first = await _counts(infra)
    assert first["thapar"] == (2, 4, 3, 8, 9, 1)
    assert first["demoschool"][3] == 4 and first["democoaching"][3] == 3
    assert await seed_tenants(infra) == []  # nothing new on a second run
    assert await seed_platform_user(infra) is False
    assert await _counts(infra) == first
    async with infra.db.platform_uow() as uow:
        colours = dict(
            (
                await uow.session.execute(
                    text(
                        "SELECT t.slug, b.primary_color FROM tenants t JOIN tenant_branding b ON b.tenant_id = t.id "
                        "WHERE t.slug IN ('thapar','demoschool','democoaching')"
                    )
                )
            ).all()
        )
    assert len(set(colours.values())) == 3  # three distinct brands
