"""CPU cost of the student read path, in-process (P14.2/P14.3 before/after on one machine).

    uv run python scripts/measure_read_path.py --cache on  --requests 3000
    uv run python scripts/measure_read_path.py --cache off --requests 3000

Runs the k6 journey (config → me → latest → stats → 30% history) through the real application over an
in-process ASGI transport, as students of the ``loadtest`` tenant (backend/scripts/loadtest_data.py). There
is no network, no proxy and no load generator, so what's left is the API's own work per request: its CPU
time (process time) and wall time, on one event loop, ``--concurrency`` students at a time.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time

import httpx
from sqlalchemy import event, select

from app.core.config import Settings
from app.core.container import Infra
from app.main import create_app


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", choices=("on", "off"), default="on")
    parser.add_argument("--requests", type=int, default=3000)
    parser.add_argument("--students", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    settings = Settings(student_read_cache=args.cache == "on", log_level="WARNING", metrics_enabled=True)
    infra = Infra.build(settings, app_name="scorecode-read-bench")
    app = create_app(settings, infra)
    rng = random.Random(args.seed)  # noqa: S311 - load pattern only
    try:
        from app.modules.identity.models import User
        from app.modules.identity.sessions import SessionService

        async with infra.db.uow() as uow:
            from sqlalchemy import text

            tid = (
                await uow.session.execute(text("SELECT id FROM resolve_tenant('loadtest', NULL)"))
            ).scalar_one()
        tokens = []
        async with infra.db.uow(tid) as uow:
            users = (
                await uow.session.scalars(
                    select(User).where(User.kind == "student").order_by(User.login_id).limit(args.students)
                )
            ).all()
            for u in users:
                tokens.append(await SessionService(infra).create(uow, u, ip=None, user_agent="read bench"))
        host = f"loadtest.{settings.base_domain}"
        transport = httpx.ASGITransport(app=app, client=("198.18.0.1", 1234))
        clients = [
            httpx.AsyncClient(
                transport=transport, base_url=f"http://{host}", cookies={settings.session_cookie_name: t}
            )
            for t in tokens
        ]
        timings: dict[str, list[float]] = {}

        async def get(c: httpx.AsyncClient, name: str, path: str) -> httpx.Response:
            started = time.perf_counter()
            r = await c.get(path)
            timings.setdefault(name, []).append((time.perf_counter() - started) * 1000)
            if r.status_code != 200:
                raise RuntimeError(f"{name} {r.status_code} {r.text[:200]}")
            return r

        async def journey(c: httpx.AsyncClient) -> int:
            await get(c, "config", "/api/v1/tenant/config")
            await get(c, "me", "/api/v1/me")
            latest = (await get(c, "latest", "/api/v1/me/results/latest")).json()
            n = 3
            if latest:
                await get(c, "stats", f"/api/v1/me/results/{latest['publication_id']}/stats")
                n += 1
            if rng.random() < 0.3:
                await get(c, "history", "/api/v1/me/results")
                n += 1
            return n

        statements = 0

        def count(*_: object) -> None:
            nonlocal statements
            statements += 1

        event.listen(infra.db.app_engine.sync_engine, "before_cursor_execute", count)
        # Warm up: every student once (fills caches, imports, connection pool).
        for i in range(0, len(clients), args.concurrency):
            await asyncio.gather(*(journey(c) for c in clients[i : i + args.concurrency]))
        timings.clear()
        statements = 0
        done = 0
        cpu0, wall0 = time.process_time(), time.perf_counter()
        while done < args.requests:
            batch = rng.sample(clients, min(args.concurrency, len(clients)))
            done += sum(await asyncio.gather(*(journey(c) for c in batch)))
        cpu, wall = time.process_time() - cpu0, time.perf_counter() - wall0
        for c in clients:
            await c.aclose()
        print(f"read cache {args.cache} · {done} requests · {args.concurrency} students at a time")
        print(
            f"throughput {done / wall:.0f} req/s on one process · CPU {cpu / done * 1000:.2f} ms per request"
            f" · {statements / done:.2f} SQL statements per request"
        )
        for name, values in timings.items():
            q = statistics.quantiles(values, n=100)
            print(f"  {name:8s} p50 {q[49]:6.2f} ms  p95 {q[94]:6.2f} ms")
    finally:
        await infra.close()


if __name__ == "__main__":
    asyncio.run(main())
