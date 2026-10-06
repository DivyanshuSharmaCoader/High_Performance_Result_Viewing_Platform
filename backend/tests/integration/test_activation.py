"""Student activation codes (P6.7): issue per cohort → student activates → signs in; codes are single-use,
replaceable, tenant-bound and never stored in plaintext."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.modules.directory.models import Student
from app.modules.identity.models import AuthToken, User
from tests.helpers import Client, client_as, make_structure, make_student, make_tenant

pytestmark = pytest.mark.integration

CODES = "/api/v1/admin/activation-codes"
PASSWORD = "a-long-student-passphrase"


async def _activate(c: Client, enrollment: str, code: str, password: str = PASSWORD):
    return await c.post(
        "/api/v1/auth/activate", json={"enrollment_no": enrollment, "code": code, "password": password}
    )


async def test_cohort_codes_activate_students_who_can_then_sign_in(app, infra) -> None:
    t = await make_tenant(infra)
    s = await make_structure(infra, t)
    await make_student(infra, t, enrollment_no="102303001", full_name="Aarav Gupta", cohort_id=s.cohort_id)
    await make_student(infra, t, enrollment_no="102303002", full_name="Diya Sharma", cohort_id=s.cohort_id)
    await make_student(infra, t, enrollment_no="OTHER1", cohort_id=s.sibling_cohort_id)
    async with Client(app, t.host) as admin:
        await admin.login(t.owner_email)
        r = await admin.post(CODES, json={"cohort_id": str(s.cohort_id)})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["cohort_code"] == s.cohort_code and body["skipped"] == []
        slips = {i["enrollment_no"]: i for i in body["issued"]}
        assert set(slips) == {"102303001", "102303002"}
        code = slips["102303001"]["code"]
        assert len(code) == 11 and code[5] == "-" and slips["102303001"]["cohort_code"] == s.cohort_code
        listed = (await admin.get("/api/v1/admin/students", params={"account": "pending"})).json()
        assert listed["total"] == 2

    async with Client(app, t.host) as student:
        wrong = await _activate(student, "102303001", slips["102303002"]["code"])
        assert wrong.status_code == 422  # a code is bound to its enrollment number
        r = await _activate(student, " 1023 03001 ", code.lower().replace("-", " "))  # forgiving input
        assert r.status_code == 200, r.text
        assert r.json()["user_kind"] == "student" and r.json()["roles"] == ["student"]
        me = (await student.get("/api/v1/me")).json()
        assert (
            me["full_name"] == "Aarav Gupta" and me["kind"] == "student" and "me.results" in me["permissions"]
        )
        assert (await student.get("/api/v1/admin/students")).status_code == 403
        assert (await student.post("/api/v1/auth/logout")).status_code == 200

    async with Client(app, t.host) as again:
        assert (await _activate(again, "102303001", code)).status_code == 422  # single use
        r = await again.post("/api/v1/auth/login", json={"login_id": "102303001", "password": PASSWORD})
        assert r.status_code == 200

    async with Client(app, t.host) as admin:
        await admin.login(t.owner_email)
        second = (await admin.post(CODES, json={"cohort_id": str(s.cohort_id)})).json()
        reasons = {i["enrollment_no"]: i["reason"] for i in second["skipped"]}
        assert reasons == {"102303001": "already_active", "102303002": "has_code"} and second["issued"] == []
        audit = (await admin.get("/api/v1/admin/audit-logs", params={"action": "activation_codes"})).json()
        assert audit["items"][0]["after"] == {"issued": 2, "skipped": 0, "replaced": False}
        assert code not in str(audit)


async def test_replacing_codes_invalidates_the_old_slip(app, infra) -> None:
    t = await make_tenant(infra)
    sid = await make_student(infra, t, enrollment_no="R1")
    async with Client(app, t.host) as admin:
        await admin.login(t.owner_email)
        old = (await admin.post(CODES, json={"student_ids": [str(sid)]})).json()["issued"][0]["code"]
        new = (await admin.post(CODES, json={"student_ids": [str(sid)], "replace_existing": True})).json()
        assert new["issued"][0]["code"] != old
    async with Client(app, t.host) as student:
        assert (await _activate(student, "R1", old)).status_code == 422
        assert (await _activate(student, "R1", new["issued"][0]["code"])).status_code == 200


async def test_codes_are_tenant_bound_and_only_hashes_are_stored(app, infra) -> None:
    a = await make_tenant(infra)
    b = await make_tenant(infra)
    sid = await make_student(infra, a, enrollment_no="SAME1")
    await make_student(infra, b, enrollment_no="SAME1")
    async with Client(app, a.host) as admin:
        await admin.login(a.owner_email)
        code = (await admin.post(CODES, json={"student_ids": [str(sid)]})).json()["issued"][0]["code"]
    async with Client(app, b.host) as other:
        assert (await _activate(other, "SAME1", code)).status_code == 422
    async with infra.db.uow(a.id) as uow:
        user_id = (await uow.session.scalars(select(Student.user_id).where(Student.id == sid))).one()
        user = (await uow.session.scalars(select(User).where(User.id == user_id))).one()
        assert (user.kind, user.status, user.password_hash, user.login_id) == (
            "student",
            "invited",
            None,
            "SAME1",
        )
        token = (await uow.session.scalars(select(AuthToken).where(AuthToken.user_id == user_id))).one()
        assert code.replace("-", "").encode() not in token.token_hash
        dump = (
            await uow.session.execute(text("SELECT string_agg(t::text, '') FROM auth_tokens t"))
        ).scalar_one()
        assert code.replace("-", "") not in dump


async def test_archived_students_get_no_codes_and_input_is_validated(app, infra) -> None:
    t = await make_tenant(infra)
    sid = await make_student(infra, t, enrollment_no="Z1")
    async with Client(app, t.host) as admin:
        await admin.login(t.owner_email)
        await admin.put(f"/api/v1/admin/students/{sid}/status", json={"status": "archived"})
        r = (await admin.post(CODES, json={"student_ids": [str(sid)]})).json()
        assert r["issued"] == [] and r["skipped"][0]["reason"] == "not_active_student"
        assert (await admin.post(CODES, json={})).status_code == 422
        both = await admin.post(CODES, json={"cohort_id": str(sid), "student_ids": [str(sid)]})
        assert both.status_code == 422
    faculty = await client_as(app, infra, t, "faculty")
    async with faculty:
        assert (await faculty.post(CODES, json={"student_ids": [str(sid)]})).status_code == 403


async def test_a_class_can_activate_from_one_network_but_one_student_cannot_be_brute_forced(
    app, infra
) -> None:
    """docs/10 §7: 5 attempts/hour per enrollment no.; the per-IP limit is wide enough for a classroom."""
    t = await make_tenant(infra)
    s = await make_structure(infra, t)
    for i in range(8):
        await make_student(infra, t, enrollment_no=f"CLS{i}", cohort_id=s.cohort_id)
    async with Client(app, t.host) as admin:
        await admin.login(t.owner_email)
        slips = (await admin.post(CODES, json={"cohort_id": str(s.cohort_id)})).json()["issued"]
    shared_ip = "203.0.113.7"  # every student behind the school's NAT
    for slip in slips:
        async with Client(app, t.host, ip=shared_ip) as student:
            r = await _activate(student, slip["enrollment_no"], slip["code"])
            assert r.status_code == 200, (slip["enrollment_no"], r.text)
    sid = await make_student(infra, t, enrollment_no="TARGET1")
    async with Client(app, t.host) as admin:
        await admin.login(t.owner_email)
        await admin.post(CODES, json={"student_ids": [str(sid)]})
    statuses = []
    for _ in range(6):
        async with Client(app, t.host) as attacker:  # a new address each time doesn't help
            statuses.append((await _activate(attacker, "TARGET1", "AAAAA-AAAAA")).status_code)
    assert statuses[:5] == [422] * 5 and statuses[5] == 429
