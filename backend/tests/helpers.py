"""Test helpers: tenant provisioning through the real service, and host-aware HTTP clients."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pyotp

from app.core.container import Infra
from app.modules.audit.service import Actor
from app.modules.tenancy.service import OwnerSpec, ProvisionRequest, provision_tenant
from tests.conftest import unique_slug

DEFAULT_PASSWORD = "correct-horse-battery-staple"


@dataclass
class TenantFixture:
    id: uuid.UUID
    slug: str
    name: str
    owner_email: str
    owner_password: str = DEFAULT_PASSWORD
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def host(self) -> str:
        return f"{self.slug}.localhost"


async def make_tenant(
    infra: Infra,
    *,
    plan: str = "free",
    name: str | None = None,
    type: str = "school",
    slug: str | None = None,
) -> TenantFixture:
    slug = slug or unique_slug()
    email = f"owner@{slug}.example.com"
    async with infra.db.uow() as uow:
        tenant = await provision_tenant(
            uow,
            ProvisionRequest(
                slug=slug,
                name=name or f"Institute {slug}",
                type=type,
                plan_code=plan,
                owner=OwnerSpec(
                    email=email,
                    full_name="Owner Person",
                    password_hash=await infra.passwords.hash(DEFAULT_PASSWORD),
                ),
            ),
            Actor.system("test"),
        )
    return TenantFixture(id=tenant.id, slug=slug, name=tenant.name, owner_email=email)


class Client:
    """httpx client bound to one host (= one origin), with CSRF handling like the SPA."""

    def __init__(self, app: Any, host: str, *, ip: str | None = None) -> None:
        # A distinct client IP per client keeps per-IP rate-limit buckets (shared in Redis) independent.
        ip = ip or f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250 + 1}"
        self.host = host
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(ip, 12345)),
            base_url=f"http://{host}",
            follow_redirects=False,
        )

    async def __aenter__(self) -> Client:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.http.aclose()

    def _csrf(self) -> str | None:
        for cookie in self.http.cookies.jar:
            if cookie.name in ("sc_csrf", "__Host-sc_csrf"):
                return cookie.value
        return None

    async def ensure_csrf(self) -> str:
        token = self._csrf()
        if token is None:
            await self.http.get("/api/v1/auth/csrf")
            token = self._csrf()
        assert token is not None
        return token

    async def get(self, url: str, **kw: Any) -> httpx.Response:
        return await self.http.get(url, **kw)

    async def _unsafe(self, method: str, url: str, **kw: Any) -> httpx.Response:
        headers = dict(kw.pop("headers", {}) or {})
        headers.setdefault("X-CSRF-Token", await self.ensure_csrf())
        return await self.http.request(method, url, headers=headers, **kw)

    async def post(self, url: str, **kw: Any) -> httpx.Response:
        return await self._unsafe("POST", url, **kw)

    async def put(self, url: str, **kw: Any) -> httpx.Response:
        return await self._unsafe("PUT", url, **kw)

    async def patch(self, url: str, **kw: Any) -> httpx.Response:
        return await self._unsafe("PATCH", url, **kw)

    async def delete(self, url: str, **kw: Any) -> httpx.Response:
        return await self._unsafe("DELETE", url, **kw)

    async def login(self, login_id: str, password: str = DEFAULT_PASSWORD) -> httpx.Response:
        r = await self.post("/api/v1/auth/login", json={"login_id": login_id, "password": password})
        assert r.status_code == 200, r.text
        return r

    def session_cookie(self) -> str | None:
        for cookie in self.http.cookies.jar:
            if cookie.name in ("sc_session", "__Host-sc_session"):
                return cookie.value
        return None


def totp_now(secret: str) -> str:
    return pyotp.TOTP(secret).now()


MAILPIT = "http://localhost:58025"


async def drain_jobs(infra: Infra, queues: list[str] | None = None) -> int:
    from app.core.jobs import Worker

    return await Worker(infra, queues or infra.settings.queues).drain()


async def mailpit_latest(to: str) -> dict[str, Any]:
    """Return the newest message sent to ``to`` (subject, text) from Mailpit's API."""
    import os

    base = os.environ.get("SCORECODE_TEST_MAILPIT_API", MAILPIT)
    async with httpx.AsyncClient(base_url=base, timeout=5) as client:
        found = (await client.get("/api/v1/search", params={"query": f'to:"{to}"', "limit": 1})).json()
        messages = found.get("messages") or []
        assert messages, f"no email to {to}"
        msg = (await client.get(f"/api/v1/message/{messages[0]['ID']}")).json()
    return {"subject": msg["Subject"], "text": msg["Text"], "html": msg.get("HTML", "")}


def link_token(text: str, param: str = "token") -> str:
    import re

    match = re.search(rf"[?&]{param}=([A-Za-z0-9_\-]+)", text)
    assert match, f"no {param} link in email"
    return match.group(1)


