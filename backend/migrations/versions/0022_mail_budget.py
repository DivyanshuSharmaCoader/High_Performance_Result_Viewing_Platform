"""a daily email budget shared by every process (docs/16 §5; the email provider's daily cap)

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-14 10:30:00

A free email plan sends a fixed number a day (Brevo: 300). Past it every message fails, password resets
and invitations included. ``ops_mail_take`` hands out sends from a rolling 24-hour window, so no 24 hours
ever exceed the limit, whenever the provider's own day starts. Result notices (bulk) stop ``reserve``
short of the limit, which is kept for account emails; a bulk sender is told when the next send frees up
and waits until then. One row per send, no recipient and no content; rows older than two days go.

Only the migrator owns the table; the runtime role reaches it through the function alone.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TAKE = """
CREATE FUNCTION ops_mail_take(p_limit int, p_reserve int, p_bulk boolean)
RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    cap int := p_limit - CASE WHEN p_bulk THEN greatest(p_reserve, 0) ELSE 0 END;
    used int;
BEGIN
    -- NULL: take it, send now. A time: the budget is spent until then.
    PERFORM pg_advisory_xact_lock(hashtext('scorecode.mail_budget'));
    DELETE FROM mail_sends WHERE sent_at < now() - interval '2 days';
    SELECT count(*) INTO used FROM mail_sends WHERE sent_at > now() - interval '24 hours';
    IF used < cap THEN
        INSERT INTO mail_sends (bulk) VALUES (p_bulk);
        RETURN NULL;
    END IF;
    IF cap <= 0 THEN
        RETURN now() + interval '24 hours';
    END IF;
    -- The moment enough of the window's oldest sends age out to free one.
    RETURN (SELECT sent_at FROM mail_sends WHERE sent_at > now() - interval '24 hours'
             ORDER BY sent_at OFFSET used - cap LIMIT 1) + interval '24 hours';
END
$$;
"""


def upgrade() -> None:
    op.execute(
        "CREATE TABLE mail_sends (id bigserial PRIMARY KEY, sent_at timestamptz NOT NULL DEFAULT now(), "
        "bulk boolean NOT NULL)"
    )
    op.execute("CREATE INDEX ix_mail_sends_sent_at ON mail_sends (sent_at)")
    op.execute("REVOKE ALL ON mail_sends FROM PUBLIC")
    op.execute(TAKE)
    op.execute("REVOKE ALL ON FUNCTION ops_mail_take(int, int, boolean) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ops_mail_take(int, int, boolean) TO scorecode_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS ops_mail_take(int, int, boolean)")
    op.execute("DROP TABLE IF EXISTS mail_sends")
