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
                        " (SELECT count(*) FROM users x WHERE x.tenant_id = t.id),"
                        " (SELECT count(*) FROM students x WHERE x.tenant_id = t.id),"
                        " (SELECT count(DISTINCT student_id) FROM cohort_memberships x WHERE x.tenant_id = t.id),"
                        " (SELECT value FROM tenant_usage_counters x"
                        "   WHERE x.tenant_id = t.id AND x.metric = 'active_students'),"
                        " (SELECT count(*) FROM grading_schemes x WHERE x.tenant_id = t.id),"
                        " (SELECT count(*) FROM tenant_settings x"
                        "   WHERE x.tenant_id = t.id AND x.default_grading_scheme_id IS NOT NULL)"
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
    # sessions, terms, programs, cohorts, courses, users (owner + demo student), students, placed, usage,
    # grading schemes, default scheme set
    assert first["thapar"] == (2, 4, 3, 8, 9, 2, 120, 120, 120, 1, 1)
    assert first["demoschool"][9:] == (1, 1) and first["democoaching"][9:] == (1, 1)
    assert first["demoschool"][3] == 4 and first["democoaching"][3] == 3
    assert first["demoschool"][6] == 120 and first["democoaching"][6] == 120  # 3 cohorts × 40
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


async def test_seeded_demo_student_can_sign_in(app, infra) -> None:
    from app.demo.students import demo_student_login
    from app.seed import DEMO_PASSWORD
    from tests.helpers import Client

    await seed_tenants(infra)
    async with Client(app, "thapar.localhost") as c:
        r = await c.post(
            "/api/v1/auth/login", json={"login_id": demo_student_login("thapar"), "password": DEMO_PASSWORD}
        )
        assert r.status_code == 200, r.text
        me = (await c.get("/api/v1/me")).json()
        assert me["kind"] == "student" and me["login_id"] == "102401001"


async def test_demo_history_publishes_through_the_services_and_is_idempotent(infra) -> None:
    """`scorecode seed --with-history` (P17.1, P17.2): the states the presentation needs (docs/demo/)."""
    from app.core.jobs import Worker
    from app.seed import seed_histories

    await seed_tenants(infra, students_per_tenant=24)
    first = await seed_histories(infra)
    assert first["thapar"] == [
        ("End semester examination, odd 2024", "published"),
        ("End semester examination, even 2025", "published"),
        ("End semester examination, odd 2025", "published"),
        ("End semester examination, even 2026", "approved"),
        ("Mid-semester test, even 2026", "marks_entry_open"),
    ]
    assert [s for _, s in first["demoschool"]] == ["published", "approved"]
    assert [s for _, s in first["democoaching"]] == ["published", "published", "approved"]
    assert await seed_histories(infra) == first  # a second run moves nothing
    await Worker(infra, ["pdf", "notifications", "publishing"]).drain()  # the publications' own jobs
    async with infra.db.platform_uow() as uow:
        rows = (
            await uow.session.execute(
                text(
                    "SELECT t.slug, count(DISTINCT p.id) AS pubs, count(r.*) AS results"
                    " FROM tenants t JOIN publications p ON p.tenant_id = t.id AND p.status = 'published'"
                    " JOIN published_results r ON r.publication_id = p.id"
                    " WHERE t.slug IN ('thapar', 'demoschool', 'democoaching') GROUP BY t.slug ORDER BY 1"
                )
            )
        ).all()
        demo_student = (
            await uow.session.execute(
                text(
                    "SELECT count(*) FROM published_results r JOIN students s ON s.id = r.student_id"
                    " JOIN tenants t ON t.id = s.tenant_id WHERE t.slug = 'thapar' AND s.enrollment_no = '102401001'"
                )
            )
        ).scalar_one()
    pubs = {r.slug: (r.pubs, r.results) for r in rows}
    assert pubs["thapar"][0] == 3 and pubs["demoschool"][0] == 1 and pubs["democoaching"][0] == 2
    assert demo_student == 3  # the demo student's history: two academic years
