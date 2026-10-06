"""Platform kernel guarantees (Phase 2): DB roles, RLS coverage and fail-closed behaviour, composite
foreign keys, audit atomicity, job queue semantics, cache degradation, default-deny routing."""

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from app.core.cache import CircuitBreaker, LocalCache, TieredCache
from app.core.jobs import JobContext, Worker, enqueue, registry
from app.modules.audit.service import Actor, record
from tests.conftest import PG_HOST, PG_PORT
from tests.helpers import make_tenant

pytestmark = pytest.mark.integration

APPEND_ONLY_TABLES = ("audit_logs",)


async def _connect(db: str, role: str, password: str) -> asyncpg.Connection:
    return await asyncpg.connect(host=PG_HOST, port=PG_PORT, user=role, password=password, database=db)


# ---- P2.1 roles ---------------------------------------------------------------------------------


async def test_each_role_connects_and_app_role_cannot_ddl(migrated_db: str) -> None:
    for role, pw in (
        ("scorecode_app", "app-dev-pw"),
        ("scorecode_platform", "platform-dev-pw"),
        ("scorecode_migrator", "migrator-dev-pw"),
    ):
        conn = await _connect(migrated_db, role, pw)
        assert await conn.fetchval("SELECT current_user") == role
        await conn.close()
    conn = await _connect(migrated_db, "scorecode_app", "app-dev-pw")
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("CREATE TABLE should_fail (id int)")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")
        assert await conn.fetchval("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user") is False
    finally:
        await conn.close()


# ---- P2.6 RLS coverage --------------------------------------------------------------------------


