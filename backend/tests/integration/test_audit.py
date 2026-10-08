"""The audit-log viewer's filters (P13.4): kind of activity, person, record and dates, combined."""

from __future__ import annotations

import asyncio

import pytest

from app.core.clock import utcnow
from tests.helpers import Client, make_tenant, make_user

pytestmark = pytest.mark.integration


async def _rename(c: Client, name: str) -> None:
    current = (await c.get("/api/v1/admin/settings")).json()
    r = await c.put("/api/v1/admin/settings", json={"version": current["version"], "official_name": name})
    assert r.status_code == 200, r.text


async def test_filters_combine_by_activity_person_record_and_date(app, infra) -> None:
    t = await make_tenant(infra)
    admin_id, admin_login = await make_user(infra, t, "institution_admin")
    async with Client(app, t.host) as owner:
        await owner.login(t.owner_email)
        await _rename(owner, "Renamed Institute")
    await asyncio.sleep(0.6)  # (the database and this process may disagree by a few milliseconds)
    between = utcnow().isoformat()
    await asyncio.sleep(0.6)
    async with Client(app, t.host) as admin:
        await admin.login(admin_login)
        await _rename(admin, "Renamed Again")
    async with Client(app, t.host) as owner:
        await owner.login(t.owner_email)

        async def actions(**params: str) -> list[tuple[str, str | None]]:
            r = await owner.get("/api/v1/admin/audit-logs", params=params)
            assert r.status_code == 200, r.text
            return [
                (i["action"], i["after"].get("official_name") if i["after"] else None)
                for i in r.json()["items"]
            ]

        assert await actions(action="settings.") == [
            ("settings.updated", "Renamed Again"),
            ("settings.updated", "Renamed Institute"),
        ]
        assert await actions(action="settings.", actor_id=str(admin_id)) == [
            ("settings.updated", "Renamed Again")
        ]
        assert await actions(action="settings.", since=between) == [("settings.updated", "Renamed Again")]
        assert await actions(action="settings.", until=between) == [("settings.updated", "Renamed Institute")]
        assert await actions(action="settings.", entity_id=str(t.id)) == await actions(action="settings.")
        assert await actions(action="nothing.") == []
        bad = await owner.get("/api/v1/admin/audit-logs", params={"actor_id": "not-a-uuid"})
        assert bad.status_code == 422
    # Faculty don't see the institution's audit log.
    _, faculty = await make_user(infra, t, "faculty")
    async with Client(app, t.host) as f:
        await f.login(faculty)
        assert (await f.get("/api/v1/admin/audit-logs")).status_code == 403
