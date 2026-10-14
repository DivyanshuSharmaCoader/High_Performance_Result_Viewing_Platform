"""The email provider's daily cap (migration 0022): result notices stop short of a reserve and wait for the
budget; account emails may use the reserve; notices that would arrive days late are skipped, not sent.

Uses the approved exam from test_results (A001, A002, ...).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import asyncpg
import pytest
from sqlalchemy import text

from app.core.clock import utcnow
from app.modules.notifications import budget
from app.modules.notifications.service import Notifier
from tests.conftest import PG_HOST, PG_PORT, TEST_DB
from tests.helpers import Client
from tests.integration.test_notifications import _deliveries, _with_email
from tests.integration.test_publishing import _approved, _logins, _publish

pytestmark = pytest.mark.integration


async def _clear_budget() -> None:
    conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user="scorecode_migrator", password="migrator-dev-pw", database=TEST_DB
    )
    try:
        await conn.execute("DELETE FROM mail_sends")
    finally:
        await conn.close()


async def test_the_budget_keeps_a_reserve_for_account_emails(infra, monkeypatch) -> None:
    await _clear_budget()
    monkeypatch.setattr(infra.settings, "mail_daily_limit", 3)
    monkeypatch.setattr(infra.settings, "mail_daily_reserve", 1)
    assert await budget.take(infra, bulk=True) is None
    assert await budget.take(infra, bulk=True) is None
    later = await budget.take(infra, bulk=True)  # bulk stops one short of the limit
    assert later is not None and timedelta(hours=23) < later - utcnow() <= timedelta(hours=24)
    assert await budget.take(infra, bulk=False) is None  # the reserve, for a reset or an invitation
    assert await budget.take(infra, bulk=False) is not None  # and then nothing more today
    monkeypatch.setattr(infra.settings, "mail_daily_limit", 0)
    assert await budget.take(infra, bulk=True) is None  # 0: no budget configured
    await _clear_budget()


async def test_result_notices_wait_for_the_budget_then_give_up_after_the_delay(
    app, infra, monkeypatch
) -> None:
    await _clear_budget()
    e = await _approved(app, infra)
    await _logins(app, e, "A001", "A002")
    await _with_email(infra, e, "A001")
    await _with_email(infra, e, "A002")
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        pub = (await _publish(c, e)).json()
    monkeypatch.setattr(infra.settings, "mail_daily_limit", 2)
    monkeypatch.setattr(infra.settings, "mail_daily_reserve", 1)
    notifier = Notifier(infra)
    await notifier.publication_live(e.x.t.id, uuid.UUID(pub["id"]))
    async with infra.db.uow(e.x.t.id) as uow:
        ids = list(
            (await uow.session.execute(text("SELECT id FROM notification_deliveries ORDER BY id")))
            .scalars()
            .all()
        )
    r = await notifier.send_batch(e.x.t.id, ids, final_attempt=False)
    assert (r["sent"], r["deferred"]) == (1, 1)
    assert sorted(s for _, s in await _deliveries(infra, e)) == ["queued", "sent"]
    async with infra.db.uow(e.x.t.id) as uow:
        waiting = (
            await uow.session.execute(
                text(
                    "SELECT count(*) FROM jobs WHERE kind = 'notifications.send_batch' AND status = 'queued' "
                    "AND run_at > now() + interval '23 hours'"
                )
            )
        ).scalar_one()
    assert waiting == 1  # the rest go when the budget frees up, not now

    # A notice that couldn't go within the allowed delay is skipped, and says why.
    monkeypatch.setattr(infra.settings, "mail_notice_max_delay_hours", 0)
    r = await notifier.send_batch(e.x.t.id, ids, final_attempt=False)
    assert r["sent"] == 0 and "deferred" not in r
    async with infra.db.uow(e.x.t.id) as uow:
        skipped = (
            await uow.session.execute(
                text(
                    "SELECT count(*) FROM notification_deliveries WHERE status = 'skipped' AND last_error = 'daily-limit'"
                )
            )
        ).scalar_one()
    assert skipped == 1
    await _clear_budget()
