"""EXPLAIN ANALYZE the student read path (P14.2) against the load-test tenant.

    uv run python scripts/explain_hot_queries.py > ../benchmarks/results/runs/explain.txt

Runs as the runtime role, in the tenant's context, the way the API does. The SQL mirrors what the services
issue for one student request (session lookup on a cache miss, the student, "my results", the stats
snapshot, the marksheet, the unread count), with real ids from ``loadtest_data.py``'s data. Plans are
printed with buffers and timing. The point is to see index use and row estimates, not to time anything.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.config import Settings
from app.core.container import Infra

QUERIES: list[tuple[str, str]] = [
    (
        "tenant from host (cache miss)",
        "SELECT id, slug, name, status, config_version FROM resolve_tenant(:slug, NULL)",
    ),
    (
        "session + user (cache miss)",
        "SELECT s.*, u.* FROM sessions s JOIN users u ON u.id = s.user_id AND u.tenant_id = s.tenant_id "
        "WHERE s.id = :session_id",
    ),
    ("the session's student", "SELECT * FROM students WHERE user_id = :user_id"),
    (
        "my results (latest first)",
        "SELECT p.*, r.payload FROM publications p JOIN published_results r "
        "ON r.publication_id = p.id AND r.student_id = :student_id "
        "WHERE p.status = 'published' ORDER BY p.published_at DESC, p.id",
    ),
    ("class statistics", "SELECT stats FROM exam_statistics WHERE publication_id = :publication_id"),
    (
        "marksheet",
        "SELECT * FROM marksheet_documents WHERE publication_id = :publication_id AND student_id = :student_id",
    ),
    (
        "unread notifications",
        "SELECT count(*) FROM notifications WHERE user_id = :user_id AND read_at IS NULL",
    ),
]


async def main() -> None:
    infra = Infra.build(Settings(), app_name="scorecode-explain")
    try:
        async with infra.db.uow() as uow:
            tenant_id = (
                await uow.session.execute(text("SELECT id FROM resolve_tenant('loadtest', NULL)"))
            ).scalar_one()
        async with infra.db.uow(tenant_id) as uow:
            ids = (
                await uow.session.execute(
                    text(
                        "SELECT s.id AS session_id, s.user_id, st.id AS student_id, r.publication_id "
                        "FROM sessions s JOIN students st ON st.user_id = s.user_id "
                        "JOIN published_results r ON r.student_id = st.id ORDER BY s.created_at LIMIT 1"
                    )
                )
            ).one()
            params = {"slug": "loadtest", **ids._mapping}
            for title, sql in QUERIES:
                plan = await uow.session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS, COSTS) {sql}"), params)
                print(f"== {title}\n{sql}\n")
                print("\n".join(row[0] for row in plan.all()))
                print()
    finally:
        await infra.close()


if __name__ == "__main__":
    asyncio.run(main())
