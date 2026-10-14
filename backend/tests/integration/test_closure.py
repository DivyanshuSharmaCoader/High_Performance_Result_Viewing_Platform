"""Closing an account and erasing an institution's data (P18.14; migration 0021).

Two approvals (the owner's request, then ScoreCode staff after 30 days), then the worker erases: every
tenant row goes, the stored files go, and another institution is untouched. Kept: the tombstone, the
subscription and trial records, the platform audit log.
"""

from __future__ import annotations

import asyncpg
import pytest
from sqlalchemy import text

from app.core.jobs import Worker
from app.models_registry import metadata
from tests.conftest import PG_HOST, PG_PORT, TEST_DB
from tests.helpers import Client, client_as, platform_client
from tests.integration.test_publishing import _approved, _publish
from tests.integration.test_results import _reauth

pytestmark = pytest.mark.integration

URL = "/api/v1/admin/closure"
KEPT = {"tenant_subscriptions", "tenant_trials"}


async def _rows(infra, tenant_id) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Rows per tenant table for one tenant, read as the schema owner. The WHERE matters: a few tables
    let the owner see every tenant (definer policies on jobs and verification_records; signup_requests
    has no RLS), so the RLS context alone would count other institutions' rows."""
    conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user="scorecode_migrator", password="migrator-dev-pw", database=TEST_DB
    )
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            return {
                name: await conn.fetchval(f"SELECT count(*) FROM {name} WHERE tenant_id = $1", tenant_id)
                for name, table in metadata.tables.items()
                if "tenant_id" in table.c
            }
    finally:
        await conn.close()


async def test_the_owner_asks_staff_approve_after_30_days_and_everything_is_erased(app, infra) -> None:
    e = await _approved(app, infra)
    other = await _approved(app, infra)
    t = e.x.t
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        await _publish(c, e)  # marksheets, verification codes, notifications: all of it must go
    await Worker(infra, ["pdf", "notifications"]).drain()
    async with infra.db.uow(t.id) as uow:
        keys = (await uow.session.execute(text("SELECT object_key FROM files"))).scalars().all()
    assert keys, "the test needs stored files"
    other_before = await _rows(infra, other.x.t.id)

    async with await client_as(app, infra, t, "institution_admin") as admin:
        assert (await admin.post(URL, json={"reason": "moving on", "confirm": t.slug})).status_code == 403
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        r = await c.post(URL, json={"reason": "We are moving to another system", "confirm": "wrong"})
        assert r.status_code == 422 and r.json()["field"] == "confirm"
        r = await c.post(URL, json={"reason": "We are moving to another system", "confirm": t.slug})
        assert r.status_code == 201, r.text
        assert r.json()["requested"] and r.json()["delete_after"]
        assert (await c.post(URL, json={"reason": "again", "confirm": t.slug})).status_code == 409
        assert (await c.get("/api/v1/me")).status_code == 200  # everything keeps working meanwhile
        assert (await c.post("/api/v1/admin/exports")).status_code == 202  # and the data can be exported

    async with await platform_client(app, infra) as console:
        r = await console.post(
            f"/api/v1/platform/tenants/{t.id}/erase", json={"confirm": t.slug, "reason": "Owner asked"}
        )
        assert r.status_code == 409 and "change its mind until" in r.json()["detail"]  # 30 days not over
        detail = (await console.get(f"/api/v1/platform/tenants/{t.id}")).json()
        assert detail["closure"]["erasable"] is False

    async with infra.db.uow(t.id) as uow:
        await uow.session.execute(
            text("UPDATE tenant_settings SET closure_delete_after = now() - interval '1 minute'")
        )
    async with await platform_client(app, infra) as console:
        r = await console.post(
            f"/api/v1/platform/tenants/{t.id}/erase", json={"confirm": "nope", "reason": "x y z"}
        )
        assert r.status_code == 422
        r = await console.post(
            f"/api/v1/platform/tenants/{t.id}/erase", json={"confirm": t.slug, "reason": "Owner asked"}
        )
        assert r.status_code == 200, r.text
    async with Client(app, t.host) as c:
        r = await c.get("/api/v1/tenant/config")
        assert r.status_code == 403 and r.json()["code"] == "tenant-unavailable"  # offline from approval

    counts = await Worker(infra, ["maintenance"]).maintenance()
    assert counts["tenants_erased"] == 1

    after = await _rows(infra, t.id)
    assert {k: v for k, v in after.items() if v and k not in KEPT} == {}, "rows left behind"
    for key in keys:
        with pytest.raises(Exception):  # noqa: B017 - the storage client's not-found error
            await infra.storage.get(key)
    assert await _rows(infra, other.x.t.id) == other_before  # the other institution is untouched
    async with infra.db.platform_uow() as uow:
        status = (
            await uow.session.execute(text("SELECT status FROM tenants WHERE id = :t"), {"t": t.id})
        ).scalar_one()
        assert status == "closed"
        erased = (
            await uow.session.execute(
                text(
                    "SELECT after FROM platform_audit_logs WHERE action = 'tenant.erased' AND target_tenant_id = :t"
                ),
                {"t": t.id},
            )
        ).scalar_one()
        assert erased["rows"] > 0 and erased["files"] >= len(keys)
    assert (await Worker(infra, ["maintenance"]).maintenance())["tenants_erased"] == 0  # once only


async def test_the_owner_can_cancel_and_nothing_is_erased(app, infra) -> None:
    e = await _approved(app, infra)
    t = e.x.t
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        async with infra.db.uow(t.id) as uow:
            await uow.session.execute(
                text("UPDATE sessions SET reauthenticated_at = now() - interval '1 hour'")
            )
        r = await c.post(URL, json={"reason": "closing", "confirm": t.slug})
        assert r.status_code == 401 and r.json()["code"] == "reauth-required"
        await _reauth(c)
        assert (await c.post(URL, json={"reason": "closing", "confirm": t.slug})).status_code == 201
        r = await c.delete(URL)
        assert r.status_code == 200 and r.json()["requested"] is False
        audit = (await c.get("/api/v1/admin/audit-logs", params={"action": "tenant.closure"})).json()["items"]
        assert {a["action"] for a in audit} == {"tenant.closure_requested", "tenant.closure_cancelled"}
    async with await platform_client(app, infra) as console:
        r = await console.post(
            f"/api/v1/platform/tenants/{t.id}/erase", json={"confirm": t.slug, "reason": "x y z"}
        )
        assert r.status_code == 409 and "hasn't asked" in r.json()["detail"]


async def test_the_database_refuses_an_erasure_without_both_approvals(infra) -> None:
    from tests.helpers import make_tenant

    t = await make_tenant(infra)
    for slug in (t.slug, "someone-else"):
        with pytest.raises(Exception, match=r"approval|does not match"):
            async with infra.db.uow() as uow:
                await uow.session.execute(text("SELECT ops_erase_tenant(:t, :s)"), {"t": t.id, "s": slug})
    async with infra.db.platform_uow() as uow:
        await uow.session.execute(text("UPDATE tenants SET status = 'closing' WHERE id = :t"), {"t": t.id})
    with pytest.raises(Exception, match=r"30 days|not asked"):
        async with infra.db.uow() as uow:
            await uow.session.execute(text("SELECT ops_erase_tenant(:t, :s)"), {"t": t.id, "s": t.slug})
