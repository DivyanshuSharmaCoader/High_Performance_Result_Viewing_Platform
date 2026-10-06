"""Academic structure (P5.1–P5.2): CRUD, per-tenant uniqueness, current session, archiving rules,
department entitlement, copy-structure, audit."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.helpers import Client, make_tenant

pytestmark = pytest.mark.integration

S = "/api/v1/admin"


async def _owner(app, infra, plan: str = "growth"):
    t = await make_tenant(infra, plan=plan)
    c = Client(app, t.host)
    await c.login(t.owner_email)
    return t, c


async def _session(c: Client, code: str = "2025-26", **kw) -> dict:
    body = {"code": code, "name": f"Session {code}", "starts_on": "2025-07-01", "ends_on": "2026-06-30", **kw}
    r = await c.post(f"{S}/academic-sessions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_sessions_terms_and_current_session(app, infra) -> None:
    _t, c = await _owner(app, infra)
    async with c:
        first = await _session(c, "2024-25", starts_on="2024-07-01", ends_on="2025-06-30")
        assert first["is_current"] is True  # the first session becomes current automatically
        second = await _session(c, "2025-26", make_current=True)
        sessions = {s["code"]: s for s in (await c.get(f"{S}/academic-sessions")).json()}
        assert sessions["2025-26"]["is_current"] and not sessions["2024-25"]["is_current"]
        dup = await c.post(
            f"{S}/academic-sessions",
            json={"code": " 2025-26 ", "name": "Dup", "starts_on": "2025-07-01", "ends_on": "2026-06-30"},
        )
        assert dup.status_code == 409 and dup.json()["field"] == "code"
        bad = await c.post(
            f"{S}/academic-sessions",
            json={"code": "X", "name": "X", "starts_on": "2026-01-01", "ends_on": "2025-01-01"},
        )
        assert bad.status_code == 422 and bad.json()["field"] == "ends_on"
        r = await c.post(
            f"{S}/academic-sessions/{second['id']}/terms",
            json={"code": "odd", "name": "Odd semester", "starts_on": "2025-07-15", "ends_on": "2025-12-20"},
        )
        assert r.status_code == 201 and r.json()["code"] == "ODD" and r.json()["sequence"] == 1
        r = await c.post(
            f"{S}/academic-sessions/{second['id']}/terms", json={"code": "EVEN", "name": "Even semester"}
        )
        assert r.json()["sequence"] == 2
        outside = await c.post(
            f"{S}/academic-sessions/{second['id']}/terms",
            json={"code": "SUM", "name": "Summer", "starts_on": "2026-07-05"},
        )
        assert outside.status_code == 422 and outside.json()["field"] == "starts_on"
        archive_current = await c.put(
            f"{S}/academic-sessions/{second['id']}/archived", json={"archived": True}
        )
        assert archive_current.status_code == 409
        r = await c.put(f"{S}/academic-sessions/{first['id']}/archived", json={"archived": True})
        assert r.status_code == 200 and r.json()["archived_at"]
        assert [s["code"] for s in (await c.get(f"{S}/academic-sessions")).json()] == ["2025-26"]


async def test_departments_programs_cohorts_courses(app, infra) -> None:
    t, c = await _owner(app, infra)
    async with c:
        sess = await _session(c)
        cse = (await c.post(f"{S}/departments", json={"code": "cse", "name": "Computer Science"})).json()
        ece = (await c.post(f"{S}/departments", json={"code": "ECE", "name": "Electronics"})).json()
        prog = await c.post(
            f"{S}/programs",
            json={
                "code": "BE-COE",
                "name": "B.E. Computer Engineering",
                "department_id": cse["id"],
                "level": "UG",
                "duration_terms": 8,
            },
        )
        assert prog.status_code == 201, prog.text
        prog = prog.json()
        cohort = await c.post(
            f"{S}/cohorts",
            json={
                "code": "coe-2a",
                "name": "COE 2nd year A",
                "program_id": prog["id"],
                "session_id": sess["id"],
            },
        )
        assert cohort.status_code == 201 and cohort.json()["code"] == "COE-2A"
        dup = await c.post(
            f"{S}/cohorts",
            json={"code": "COE-2A", "name": "dup", "program_id": prog["id"], "session_id": sess["id"]},
        )
        assert dup.status_code == 409
        course = await c.post(
            f"{S}/courses",
            json={"code": "ucs301", "name": "Data Structures", "department_id": cse["id"], "credits": "4.0"},
        )
        assert course.status_code == 201 and course.json()["credits"] == "4.0"
        bad_credits = await c.post(f"{S}/courses", json={"code": "X1", "name": "X", "credits": "4.25"})
        assert bad_credits.status_code == 422
        listing = (await c.get(f"{S}/courses", params={"q": "data"})).json()
        assert listing["total"] == 1 and listing["items"][0]["code"] == "UCS301"
        r = await c.put(f"{S}/departments/{ece['id']}/archived", json={"archived": True})
        assert r.status_code == 200
        r = await c.post(
            f"{S}/programs", json={"code": "BE-ECE", "name": "B.E. ECE", "department_id": ece["id"]}
        )
        assert r.status_code == 422 and r.json()["field"] == "department_id"
        r = await c.put(f"{S}/programs/{prog['id']}/archived", json={"archived": True})
        r = await c.post(
            f"{S}/cohorts",
            json={"code": "COE-2B", "name": "B", "program_id": prog["id"], "session_id": sess["id"]},
        )
        assert r.status_code == 422 and r.json()["field"] == "program_id"
        summary = (await c.get(f"{S}/academic-structure/summary")).json()
        assert summary == {"sessions": 1, "departments": 1, "programs": 0, "cohorts": 1, "courses": 1}
    async with infra.db.uow(t.id) as uow:
        actions = set((await uow.session.execute(text("SELECT action FROM audit_logs"))).scalars().all())
    assert {
        "department.created",
        "program.created",
        "cohort.created",
        "course.created",
        "department.archived",
        "program.archived",
    } <= actions


async def test_multiple_departments_is_an_entitlement(app, infra) -> None:
    _t, c = await _owner(app, infra, plan="free")
    async with c:
        assert (await c.post(f"{S}/departments", json={"code": "MAIN", "name": "Main"})).status_code == 201
        r = await c.post(f"{S}/departments", json={"code": "SEC", "name": "Secondary wing"})
        assert r.status_code == 402 and r.json()["feature"] == "multiple_departments"


async def test_copy_structure_from_previous_session_is_idempotent(app, infra) -> None:
    _t, c = await _owner(app, infra)
    async with c:
        old = await _session(c, "2024-25", starts_on="2024-07-01", ends_on="2025-06-30")
        new = await _session(c, "2025-26")
        prog = (await c.post(f"{S}/programs", json={"code": "CLS8", "name": "Class 8"})).json()
        for code in ("8A", "8B"):
            await c.post(
                f"{S}/cohorts",
                json={
                    "code": code,
                    "name": f"Class {code}",
                    "program_id": prog["id"],
                    "session_id": old["id"],
                },
            )
        await c.post(f"{S}/academic-sessions/{old['id']}/terms", json={"code": "T1", "name": "Term 1"})
        r = await c.post(
            f"{S}/academic-sessions/{new['id']}/copy-structure", json={"source_session_id": old["id"]}
        )
        assert r.json() == {"terms": 1, "cohorts": 2}
        again = await c.post(
            f"{S}/academic-sessions/{new['id']}/copy-structure", json={"source_session_id": old["id"]}
        )
        assert again.json() == {"terms": 0, "cohorts": 0}
        cohorts = (await c.get(f"{S}/cohorts", params={"session_id": new["id"]})).json()
        assert sorted(x["code"] for x in cohorts) == ["8A", "8B"]
        self_copy = await c.post(
            f"{S}/academic-sessions/{new['id']}/copy-structure", json={"source_session_id": new["id"]}
        )
        assert self_copy.status_code == 422


async def test_cross_tenant_references_are_rejected(app, infra) -> None:
    """Creating a cohort in tenant A that points at tenant B's program must fail (404), never link."""
    _a, ca = await _owner(app, infra)
    _b, cb = await _owner(app, infra)
    async with ca, cb:
        b_prog = (await cb.post(f"{S}/programs", json={"code": "P1", "name": "B's program"})).json()
        a_sess = await _session(ca)
        r = await ca.post(
            f"{S}/cohorts",
            json={"code": "X", "name": "X", "program_id": b_prog["id"], "session_id": a_sess["id"]},
        )
        assert r.status_code == 404
