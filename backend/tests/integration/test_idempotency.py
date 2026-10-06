"""Idempotency keys (P2.9) and the per-session API rate limit (P3.7)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from sqlalchemy import text
from starlette.requests import Request

from app.core.errors import IdempotencyMismatch, ValidationFailed
from app.core.idempotency import idempotent
from app.modules.audit.service import Actor, record
from tests.helpers import Client, make_tenant

pytestmark = pytest.mark.integration


class Out(BaseModel):
    value: int


def _request(key: str | None, path: str = "/api/v1/exams/x/process") -> Request:
    headers = [(b"idempotency-key", key.encode())] if key else []
    return Request({"type": "http", "method": "POST", "path": path, "headers": headers, "query_string": b""})


async def test_replay_returns_stored_response_without_repeating_work(infra) -> None:
    t = await make_tenant(infra)
    calls = 0

    async def run(key: str, body: dict) -> object:
        nonlocal calls
        async with infra.db.uow(t.id) as uow:

            async def work() -> Out:
                nonlocal calls
                calls += 1
                await record(uow, Actor.system("test"), "test.idempotent_work")
                return Out(value=calls)

            return await idempotent(uow, _request(key), body, work)

    first = await run("key-12345678", {"a": 1})
    assert isinstance(first, Out) and first.value == 1
    replay = await run("key-12345678", {"a": 1})
    assert replay.status_code == 200 and replay.headers["idempotent-replayed"] == "true"
    assert calls == 1
    with pytest.raises(IdempotencyMismatch):
        await run("key-12345678", {"a": 2})
    with pytest.raises(ValidationFailed):
        await run("short", {"a": 1})
    async with infra.db.uow(t.id) as uow:
        n = (
            await uow.session.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = 'test.idempotent_work'")
            )
        ).scalar_one()
    assert n == 1


async def test_failed_work_releases_the_key(infra) -> None:
    t = await make_tenant(infra)

    async def boom() -> Out:
        raise RuntimeError("fails")

    with pytest.raises(RuntimeError):
        async with infra.db.uow(t.id) as uow:
            await idempotent(uow, _request("retry-key-1"), {}, boom)

    async def ok() -> Out:
        return Out(value=7)

    async with infra.db.uow(t.id) as uow:
        result = await idempotent(uow, _request("retry-key-1"), {}, ok)
    assert isinstance(result, Out) and result.value == 7


async def test_per_session_api_rate_limit(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        statuses = [
            (await c.get("/api/v1/me")).status_code for _ in range(infra.settings.api_session_burst + 80)
        ]
    assert statuses[0] == 200
    assert 429 in statuses
