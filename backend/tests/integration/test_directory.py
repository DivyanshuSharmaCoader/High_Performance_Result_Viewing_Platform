"""Students & cohort memberships (P6.1, P6.2): constraints, search, limits under concurrency, moves."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.modules.directory.models import CohortMembership, Student
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.models import TenantFeatureOverride
from app.modules.entitlements.service import EntitlementService
from app.modules.identity.models import User
from tests.helpers import Client, client_as, make_structure, make_student, make_tenant

pytestmark = pytest.mark.integration

BASE = "/api/v1/admin/students"


async def _limit(infra, tenant_id, n: int) -> None:
    async with infra.db.platform_uow() as uow:
        uow.session.add(
            TenantFeatureOverride(tenant_id=tenant_id, feature_key=F.MAX_STUDENTS, value=n, reason="test")
        )
    await EntitlementService(infra).invalidate(tenant_id)


async def _usage(infra, tenant_id) -> int:
    async with infra.db.uow(tenant_id) as uow:
        return (await EntitlementService(infra).usage(uow)).get("active_students", 0)


# ---- schema (P6.1) --------------------------------------------------------------------------------


async def test_one_cohort_per_program_per_session_is_enforced_by_the_database(infra) -> None:
    t = await make_tenant(infra)
    s = await make_structure(infra, t)
    student_id = await make_student(infra, t, cohort_id=s.cohort_id)
    with pytest.raises(IntegrityError, match="uq_cohort_memberships__one_per_program_session"):
        async with infra.db.uow(t.id) as uow:
            uow.session.add(
                CohortMembership(
                    tenant_id=t.id,
                    cohort_id=s.sibling_cohort_id,
                    student_id=student_id,
                    session_id=s.session_id,
                    program_id=s.program_id,
                )
            )


async def test_membership_must_copy_the_cohorts_own_session_and_program(infra) -> None:
    t = await make_tenant(infra)
    s = await make_structure(infra, t)
    other = await make_structure(infra, t, current=False)
    student_id = await make_student(infra, t)
    with pytest.raises(IntegrityError, match="fk_cohort_memberships__cohort"):
        async with infra.db.uow(t.id) as uow:
            uow.session.add(
                CohortMembership(
                    tenant_id=t.id,
                    cohort_id=s.cohort_id,
                    student_id=student_id,
                    session_id=s.session_id,
                    program_id=other.program_id,  # lies about the program
                )
            )


async def test_students_cannot_reference_another_tenants_user(infra) -> None:
    a = await make_tenant(infra)
    b = await make_tenant(infra)
    async with infra.db.uow(b.id) as uow:
        b_user = (await uow.session.scalars(select(User.id).limit(1))).one()
    with pytest.raises(IntegrityError, match="fk_students__tenant_id_user_id__users"):
        async with infra.db.uow(a.id) as uow:
            uow.session.add(Student(tenant_id=a.id, enrollment_no="X1", full_name="X", user_id=b_user))


async def test_name_search_index_exists(infra) -> None:
    async with infra.db.platform_uow() as uow:
        indexdef = (
            await uow.session.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_students__name_trgm'")
            )
        ).scalar_one()
    assert "gin" in indexdef and "gin_trgm_ops" in indexdef


# ---- service & API (P6.2) -------------------------------------------------------------------------


async def test_create_normalises_and_lists_with_search_and_filters(app, infra) -> None:
    t = await make_tenant(infra)
    s = await make_structure(infra, t)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        r = await c.post(
            BASE,
            json={
                "enrollment_no": " 1023 03001 ",
                "full_name": "  Aarav   Gupta ",
                "email": "Aarav@Example.com",
                "cohort_ids": [str(s.cohort_id)],
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["enrollment_no"] == "102303001"
        assert body["full_name"] == "Aarav Gupta"
        assert body["email"] == "aarav@example.com"
        assert body["status"] == "active" and body["account"] == "none" and body["version"] == 1
        assert [m["cohort_code"] for m in body["memberships"]] == [s.cohort_code]
        await c.post(BASE, json={"enrollment_no": "102303002", "full_name": "Diya Sharma"})
        await c.post(BASE, json={"enrollment_no": "CSE/21/045", "full_name": "Kabir Singh"})

        def names(resp) -> list[str]:
            return [i["full_name"] for i in resp.json()["items"]]

        assert names(await c.get(BASE, params={"q": "sharma"})) == ["Diya Sharma"]
        assert names(await c.get(BASE, params={"q": "1023"})) == ["Aarav Gupta", "Diya Sharma"]
        assert names(await c.get(BASE, params={"q": "cse/21"})) == ["Kabir Singh"]
        assert names(await c.get(BASE, params={"q": "100%"})) == []  # LIKE wildcards are escaped
        assert names(await c.get(BASE, params={"cohort_id": str(s.cohort_id)})) == ["Aarav Gupta"]
        assert names(await c.get(BASE, params={"account": "none"})) == [
            "Aarav Gupta",
            "Diya Sharma",
            "Kabir Singh",
        ]
        page1 = (await c.get(BASE, params={"limit": 2})).json()
        assert page1["total"] == 3 and len(page1["items"]) == 2 and page1["next_cursor"]
        page2 = (await c.get(BASE, params={"limit": 2, "cursor": page1["next_cursor"]})).json()
        assert [i["enrollment_no"] for i in page2["items"]] == ["CSE/21/045"] and page2["next_cursor"] is None


async def test_validation_and_duplicates(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        assert (await c.post(BASE, json={"enrollment_no": "A1", "full_name": "A"})).status_code == 201
        dup = await c.post(BASE, json={"enrollment_no": " a1 ", "full_name": "B"})
        assert dup.status_code == 409 and dup.json()["field"] == "enrollment_no"
        bad = await c.post(BASE, json={"enrollment_no": "me@school", "full_name": "B"})
        assert bad.status_code == 422 and bad.json()["field"] == "enrollment_no"
        bad_year = await c.post(BASE, json={"enrollment_no": "A2", "full_name": "B", "admission_year": 1800})
        assert bad_year.status_code == 422
    assert await _usage(infra, t.id) == 1  # failed creates rolled back their counter increment


async def test_update_uses_optimistic_locking_and_freezes_enrollment_once_an_account_exists(
    app, infra
) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        created = (await c.post(BASE, json={"enrollment_no": "A1", "full_name": "Asha"})).json()
        url = f"{BASE}/{created['id']}"
        ok = await c.put(url, json={"enrollment_no": "A1", "full_name": "Asha Rao", "version": 1})
        assert ok.status_code == 200 and ok.json()["version"] == 2
        stale = await c.put(url, json={"enrollment_no": "A1", "full_name": "Other", "version": 1})
        assert stale.status_code == 409 and stale.json()["current_version"] == 2
        renamed = await c.put(url, json={"enrollment_no": "A1-NEW", "full_name": "Asha Rao", "version": 2})
        assert renamed.status_code == 200 and renamed.json()["enrollment_no"] == "A1-NEW"

        async with infra.db.uow(t.id) as uow:
            user = User(
                tenant_id=t.id, kind="student", login_id="A1-NEW", full_name="Asha Rao", status="invited"
            )
            uow.session.add(user)
            await uow.flush()
            student = (
                await uow.session.scalars(select(Student).where(Student.id == uuid.UUID(created["id"])))
            ).one()
            student.user_id = user.id
        frozen = await c.put(url, json={"enrollment_no": "A2", "full_name": "Asha Rao", "version": 3})
        assert frozen.status_code == 409 and frozen.json()["code"] == "invalid-state"
        synced = await c.put(url, json={"enrollment_no": "A1-NEW", "full_name": "Asha R. Rao", "version": 3})
        assert synced.json()["account"] == "pending"
        async with infra.db.uow(t.id) as uow:
            assert (await uow.session.scalars(select(User.full_name).where(User.id == user.id))).one() == (
                "Asha R. Rao"
            )


async def test_status_changes_move_the_usage_counter_and_lock_out_archived_accounts(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        sid = (await c.post(BASE, json={"enrollment_no": "A1", "full_name": "Asha"})).json()["id"]
        assert await _usage(infra, t.id) == 1
        async with infra.db.uow(t.id) as uow:
            user = User(
                tenant_id=t.id,
                kind="student",
                login_id="A1",
                full_name="Asha",
                status="active",
                password_hash="x",
            )
            uow.session.add(user)
            await uow.flush()
            (
                await uow.session.scalars(select(Student).where(Student.id == uuid.UUID(sid)))
            ).one().user_id = user.id
        r = await c.put(f"{BASE}/{sid}/status", json={"status": "graduated"})
        assert r.json()["status"] == "graduated" and r.json()["account"] == "active"  # alumni keep access
        assert await _usage(infra, t.id) == 0
        r = await c.put(f"{BASE}/{sid}/status", json={"status": "archived", "reason": "left"})
        assert (
            r.json()["status"] == "archived" and r.json()["archived_at"] and r.json()["account"] == "disabled"
        )
        assert await _usage(infra, t.id) == 0
        r = await c.put(f"{BASE}/{sid}/status", json={"status": "active"})
        assert r.json()["account"] == "active" and r.json()["archived_at"] is None
        assert await _usage(infra, t.id) == 1
        counts = (await c.get(f"{BASE}/counts")).json()
        assert counts == {"active": 1, "graduated": 0, "withdrawn": 0, "archived": 0}
        audit = (await c.get("/api/v1/admin/audit-logs", params={"entity_id": sid})).json()["items"]
        assert {"student.created", "student.status_changed", "student.archived"} <= {
            e["action"] for e in audit
        }


async def test_limit_is_enforced_and_reactivation_counts(app, infra) -> None:
    t = await make_tenant(infra)
    await _limit(infra, t.id, 2)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        a = (await c.post(BASE, json={"enrollment_no": "A1", "full_name": "A"})).json()["id"]
        assert (await c.post(BASE, json={"enrollment_no": "A2", "full_name": "B"})).status_code == 201
        over = await c.post(BASE, json={"enrollment_no": "A3", "full_name": "C"})
        assert over.status_code == 402 and over.json()["code"] == "limit-exceeded"
        await c.put(f"{BASE}/{a}/status", json={"status": "withdrawn"})
        assert (await c.post(BASE, json={"enrollment_no": "A3", "full_name": "C"})).status_code == 201
        back = await c.put(f"{BASE}/{a}/status", json={"status": "active"})
        assert back.status_code == 402
    assert await _usage(infra, t.id) == 2


async def test_parallel_creates_cannot_overshoot_the_limit(app, infra) -> None:
    t = await make_tenant(infra)
    await _limit(infra, t.id, 3)
    await make_student(infra, t)
    await make_student(infra, t)

    async def create(i: int) -> int:
        async with Client(app, t.host) as c:
            await c.login(t.owner_email)
            r = await c.post(BASE, json={"enrollment_no": f"RACE{i}", "full_name": f"Racer {i}"})
            return r.status_code

    results = await asyncio.gather(*(create(i) for i in range(4)))
    assert sorted(results) == [201, 402, 402, 402]
    async with infra.db.uow(t.id) as uow:
        active = (
            await uow.session.execute(text("SELECT count(*) FROM students WHERE status = 'active'"))
        ).scalar_one()
    assert active == 3 and await _usage(infra, t.id) == 3


async def test_assigning_a_sibling_cohort_moves_the_student(app, infra) -> None:
    t = await make_tenant(infra)
    s = await make_structure(infra, t)
    other_session = await make_structure(infra, t, current=False)
    sid = await make_student(infra, t, cohort_id=s.cohort_id)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        r = await c.post(f"{BASE}/{sid}/cohorts", json={"cohort_id": str(s.sibling_cohort_id)})
        assert [m["cohort_code"] for m in r.json()["memberships"]] == [s.sibling_cohort_code]
        r = await c.post(f"{BASE}/{sid}/cohorts", json={"cohort_id": str(other_session.cohort_id)})
        assert {m["cohort_code"] for m in r.json()["memberships"]} == {
            s.sibling_cohort_code,
            other_session.cohort_code,
        }
        r = await c.delete(f"{BASE}/{sid}/cohorts/{other_session.cohort_id}")
        assert [m["cohort_code"] for m in r.json()["memberships"]] == [s.sibling_cohort_code]
        assert (await c.delete(f"{BASE}/{sid}/cohorts/{other_session.cohort_id}")).status_code == 404
        await c.put(f"/api/v1/admin/cohorts/{s.cohort_id}/archived", json={"archived": True})
        archived = await c.post(f"{BASE}/{sid}/cohorts", json={"cohort_id": str(s.cohort_id)})
        assert archived.status_code == 422 and archived.json()["field"] == "cohort_id"
        audit = (await c.get("/api/v1/admin/audit-logs", params={"entity_id": str(sid)})).json()["items"]
        assert any(e["summary"].startswith("Moved ") for e in audit)


async def test_bulk_add_to_cohort_reports_added_moved_and_unchanged(app, infra) -> None:
    t = await make_tenant(infra)
    s = await make_structure(infra, t)
    in_a = await make_student(infra, t, cohort_id=s.cohort_id)
    in_b = await make_student(infra, t, cohort_id=s.sibling_cohort_id)
    loose = await make_student(infra, t)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        r = await c.post(
            f"/api/v1/admin/cohorts/{s.cohort_id}/students",
            json={"student_ids": [str(in_a), str(in_b), str(loose)]},
        )
        assert r.json() == {"added": 1, "moved": 1, "unchanged": 1}
        members = (await c.get(BASE, params={"cohort_id": str(s.cohort_id)})).json()
        assert members["total"] == 3
        missing = await c.post(
            f"/api/v1/admin/cohorts/{s.cohort_id}/students", json={"student_ids": [str(uuid.uuid4())]}
        )
        assert missing.status_code == 404


async def test_faculty_cannot_browse_or_manage_the_student_directory(app, infra) -> None:
    """Faculty see students only through their assigned papers (Phase 8), never the whole directory."""
    t = await make_tenant(infra)
    c = await client_as(app, infra, t, "faculty")
    async with c:
        assert (await c.get(BASE)).status_code == 403
        assert (await c.post(BASE, json={"enrollment_no": "A1", "full_name": "A"})).status_code == 403


# ---- staff profiles (P6.3) ------------------------------------------------------------------------


async def test_staff_profile_fields_are_editable_and_listed(app, infra) -> None:
    t = await make_tenant(infra, plan="enterprise")
    s = await make_structure(infra, t)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        invited = await c.post(
            "/api/v1/admin/staff",
            json={"email": "kaur@example.com", "full_name": "Simran Kaur", "role": "faculty"},
        )
        uid = invited.json()["id"]
        r = await c.put(
            f"/api/v1/admin/staff/{uid}/profile",
            json={
                "full_name": "Dr  Simran Kaur",
                "employee_code": " EMP-042 ",
                "designation": "Assistant Professor",
                "department_id": str(s.department_id),
                "phone": "",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["full_name"] == "Dr Simran Kaur"
        assert r.json()["employee_code"] == "EMP-042" and r.json()["phone"] is None
        listed = {m["id"]: m for m in (await c.get("/api/v1/admin/staff")).json()}
        assert listed[uid]["designation"] == "Assistant Professor"
        assert listed[uid]["department_id"] == str(s.department_id)
        owner = next(m for m in listed.values() if m["role"] == "institution_owner")
        assert owner["designation"] is None  # no profile row yet → nulls, not an error

        bad = await c.put(
            f"/api/v1/admin/staff/{uid}/profile",
            json={"full_name": "Dr Simran Kaur", "department_id": str(uuid.uuid4())},
        )
        assert bad.status_code == 422 and bad.json()["field"] == "department_id"
        audit = (await c.get("/api/v1/admin/audit-logs", params={"entity_id": uid})).json()["items"]
        updated = next(e for e in audit if e["action"] == "user.profile_updated")
        assert updated["after"]["designation"] == "Assistant Professor"
        assert (
            await c.put(f"/api/v1/admin/staff/{uuid.uuid4()}/profile", json={"full_name": "X Y"})
        ).status_code == 404