async def test_every_tenant_table_has_forced_rls_and_policy(migrated_db: str) -> None:
    conn = await _connect(migrated_db, "scorecode_migrator", "migrator-dev-pw")
    try:
        rows = await conn.fetch(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid AND p.polname = 'tenant_isolation') AS policies
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
             WHERE c.relkind IN ('r', 'p') AND NOT c.relispartition
               AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped)
            """
        )
    finally:
        await conn.close()
    exempt = {"signup_requests"}  # pre-tenant staging table: tenant_id is set only after verification
    offenders = [
        r["relname"]
        for r in rows
        if r["relname"] not in exempt
        and not (r["relrowsecurity"] and r["relforcerowsecurity"] and r["policies"] == 1)
    ]
    assert rows, "expected tenant tables"
    assert offenders == [], f"tenant tables without forced RLS + tenant_isolation policy: {offenders}"


async def test_app_role_has_no_update_or_delete_on_append_only_tables(migrated_db: str) -> None:
    conn = await _connect(migrated_db, "scorecode_migrator", "migrator-dev-pw")
    try:
        for table in APPEND_ONLY_TABLES:
            for priv in ("UPDATE", "DELETE", "TRUNCATE"):
                assert (
                    await conn.fetchval("SELECT has_table_privilege('scorecode_app', $1, $2)", table, priv)
                    is False
                )
        # Partitions are never directly accessible to the runtime role.
        parts = await conn.fetch(
            "SELECT relname FROM pg_class WHERE relispartition AND relname LIKE 'audit_logs_p%'"
        )
        assert parts
        for p in parts:
            assert (
                await conn.fetchval("SELECT has_table_privilege('scorecode_app', $1, 'SELECT')", p["relname"])
                is False
            )
    finally:
        await conn.close()


async def test_query_without_tenant_context_fails_closed(infra) -> None:
    await make_tenant(infra)
    async with infra.db.uow() as uow:
        with pytest.raises(DBAPIError):
            await uow.session.execute(text("SELECT count(*) FROM users"))


async def test_tenant_context_sees_only_own_rows_and_cannot_write_others(infra) -> None:
    a = await make_tenant(infra)
    b = await make_tenant(infra)
    async with infra.db.uow(a.id) as uow:
        # Even an explicit predicate for B returns nothing: RLS filters before the WHERE matters.
        assert (
            await uow.session.execute(text("SELECT count(*) FROM users WHERE tenant_id = :b"), {"b": b.id})
        ).scalar_one() == 0
        assert (await uow.session.execute(text("SELECT count(*) FROM users"))).scalar_one() == 1
        assert (await uow.session.execute(text("SELECT count(*) FROM tenants"))).scalar_one() == 1
    with pytest.raises(DBAPIError):
        async with infra.db.uow(a.id) as uow:
            await uow.session.execute(
                text(
                    "INSERT INTO users (id, tenant_id, kind, login_id, full_name, status) "
                    "VALUES (:id, :b, 'staff', 'x@y.z', 'Intruder', 'active')"
                ),
                {"id": uuid.uuid4(), "b": b.id},
            )


async def test_set_config_is_transaction_local(infra) -> None:
    a = await make_tenant(infra)
    async with infra.db.uow(a.id) as uow:
        assert (
            await uow.session.execute(text("SELECT current_setting('app.tenant_id')"))
        ).scalar_one() == str(a.id)
    # A new transaction (possibly on the same pooled connection) has no tenant context.
    async with infra.db.uow() as uow:
        value = (
            await uow.session.execute(text("SELECT current_setting('app.tenant_id', true)"))
        ).scalar_one()
        assert value in (None, "")


# ---- P2.7 composite FKs -------------------------------------------------------------------------


async def test_composite_fk_blocks_cross_tenant_reference(infra) -> None:
    """A buggy service running in tenant A's context tries to attach tenant B's user: the composite
    foreign key (tenant_id, user_id) → users(tenant_id, id) rejects it at the schema level."""
    a = await make_tenant(infra)
    b = await make_tenant(infra)
    async with infra.db.uow(b.id) as uow:
        b_user = (await uow.session.execute(text("SELECT id FROM users"))).scalar_one()
    with pytest.raises(IntegrityError, match="fk_user_roles__tenant_id_user_id__users"):
        async with infra.db.uow(a.id) as uow:
            await uow.session.execute(
                text("INSERT INTO user_roles (tenant_id, user_id, role) VALUES (:a, :u, 'faculty')"),
                {"a": a.id, "u": b_user},
            )


# ---- P2.8 audit ---------------------------------------------------------------------------------


async def test_rolled_back_change_leaves_no_audit_row(infra) -> None:
    t = await make_tenant(infra)

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        async with infra.db.uow(t.id) as uow:
            await record(uow, Actor.system("test"), "test.should_not_persist")
            await uow.flush()
            raise Boom
    async with infra.db.uow(t.id) as uow:
        await record(uow, Actor.system("test"), "test.persisted")
    async with infra.db.uow(t.id) as uow:
        actions = (
            (await uow.session.execute(text("SELECT action FROM audit_logs WHERE action LIKE 'test.%'")))
            .scalars()
            .all()
        )
    assert actions == ["test.persisted"]


async def test_app_role_cannot_modify_audit_rows(infra) -> None:
    t = await make_tenant(infra)
    for stmt in ("UPDATE audit_logs SET action = 'tampered'", "DELETE FROM audit_logs"):
        with pytest.raises(ProgrammingError):
            async with infra.db.uow(t.id) as uow:
                await uow.session.execute(text(stmt))


# ---- P1.7 / P2 job queue ------------------------------------------------------------------------

_calls: list[str] = []


@registry.register("test.echo", queue="test")
async def _echo(ctx: JobContext) -> dict[str, str]:
    _calls.append(ctx.job.payload["value"])
    return {"echo": ctx.job.payload["value"]}


@registry.register("test.flaky", queue="test", max_attempts=2)
async def _flaky(ctx: JobContext) -> None:
    raise RuntimeError("transient failure")


async def test_job_enqueued_only_if_transaction_commits(infra) -> None:
    t = await make_tenant(infra)
    _calls.clear()

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        async with infra.db.uow(t.id) as uow:
            await enqueue(uow, "test.echo", {"value": "rolled-back"})
            raise Boom
    async with infra.db.uow(t.id) as uow:
        job_id = await enqueue(uow, "test.echo", {"value": "committed"})
    worker = Worker(infra, ["test"])
    assert await worker.drain() == 1
    assert _calls == ["committed"]
    async with infra.db.uow(t.id) as uow:
        row = (
            await uow.session.execute(text("SELECT status, result FROM jobs WHERE id = :id"), {"id": job_id})
        ).one()
    assert row.status == "succeeded"
    assert row.result == {"echo": "committed"}


async def test_failed_job_retries_then_dead_letters(infra) -> None:
    t = await make_tenant(infra)
    async with infra.db.uow(t.id) as uow:
        job_id = await enqueue(uow, "test.flaky", {})
    worker = Worker(infra, ["test"])
    await worker.drain()
    async with infra.db.uow(t.id) as uow:
        row = (
            await uow.session.execute(
                text("SELECT status, attempts FROM jobs WHERE id = :id"), {"id": job_id}
            )
        ).one()
    assert row.status == "queued" and row.attempts == 1  # scheduled for retry with backoff
    await worker.drain(include_future=True)
    async with infra.db.uow(t.id) as uow:
        row = (
            await uow.session.execute(
                text("SELECT status, attempts, last_error FROM jobs WHERE id = :id"), {"id": job_id}
            )
        ).one()
    assert row.status == "dead" and row.attempts == 2
    assert "transient failure" in row.last_error


async def test_concurrent_workers_never_run_a_job_twice(infra) -> None:
    t = await make_tenant(infra)
    _calls.clear()
    async with infra.db.uow(t.id) as uow:
        for i in range(30):
            await enqueue(uow, "test.echo", {"value": f"v{i}"})
    workers = [Worker(infra, ["test"], tenant_concurrency_cap=100) for _ in range(4)]
    await asyncio.gather(*(w.drain() for w in workers))
    assert sorted(_calls) == sorted(f"v{i}" for i in range(30))


async def test_reaper_requeues_jobs_from_dead_workers(infra) -> None:
    t = await make_tenant(infra)
    async with infra.db.uow(t.id) as uow:
        job_id = await enqueue(uow, "test.echo", {"value": "reaped"})
    async with infra.db.uow() as uow:
        await uow.session.execute(text("SELECT * FROM jobs_claim(ARRAY['test'], 'ghost-worker', 1, 1, 10)"))
    async with infra.db.uow(t.id) as uow:
        await uow.session.execute(
            text("UPDATE jobs SET locked_until = now() - interval '1 second' WHERE id = :id"), {"id": job_id}
        )
    worker = Worker(infra, ["test"])
    assert await worker.reap() >= 1
    _calls.clear()
    await worker.drain()
    assert "reaped" in _calls


async def test_runtime_role_cannot_read_other_tenants_jobs(infra) -> None:
    a = await make_tenant(infra)
    b = await make_tenant(infra)
    async with infra.db.uow(b.id) as uow:
        b_job = await enqueue(uow, "test.echo", {"value": "b-secret"})
    async with infra.db.uow(a.id) as uow:
        assert (
            await uow.session.execute(text("SELECT count(*) FROM jobs WHERE id = :id"), {"id": b_job})
        ).scalar_one() == 0
    await Worker(infra, ["test"]).drain()


# ---- P2.10 cache degradation --------------------------------------------------------------------


async def test_cache_falls_back_to_local_when_redis_is_down() -> None:
    import redis.asyncio as aioredis

    dead = aioredis.from_url("redis://127.0.0.1:1/0", socket_timeout=0.05, socket_connect_timeout=0.05)
    cache = TieredCache(
        dead, LocalCache(), local_ttl_s=30, breaker=CircuitBreaker(failure_threshold=2, cooldown_s=60)
    )
    await cache.set("k", {"v": 1}, 60)
    assert await cache.get("k") == {"v": 1}  # served from local tier
    assert await cache.get("missing") is None
    await cache.get("missing-2")
    assert cache.breaker.is_open  # stop waiting on Redis timeouts
    assert await cache.incr("counter", 60) == 1
    assert await cache.incr("counter", 60) == 2
    await dead.aclose()


async def test_rate_limiter_degrades_to_local_buckets_when_redis_is_down() -> None:
    import redis.asyncio as aioredis

    from app.core.errors import RateLimited
    from app.core.ratelimit import Bucket, RateLimiter

    dead = aioredis.from_url("redis://127.0.0.1:1/0", socket_timeout=0.05, socket_connect_timeout=0.05)
    limiter = RateLimiter(TieredCache(dead, LocalCache()))
    bucket = Bucket("t", rate_per_s=0.001, burst=3)
    for _ in range(3):
        await limiter.hit(bucket, "ip")
    with pytest.raises(RateLimited):
        await limiter.hit(bucket, "ip")
    await dead.aclose()


async def test_api_keeps_serving_when_redis_is_unreachable(app, infra) -> None:
    """Swap the Redis client for an unreachable one: requests must still succeed (degraded)."""
    import redis.asyncio as aioredis

    from tests.helpers import Client

    t = await make_tenant(infra)
    original = infra.cache.redis
    dead = aioredis.from_url("redis://127.0.0.1:1/0", socket_timeout=0.05, socket_connect_timeout=0.05)
    infra.cache.redis = dead
    try:
        async with Client(app, t.host) as c:
            await c.login(t.owner_email)
            assert (await c.get("/api/v1/me")).status_code == 200
            assert (await c.get("/api/v1/tenant/config")).status_code == 200
    finally:
        infra.cache.redis = original
        infra.cache.breaker = CircuitBreaker()
        await dead.aclose()


# ---- default deny -------------------------------------------------------------------------------


def _policies(dependant, attr: str) -> list[str]:  # type: ignore[no-untyped-def]
    found: list[str] = []
    for dep in dependant.dependencies:
        if dep.call is not None and hasattr(dep.call, attr):
            found.append(getattr(dep.call, attr))
        found.extend(_policies(dep, attr))
    return found


def test_every_route_declares_an_access_policy(app) -> None:
    import fastapi.routing as fr

    from app.core.http import ACCESS_POLICY_ATTR

    exempt = {"/livez", "/readyz", "/metrics", "/api/openapi.json", "/api/docs", "/docs/oauth2-redirect"}
    missing = []
    for ctx in fr.iter_route_contexts(app.routes):
        route = ctx.route
        if not isinstance(route, fr.APIRoute) or route.path in exempt:
            continue
        if not _policies(route.dependant, ACCESS_POLICY_ATTR):
            missing.append(f"{sorted(route.methods)} {route.path}")
    assert missing == [], f"routes without require()/require_platform()/public(): {missing}"
