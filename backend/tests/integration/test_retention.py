"""The retention purge (docs/10 §12, ASVS 8.3.4; migrations 0016 and 0020): old operational rows go, in
every tenant,
under each tenant's own RLS context. What's recent stays, and the record (audit, results) is never
touched. The runtime role still can't delete append-only rows itself."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.jobs import Worker, enqueue
from tests.helpers import Client, drain_jobs, make_tenant
from tests.integration.test_imports import _csv, _upload

pytestmark = pytest.mark.integration


async def _exists(s, sql: str, **params: object) -> bool:  # type: ignore[no-untyped-def]
    return bool((await s.execute(text(f"SELECT EXISTS ({sql})"), params)).scalar_one())


async def _ageing_rows(app, infra, t) -> dict[str, uuid.UUID]:
    """One old and one recent row of each kind the purge handles, in tenant ``t``."""
    ids: dict[str, uuid.UUID] = {}
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        old_import = (await _upload(c, _csv("enrollment_no,full_name", "R001,Old Row"))).json()["id"]
        new_import = (await _upload(c, _csv("enrollment_no,full_name", "R002,New Row"), name="b.csv")).json()[
            "id"
        ]
    await drain_jobs(infra, ["imports"])
    async with infra.db.uow(t.id) as uow:
        s = uow.session
        user = (await s.execute(text("SELECT id FROM users LIMIT 1"))).scalar_one()
        for age, key in ((timedelta(days=400), "old"), (timedelta(days=1), "new")):
            n = (
                await s.execute(
                    text(
                        "INSERT INTO notifications (id, tenant_id, user_id, kind, title, body, created_at)"
                        " VALUES (gen_random_uuid(), :t, :u, 'result_published', 'Old news', 'body', now() - CAST(:age AS interval))"
                        " RETURNING id"
                    ),
                    {"t": t.id, "u": user, "age": age},
                )
            ).scalar_one()
            await s.execute(
                text(
                    "INSERT INTO notification_deliveries (id, tenant_id, notification_id, user_id, status, sent_at, created_at)"
                    " VALUES (gen_random_uuid(), :t, :n, :u, 'sent', now() - CAST(:age AS interval), now() - CAST(:age AS interval))"
                ),
                {"t": t.id, "n": n, "u": user, "age": age},
            )
            ids[f"notification_{key}"] = n
            ids[f"inapp_{key}"] = (  # in-app only: no delivery, so only its age decides
                await s.execute(
                    text(
                        "INSERT INTO notifications (id, tenant_id, user_id, kind, title, body, created_at)"
                        " VALUES (gen_random_uuid(), :t, :u, 'result_published', 'In app', 'body',"
                        " now() - CAST(:age AS interval)) RETURNING id"
                    ),
                    {"t": t.id, "u": user, "age": age},
                )
            ).scalar_one()
        await s.execute(
            text(
                "UPDATE sessions SET expires_at = now() - interval '400 days', absolute_expires_at = now() - interval '400 days'"
            )
        )
        await s.execute(
            text(
                "UPDATE import_jobs SET status = 'committed', updated_at = now() - interval '40 days' WHERE id = :i"
            ),
            {"i": old_import},
        )
        ids["import_old"], ids["import_new"] = uuid.UUID(old_import), uuid.UUID(new_import)
        ids["job_old"] = await enqueue(uow, "test.stats", {})
        ids["job_new"] = await enqueue(uow, "test.stats", {})
        ids["job_month"] = await enqueue(uow, "test.stats", {})
    await Worker(infra, ["test-stats"]).drain()
    async with infra.db.uow(t.id) as uow:
        await uow.session.execute(
            text("UPDATE jobs SET finished_at = now() - interval '400 days' WHERE id = :j"),
            {"j": ids["job_old"]},
        )
        # A record of processing from last month is kept for a year now (DPDP Rules, rule 8(3)).
        await uow.session.execute(
            text("UPDATE jobs SET finished_at = now() - interval '40 days' WHERE id = :j"),
            {"j": ids["job_month"]},
        )
    return ids


async def test_the_purge_removes_old_operational_rows_in_every_tenant_and_keeps_the_rest(app, infra) -> None:
    import tests.integration.test_kernel  # noqa: F401  (registers the test.stats job kind)

    a, b = await make_tenant(infra), await make_tenant(infra)
    rows = {t.id: await _ageing_rows(app, infra, t) for t in (a, b)}
    async with infra.db.uow(a.id) as uow:
        audit_before = (await uow.session.execute(text("SELECT count(*) FROM audit_logs"))).scalar_one()

    counts = await Worker(infra, ["test-stats"]).maintenance()
    assert counts["tenants"] >= 2 and counts["sessions"] >= 2 and counts["jobs"] >= 2
    assert (
        counts["notifications"] >= 2 and counts["notification_deliveries"] >= 2 and counts["import_rows"] >= 2
    )

    for t in (a, b):
        ids = rows[t.id]
        async with infra.db.uow(t.id) as uow:
            s = uow.session

            assert not await _exists(
                s, "SELECT 1 FROM notifications WHERE id = :i", i=ids["notification_old"]
            )
            assert await _exists(s, "SELECT 1 FROM notifications WHERE id = :i", i=ids["notification_new"])
            assert not await _exists(s, "SELECT 1 FROM notifications WHERE id = :i", i=ids["inapp_old"])
            assert await _exists(s, "SELECT 1 FROM notifications WHERE id = :i", i=ids["inapp_new"])
            assert not await _exists(s, "SELECT 1 FROM jobs WHERE id = :i", i=ids["job_old"])
            assert await _exists(s, "SELECT 1 FROM jobs WHERE id = :i", i=ids["job_new"])
            assert await _exists(s, "SELECT 1 FROM jobs WHERE id = :i", i=ids["job_month"])
            assert not await _exists(
                s, "SELECT 1 FROM import_rows WHERE import_job_id = :i", i=ids["import_old"]
            )
            assert await _exists(s, "SELECT 1 FROM import_rows WHERE import_job_id = :i", i=ids["import_new"])
            assert await _exists(
                s, "SELECT 1 FROM import_jobs WHERE id = :i", i=ids["import_old"]
            )  # summary kept
            assert not await _exists(s, "SELECT 1 FROM sessions")
    async with infra.db.uow(a.id) as uow:
        assert (
            await uow.session.execute(text("SELECT count(*) FROM audit_logs"))
        ).scalar_one() == audit_before

    # Uploaded spreadsheets follow their staging rows: the stored object goes, the row stays, marked.
    assert counts["import_files"] >= 2
    for t in (a, b):
        async with infra.db.uow(t.id) as uow:
            files = {
                r.import_id: r
                for r in (
                    await uow.session.execute(
                        text(
                            "SELECT j.id AS import_id, f.object_key, f.purged_at FROM import_jobs j"
                            " JOIN files f ON f.id = j.file_id WHERE j.id IN (:o, :n)"
                        ),
                        {"o": rows[t.id]["import_old"], "n": rows[t.id]["import_new"]},
                    )
                ).all()
            }
        old, new = files[rows[t.id]["import_old"]], files[rows[t.id]["import_new"]]
        assert old.purged_at is not None and new.purged_at is None
        with pytest.raises(Exception):  # noqa: B017 - the storage client's own not-found error
            await infra.storage.get(old.object_key)
        assert await infra.storage.get(new.object_key)

    again = await Worker(infra, ["test-stats"]).maintenance()  # idempotent: nothing left to remove here
    assert again["notifications"] == 0 and again["import_rows"] == 0 and again["import_files"] == 0


async def test_the_runtime_role_still_cannot_delete_notifications(infra) -> None:
    t = await make_tenant(infra)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with infra.db.uow(t.id) as uow:
            await uow.session.execute(text("DELETE FROM notifications"))
