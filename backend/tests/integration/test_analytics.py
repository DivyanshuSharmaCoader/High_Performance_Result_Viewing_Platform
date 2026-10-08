"""Exam statistics (P13.1, P13.3): computed with the results, frozen with each publication, and shown to
students only as far as the institution allows.

Uses the approved exam from test_results: cohort A (A001, A002, A003) and cohort B (B001).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.helpers import Client
from tests.integration.test_publishing import _approved, _as_student, _logins, _publish
from tests.integration.test_results import Exam

pytestmark = pytest.mark.integration


async def _stats_level(app, e: Exam, level: str) -> None:
    """Through the settings API, as an institution would (it also refreshes the read cache)."""
    from app.modules.tenancy.router import SETTINGS_FIELDS

    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        current = (await c.get("/api/v1/admin/settings")).json()
        body = {k: current[k] for k in (*SETTINGS_FIELDS, "version")} | {"student_stats": level}
        r = await c.put("/api/v1/admin/settings", json=body)
        assert r.status_code == 200, r.text


async def test_statistics_compare_sections_and_are_frozen_with_the_publication(app, infra) -> None:
    e = await _approved(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        stats = (await c.get(e.base)).json()["run"]["stats"]
        pub = (await _publish(c, e)).json()
    assert stats["stdev_percentage"] is not None
    paper = stats["papers"][0]
    assert {"median", "stdev", "histogram"} <= set(paper) and len(paper["histogram"]) == 10
    sections = {s["code"]: s for s in stats["cohorts"]}
    assert set(sections) == {e.x.s.cohort_code, e.x.s.sibling_cohort_code}
    assert sum(s["students"] for s in sections.values()) == stats["students"] == 4
    assert all(s["name"] and s["cohort_id"] for s in sections.values())
    async with infra.db.uow(e.x.t.id) as uow:
        frozen = (
            await uow.session.execute(
                text("SELECT stats FROM exam_statistics WHERE publication_id = :p"), {"p": pub["id"]}
            )
        ).scalar_one()
    assert frozen == stats  # what was approved is what the publication keeps


async def test_students_see_only_the_aggregates_the_institution_allows(app, infra) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001")
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        pub = (await _publish(c, e)).json()
    url = f"/api/v1/me/results/{pub['id']}/stats"

    async with await _as_student(app, e, "A001") as a1:
        default = (await a1.get(url)).json()
        assert default["available"] is True and set(default["stats"]) == {"average_percentage", "papers"}

    await _stats_level(app, e, "none")
    async with await _as_student(app, e, "A001") as a1:
        assert (await a1.get(url)).json() == {"available": False, "stats": None}

    await _stats_level(app, e, "full")
    async with await _as_student(app, e, "A001") as a1:
        full = (await a1.get(url)).json()["stats"]
    assert {"histogram", "median_percentage", "stdev_percentage", "pass_percentage", "grades"} <= set(full)
    assert "cohorts" not in full  # comparing sections is for staff
    assert all("lowest" not in p and "paper_id" not in p for p in full["papers"])
    assert {"median", "highest", "pass_percentage"} <= set(full["papers"][0])
