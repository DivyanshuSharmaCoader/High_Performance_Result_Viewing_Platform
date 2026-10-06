"""Tenant isolation suite (P3.10, docs/15 §4.1) — a required CI check.

Generated from the live route table, so every new endpoint is covered automatically:

1. **ID swap** — as tenant A's owner on A's host, call every tenant route whose path has an id with
   tenant B's ids → must be 404, and B's data must be unchanged.
2. **Host swap / cookie replay** — A's session cookie sent to B's host → 401 on every tenant route.
3. **Forged tenant in input** — tenant ids in query/body are ignored or rejected.
4. **DB layer** — in A's context, every tenant table returns 0 rows for B and rejects writes for B.

A route with a path parameter that has no provider below fails the suite: new resource types must
teach the suite how to create a tenant-B instance.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg
import pytest
from sqlalchemy import text

from app.core.clock import utcnow
from app.core.jobs import enqueue
from app.core.security import hash_token, new_token
from app.modules.identity.models import AuthToken
from tests.conftest import PG_HOST, PG_PORT
from tests.helpers import Client, TenantFixture, make_structure, make_student, make_tenant, make_user
from tests.routes import RouteInfo, api_routes

pytestmark = pytest.mark.integration

Provider = Callable[[Any, TenantFixture], Awaitable[Any]]


async def _staff_user(infra: Any, t: TenantFixture) -> uuid.UUID:
    user_id, _ = await make_user(infra, t, "faculty")
    return user_id


async def _job(infra: Any, t: TenantFixture) -> uuid.UUID:
    async with infra.db.uow(t.id) as uow:
        return await enqueue(uow, "notifications.send_email", {"template": "password_reset", "params": {}})


async def _invite_token(infra: Any, t: TenantFixture) -> str:
    user_id, _ = await make_user(infra, t, "faculty")
    token = new_token(32)
    async with infra.db.uow(t.id) as uow:
        uow.session.add(
            AuthToken(
                tenant_id=t.id,
                user_id=user_id,
                purpose="invite",
                token_hash=hash_token(token),
                expires_at=utcnow().replace(year=utcnow().year + 1),
            )
        )
    return token


async def _academic(infra: Any, t: TenantFixture) -> dict[str, uuid.UUID]:
    """One instance of every academic-structure resource in tenant t."""
    from datetime import date

    from app.modules.academics.models import AcademicSession, Cohort, Course, Department, Program, Term

    async with infra.db.uow(t.id) as uow:
        sess = AcademicSession(
            tenant_id=t.id,
            code=f"S{uuid.uuid4().hex[:6]}",
            name="S",
            starts_on=date(2025, 7, 1),
            ends_on=date(2026, 6, 30),
        )
        dept = Department(tenant_id=t.id, code=f"D{uuid.uuid4().hex[:6]}", name="D")
        uow.session.add_all([sess, dept])
        await uow.flush()
        term = Term(tenant_id=t.id, session_id=sess.id, code="T1", name="T1", sequence=1)
        prog = Program(tenant_id=t.id, code=f"P{uuid.uuid4().hex[:6]}", name="P", department_id=dept.id)
        course = Course(tenant_id=t.id, code=f"C{uuid.uuid4().hex[:6]}", name="C")
        uow.session.add_all([term, prog, course])
        await uow.flush()
        cohort = Cohort(
            tenant_id=t.id, code=f"K{uuid.uuid4().hex[:6]}", name="K", program_id=prog.id, session_id=sess.id
        )
        uow.session.add(cohort)
        await uow.flush()
        return {
            "session_id": sess.id,
            "term_id": term.id,
            "department_id": dept.id,
            "program_id": prog.id,
            "cohort_id": cohort.id,
            "course_id": course.id,
        }


def _academic_provider(key: str) -> Provider:
    async def provide(infra: Any, t: TenantFixture) -> uuid.UUID:
        return (await _academic(infra, t))[key]

    return provide


async def _student(infra: Any, t: TenantFixture) -> uuid.UUID:
    s = await make_structure(infra, t, current=False)
    return await make_student(infra, t, cohort_id=s.cohort_id)


async def _import(infra: Any, t: TenantFixture) -> uuid.UUID:
    import hashlib

    from app.modules.files.service import CSV, FileService
    from app.modules.ingestion.models import ImportJob

    data = f"Enrollment,Name\nX{uuid.uuid4().hex[:6]},X\n".encode()
    async with infra.db.uow(t.id) as uow:
        stored = await FileService(infra).store(
            uow, data=data, kind="import", file_type=CSV, original_name="x.csv", uploaded_by=None
        )
        job = ImportJob(
            tenant_id=t.id,
            kind="students",
            status="validated",
            file_id=stored.id,
            file_name="x.csv",
            file_sha256=hashlib.sha256(data).digest(),
            params={},
            rows_valid=1,
            rows_total=1,
        )
        uow.session.add(job)
        await uow.flush()
        return job.id


async def _scheme(infra: Any, t: TenantFixture) -> uuid.UUID:
    from app.modules.grading.service import GradingService
    from app.modules.grading.templates import BY_KEY

    async with infra.db.uow(t.id) as uow:
        scheme = await GradingService(infra).create(
            uow,
            None,
            name=f"S{uuid.uuid4().hex[:6]}",
            description=None,
            config=BY_KEY["simple_letters"].config,
        )
        return scheme.id


async def _exam_and_paper(infra: Any, t: TenantFixture) -> tuple[uuid.UUID, uuid.UUID]:
    from decimal import Decimal

    from app.modules.examinations.models import Examination, ExamPaper

    st = await make_structure(infra, t, current=False)
    scheme_id = await _scheme(infra, t)
    async with infra.db.uow(t.id) as uow:
        exam = Examination(
            tenant_id=t.id, term_id=st.term_id, name=f"E{uuid.uuid4().hex[:6]}", grading_scheme_id=scheme_id
        )
        uow.session.add(exam)
        await uow.flush()
        paper = ExamPaper(
            tenant_id=t.id,
            exam_id=exam.id,
            course_id=st.course_id,
            components=[{"code": "T", "label": "T", "max": "100", "min_pass": None}],
            max_total=Decimal(100),
        )
        uow.session.add(paper)
        await uow.flush()
        return exam.id, paper.id


async def _exam(infra: Any, t: TenantFixture) -> uuid.UUID:
    return (await _exam_and_paper(infra, t))[0]


async def _paper(infra: Any, t: TenantFixture) -> uuid.UUID:
    return (await _exam_and_paper(infra, t))[1]


PROVIDERS: dict[str, Provider] = {
    "user_id": _staff_user,
    "exam_id": _exam,
    "paper_id": _paper,
    "scheme_id": _scheme,
    "student_id": _student,
    "import_id": _import,
    "job_id": _job,
    "token": _invite_token,
    **{
        k: _academic_provider(k)
        for k in ("session_id", "term_id", "department_id", "program_id", "cohort_id", "course_id")
    },
}

# Bodies that pass validation so the request reaches the resource lookup.
_ARCHIVE = {"archived": True}
SAMPLE_BODIES: dict[tuple[str, str], Any] = {
    ("PUT", "/api/v1/admin/staff/{user_id}/role"): {"role": "institution_admin"},
    ("PUT", "/api/v1/admin/staff/{user_id}/status"): {"disabled": True},
    ("PUT", "/api/v1/admin/staff/{user_id}/profile"): {"full_name": "X Y"},
    ("PUT", "/api/v1/admin/academic-sessions/{session_id}"): {
        "code": "X",
        "name": "X",
        "starts_on": "2025-07-01",
        "ends_on": "2026-06-30",
    },
    ("PUT", "/api/v1/admin/academic-sessions/{session_id}/archived"): _ARCHIVE,
    ("POST", "/api/v1/admin/academic-sessions/{session_id}/copy-structure"): {
        "source_session_id": str(uuid.uuid4())
    },
    ("POST", "/api/v1/admin/academic-sessions/{session_id}/terms"): {"code": "T9", "name": "T9"},
    ("PUT", "/api/v1/admin/terms/{term_id}"): {"code": "T9", "name": "T9", "sequence": 1},
    ("PUT", "/api/v1/admin/departments/{department_id}"): {"code": "X", "name": "X"},
    ("PUT", "/api/v1/admin/departments/{department_id}/archived"): _ARCHIVE,
    ("PUT", "/api/v1/admin/programs/{program_id}"): {"code": "X", "name": "X"},
    ("PUT", "/api/v1/admin/programs/{program_id}/archived"): _ARCHIVE,
    ("PUT", "/api/v1/admin/cohorts/{cohort_id}"): {"code": "X", "name": "X"},
    ("PUT", "/api/v1/admin/cohorts/{cohort_id}/archived"): _ARCHIVE,
    ("PUT", "/api/v1/admin/courses/{course_id}"): {"code": "X", "name": "X"},
    ("PUT", "/api/v1/admin/courses/{course_id}/archived"): _ARCHIVE,
    ("PUT", "/api/v1/admin/students/{student_id}"): {"enrollment_no": "X1", "full_name": "X", "version": 1},
    ("PUT", "/api/v1/admin/students/{student_id}/status"): {"status": "archived"},
    ("POST", "/api/v1/admin/students/{student_id}/cohorts"): {"cohort_id": str(uuid.uuid4())},
    ("POST", "/api/v1/admin/cohorts/{cohort_id}/students"): {"student_ids": [str(uuid.uuid4())]},
    ("PUT", "/api/v1/admin/imports/{import_id}/mapping"): {"mapping": {"enrollment_no": 0, "full_name": 1}},
    ("POST", "/api/v1/admin/imports/{import_id}/commit"): {"skip_errors": False},
    ("PUT", "/api/v1/admin/grading-schemes/{scheme_id}"): {"name": "X"},
    ("PUT", "/api/v1/admin/grading-schemes/{scheme_id}/archived"): _ARCHIVE,
    ("PUT", "/api/v1/admin/exams/{exam_id}"): {
        "version": 1,
        "name": "X",
        "kind": "term",
        "grading_scheme_id": str(uuid.uuid4()),
    },
    ("PUT", "/api/v1/admin/exams/{exam_id}/cohorts"): {"cohort_ids": []},
    ("POST", "/api/v1/admin/exams/{exam_id}/papers"): {
        "course_id": str(uuid.uuid4()),
        "components": [{"code": "T", "label": "T", "max": "100"}],
    },
    ("PUT", "/api/v1/admin/exams/{exam_id}/papers/{paper_id}"): {
        "components": [{"code": "T", "label": "T", "max": "100"}]
    },
    ("PUT", "/api/v1/admin/exams/{exam_id}/papers/{paper_id}/assignments"): {
        "cohort_id": str(uuid.uuid4()),
        "user_ids": [],
    },
    ("POST", "/api/v1/admin/exams/{exam_id}/transitions"): {"action": "open_entry"},
    ("POST", "/api/v1/admin/grading-schemes/{scheme_id}/versions"): {
        "config": {"strategy": "marks_only"},
        "based_on": 1,
    },
}


async def _b_fingerprint(infra: Any, t: TenantFixture) -> tuple[Any, ...]:
    async with infra.db.uow(t.id) as uow:
        audit = (await uow.session.execute(text("SELECT count(*) FROM audit_logs"))).scalar_one()
        users = (
            await uow.session.execute(
                text(
                    "SELECT string_agg(id::text || status || failed_login_count::text, ',' ORDER BY id) FROM users"
                )
            )
        ).scalar_one()
        roles = (
            await uow.session.execute(
                text("SELECT string_agg(user_id::text || role, ',' ORDER BY user_id, role) FROM user_roles")
            )
        ).scalar_one()
        jobs = (
            await uow.session.execute(
                text("SELECT string_agg(id::text || status, ',' ORDER BY id) FROM jobs")
            )
        ).scalar_one()
        students = (
            await uow.session.execute(
                text("SELECT string_agg(id::text || status || version::text, ',' ORDER BY id) FROM students")
            )
        ).scalar_one()
        members = (
            await uow.session.execute(
                text(
                    "SELECT string_agg(student_id::text || cohort_id::text, ',' ORDER BY student_id, cohort_id) "
                    "FROM cohort_memberships"
                )
            )
        ).scalar_one()
        imports = (
            await uow.session.execute(
                text("SELECT string_agg(id::text || status, ',' ORDER BY id) FROM import_jobs")
            )
        ).scalar_one()
        schemes = (
            await uow.session.execute(
                text(
                    "SELECT string_agg(s.id::text || s.name || coalesce(s.archived_at::text, ''), ',' ORDER BY s.id)"
                    " || (SELECT count(*)::text FROM grading_scheme_versions)"
                    " || coalesce((SELECT default_grading_scheme_id::text FROM tenant_settings), '')"
                    " FROM grading_schemes s"
                )
            )
        ).scalar_one()
        exams = (
            await uow.session.execute(
                text(
                    "SELECT string_agg(e.id::text || e.status || e.version::text, ',' ORDER BY e.id)"
                    " || (SELECT count(*)::text FROM exam_papers) || (SELECT count(*)::text FROM exam_cohorts)"
                    " FROM examinations e"
                )
            )
        ).scalar_one()
    return audit, users, roles, jobs, students, members, imports, schemes, exams


async def _call(c: Client, route: RouteInfo, url: str) -> Any:
    body = SAMPLE_BODIES.get((route.method, route.path))
    if route.method == "GET":
        return await c.get(url)
    if route.method == "DELETE":
        return await c.delete(url)
    return await getattr(c, route.method.lower())(url, json=body if body is not None else {})


async def test_id_swap_on_every_tenant_route_returns_404_and_changes_nothing(app, infra) -> None:
    a = await make_tenant(infra, plan="enterprise")
    b = await make_tenant(infra, plan="enterprise")
    routes = [
        r
        for r in api_routes(app)
        if r.params and r.realm in ("tenant", "public") and "platform" not in r.path
    ]
    missing = sorted({p for r in routes for p in r.params if p not in PROVIDERS})
    assert not missing, f"isolation suite has no tenant-B provider for path params: {missing}"
    assert routes, "expected tenant routes with ids"
    checked = []
    async with Client(app, a.host) as c:
        await c.login(a.owner_email)
        for route in routes:
            values = {p: await PROVIDERS[p](infra, b) for p in route.params}
            before = await _b_fingerprint(infra, b)
            r = await _call(c, route, route.url(values))
            after = await _b_fingerprint(infra, b)
            assert r.status_code == 404, (
                f"{route.method} {route.path} with tenant B ids → {r.status_code}: {r.text}"
            )
            assert before == after, f"{route.method} {route.path} modified tenant B"
            checked.append(f"{route.method} {route.path}")
    assert len(checked) == len(routes)


async def test_session_cookie_from_tenant_a_is_rejected_on_every_tenant_b_route(app, infra) -> None:
    a = await make_tenant(infra)
    b = await make_tenant(infra)
    async with Client(app, a.host) as ca:
        await ca.login(a.owner_email)
        cookie = ca.session_cookie()
    routes = [r for r in api_routes(app) if r.realm == "tenant"]
    async with Client(app, b.host) as cb:
        await cb.ensure_csrf()
        csrf = await cb.ensure_csrf()
        for route in routes:
            url = route.url({p: uuid.uuid4() for p in route.params})
            headers = {"Cookie": f"sc_session={cookie}; sc_csrf={csrf}", "X-CSRF-Token": csrf}
            r = await cb.http.request(
                route.method, url, headers=headers, json=SAMPLE_BODIES.get((route.method, route.path), {})
            )
            assert r.status_code == 401, f"{route.method} {route.path} on B with A's cookie → {r.status_code}"


async def test_forged_tenant_ids_in_input_are_ignored_or_rejected(app, infra) -> None:
    a = await make_tenant(infra)
    b = await make_tenant(infra)
    async with Client(app, a.host) as c:
        await c.login(a.owner_email)
        me = await c.get("/api/v1/me", params={"tenant_id": str(b.id)})
        assert me.json()["tenant"]["id"] == str(a.id)
        r = await c.post(
            "/api/v1/admin/staff",
            json={"email": "x@example.com", "full_name": "X Y", "role": "faculty", "tenant_id": str(b.id)},
        )
        assert r.status_code == 422
        r = await c.get("/api/v1/tenant/config", headers={"X-Tenant-Id": str(b.id)})
        assert r.json()["tenant"]["slug"] == a.slug


async def test_every_tenant_table_is_isolated_at_the_database(infra, migrated_db: str) -> None:
    a = await make_tenant(infra)
    b = await make_tenant(infra)
    conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user="scorecode_app", password="app-dev-pw", database=migrated_db
    )
    try:
        tables = [
            r["relname"]
            for r in await conn.fetch(
                """
                SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
                 WHERE c.relkind IN ('r','p') AND NOT c.relispartition AND c.relrowsecurity
                   AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'tenant_id')
                """
            )
        ]
        assert len(tables) >= 13
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(a.id))
            for table in tables:
                n = await conn.fetchval(f"SELECT count(*) FROM {table} WHERE tenant_id = $1", b.id)
                assert n == 0, f"{table} leaked {n} rows of tenant B"
            assert await conn.fetchval("SELECT count(*) FROM tenants WHERE id = $1", b.id) == 0
        # Writes for B inside A's context are rejected by WITH CHECK.
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(a.id))
                await conn.execute(
                    "INSERT INTO tenant_usage_counters (tenant_id, metric, value) VALUES ($1, 'storage_bytes', 0)",
                    b.id,
                )
    finally:
        await conn.close()
