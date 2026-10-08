"""The student read cache (P14.3): repeat reads skip the database, withdrawals still apply at once in the
process that made them, and keys never mix tenants or students."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from tests.helpers import Client
from tests.integration.test_publishing import _approved, _as_student, _logins, _publish, _pubs
from tests.integration.test_results import _reauth

pytestmark = pytest.mark.integration
HOT_TABLES = re.compile(r"\b(published_results|publications|students|exam_statistics|tenant_settings)\b")


@contextmanager
def statements(infra) -> Iterator[list[str]]:  # type: ignore[no-untyped-def]
    seen: list[str] = []

    def listener(conn, cursor, statement, params, context, executemany):  # type: ignore[no-untyped-def]
        seen.append(statement)

    engine = infra.db.app_engine.sync_engine
    event.listen(engine, "before_cursor_execute", listener)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", listener)


async def test_repeat_reads_come_from_the_cache_and_withdrawals_apply_at_once(app, infra) -> None:
    e = await _approved(app, infra)
    await _logins(app, e, "A001", "A002")
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        pub = (await _publish(c, e)).json()
    async with await _as_student(app, e, "A001") as a1:
        first = (await a1.get("/api/v1/me/results/latest")).json()
        await a1.get(f"/api/v1/me/results/{pub['id']}/stats")
        with statements(infra) as seen:
            again = (await a1.get("/api/v1/me/results/latest")).json()
            stats = await a1.get(f"/api/v1/me/results/{pub['id']}/stats")
            listed = await a1.get("/api/v1/me/results")
        assert again == first and stats.status_code == 200 and listed.status_code == 200
        assert [s for s in seen if HOT_TABLES.search(s)] == []  # nothing re-read from the database
    # A different student, same publication: their own snapshot, never A001's.
    async with await _as_student(app, e, "A002") as a2:
        theirs = (await a2.get("/api/v1/me/results/latest")).json()
        assert theirs["payload"]["student"]["enrollment_no"] == "A002"

    # Every key is scoped to the tenant (and student keys to the student).
    keys = [k for k in infra.cache.local._data if ":reads:" in k]
    assert keys and all(k.startswith(f"t:{e.x.t.id}:reads:") for k in keys if str(e.x.t.id) in k)
    assert all(k.split(":")[1] for k in keys)

    # Withdrawn: the process that withdrew forgets the live list after commit, so it's gone at once.
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        await _reauth(c)
        r = await c.post(f"{_pubs(e)}/{pub['id']}/withdraw", json={"reason": "Wrong exam picked"})
        assert r.status_code == 200
    async with await _as_student(app, e, "A001") as a1:
        assert (await a1.get("/api/v1/me/results/latest")).json() is None
        assert (await a1.get(f"/api/v1/me/results/{pub['id']}")).status_code == 404


async def test_with_the_cache_off_every_read_goes_to_the_database(migrated_db: str) -> None:
    from app.core.container import Infra
    from app.main import create_app
    from tests.conftest import make_settings

    settings = make_settings(student_read_cache=False, redis_url=None)
    infra = Infra.build(settings, app_name="scorecode-test-no-read-cache")
    try:
        app = create_app(settings, infra)
        e = await _approved(app, infra)
        await _logins(app, e, "A001")
        async with Client(app, e.x.t.host) as c:
            await c.login(e.x.t.owner_email)
            await _publish(c, e)
        async with await _as_student(app, e, "A001") as a1:
            await a1.get("/api/v1/me/results/latest")
            with statements(infra) as seen:
                await a1.get("/api/v1/me/results/latest")
        assert any("published_results" in s for s in seen)  # the "before" of the before/after
    finally:
        await infra.close()
