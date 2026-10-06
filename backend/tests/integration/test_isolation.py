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
from tests.helpers import Client, TenantFixture, make_tenant, make_user
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


PROVIDERS: dict[str, Provider] = {
    "user_id": _staff_user,
    "job_id": _job,
    "token": _invite_token,
}

# Bodies that pass validation so the request reaches the resource lookup.
SAMPLE_BODIES: dict[tuple[str, str], Any] = {
    ("PUT", "/api/v1/admin/staff/{user_id}/role"): {"role": "institution_admin"},
    ("PUT", "/api/v1/admin/staff/{user_id}/status"): {"disabled": True},
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
    return audit, users, roles, jobs


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