async def make_platform_admin(infra: Infra, role: str = "platform_admin") -> tuple[str, str, str]:
    from app.modules.platform.bootstrap import create_platform_user

    email = f"ops-{uuid.uuid4().hex[:8]}@ops.example.com"
    password = "platform-pass-12345"
    created = await create_platform_user(infra, email, "Ops Person", password, role)
    return email, password, created.totp_secret


async def platform_client(app: Any, infra: Infra, role: str = "platform_admin") -> Client:
    email, password, secret = await make_platform_admin(infra, role)
    c = Client(app, "admin.localhost", ip=f"192.0.2.{uuid.uuid4().int % 250}")
    r = await c.post(
        "/api/v1/platform/auth/login",
        json={"email": email, "password": password, "totp_code": totp_now(secret)},
    )
    assert r.status_code == 200, r.text
    return c


async def make_user(
    infra: Infra,
    tenant: TenantFixture,
    role: str,
    *,
    login_id: str | None = None,
    password: str = DEFAULT_PASSWORD,
) -> tuple[uuid.UUID, str]:
    """Create an active user with ``role`` directly (fixture shortcut; flows are tested elsewhere)."""
    from app.modules.identity.models import User, UserRole

    kind = "student" if role == "student" else "staff"
    login = login_id or (
        f"{role}-{uuid.uuid4().hex[:6]}@{tenant.slug}.example.com"
        if kind == "staff"
        else f"STU{uuid.uuid4().hex[:8].upper()}"
    )
    async with infra.db.uow(tenant.id) as uow:
        user = User(
            tenant_id=tenant.id,
            kind=kind,
            login_id=login,
            email=login if kind == "staff" else None,
            full_name=f"{role.title()} Person",
            password_hash=await infra.passwords.hash(password),
            status="active",
        )
        uow.session.add(user)
        await uow.flush()
        uow.session.add(UserRole(tenant_id=tenant.id, user_id=user.id, role=role))
    return user.id, login


async def client_as(app: Any, infra: Infra, tenant: TenantFixture, role: str) -> Client:
    c = Client(app, tenant.host)
    if role == "institution_owner":
        await c.login(tenant.owner_email)
    elif role != "anonymous":
        _, login = await make_user(infra, tenant, role)
        await c.login(login)
    return c


@dataclass
class Structure:
    session_id: uuid.UUID
    term_id: uuid.UUID
    department_id: uuid.UUID
    program_id: uuid.UUID
    cohort_id: uuid.UUID
    sibling_cohort_id: uuid.UUID  # same program and session as cohort_id
    course_id: uuid.UUID
    session_code: str
    cohort_code: str
    sibling_cohort_code: str


async def make_structure(infra: Infra, tenant: TenantFixture, *, current: bool = True) -> Structure:
    """One session (with a term), department, program, course and two sibling cohorts."""
    from datetime import date

    from app.modules.academics.models import AcademicSession, Cohort, Course, Department, Program, Term

    tag = uuid.uuid4().hex[:5].upper()
    async with infra.db.uow(tenant.id) as uow:
        sess = AcademicSession(
            tenant_id=tenant.id,
            code=f"S{tag}",
            name=f"Session {tag}",
            starts_on=date(2025, 7, 1),
            ends_on=date(2026, 6, 30),
            is_current=current,
        )
        dept = Department(tenant_id=tenant.id, code=f"D{tag}", name="Dept")
        uow.session.add_all([sess, dept])
        await uow.flush()
        term = Term(tenant_id=tenant.id, session_id=sess.id, code="T1", name="Term 1", sequence=1)
        prog = Program(tenant_id=tenant.id, code=f"P{tag}", name="Program", department_id=dept.id)
        course = Course(tenant_id=tenant.id, code=f"C{tag}", name="Course")
        uow.session.add_all([term, prog, course])
        await uow.flush()
        a = Cohort(
            tenant_id=tenant.id, code=f"A{tag}", name="Cohort A", program_id=prog.id, session_id=sess.id
        )
        b = Cohort(
            tenant_id=tenant.id, code=f"B{tag}", name="Cohort B", program_id=prog.id, session_id=sess.id
        )
        uow.session.add_all([a, b])
        await uow.flush()
        return Structure(
            session_id=sess.id,
            term_id=term.id,
            department_id=dept.id,
            program_id=prog.id,
            cohort_id=a.id,
            sibling_cohort_id=b.id,
            course_id=course.id,
            session_code=sess.code,
            cohort_code=a.code,
            sibling_cohort_code=b.code,
        )


async def make_student(
    infra: Infra,
    tenant: TenantFixture,
    *,
    enrollment_no: str | None = None,
    full_name: str = "Student Person",
    cohort_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Create an active student through the service (counts towards the limit, like the API)."""
    from app.modules.directory.service import StudentData, StudentService

    async with infra.db.uow(tenant.id) as uow:
        student = await StudentService(infra).create(
            uow,
            None,
            StudentData(
                enrollment_no=enrollment_no or f"E{uuid.uuid4().hex[:9].upper()}", full_name=full_name
            ),
            cohort_ids=[cohort_id] if cohort_id else [],
        )
        return student.id
