"""Regression: a request must never hold two pooled DB connections at once.

Authentication used to open its own transaction (session lookup on cache miss) while the request's unit
of work already held a connection. With N concurrent requests and a pool of N, every request held one
connection and waited for a second — a pool deadlock resolved only by the pool timeout.
"""

from __future__ import annotations

import pytest

from app.core.container import Infra
from app.main import create_app
from tests.conftest import make_settings
from tests.helpers import Client, make_tenant

pytestmark = pytest.mark.integration


async def test_authenticated_request_needs_only_one_connection(migrated_db: str) -> None:
    settings = make_settings(db_pool_size=1, db_max_overflow=0, db_pool_timeout_s=2.0, redis_url=None)
    infra = Infra.build(settings, app_name="scorecode-test-pool1")
    try:
        from app.modules.entitlements.sync import sync_catalogue

        await sync_catalogue(infra.db)
        app = create_app(settings, infra)
        t = await make_tenant(infra)
        async with Client(app, t.host) as c:
            await c.login(t.owner_email)
            infra.cache.local.clear()  # force the session lookup to hit the database
            for path in ("/api/v1/me", "/api/v1/admin/onboarding", "/api/v1/admin/staff"):
                r = await c.get(path)
                assert r.status_code == 200, (path, r.status_code, r.text)
                infra.cache.local.clear()
    finally:
        await infra.close()


async def test_platform_request_needs_only_one_connection(migrated_db: str) -> None:
    from tests.helpers import make_platform_admin, totp_now

    settings = make_settings(db_pool_size=1, db_max_overflow=0, db_pool_timeout_s=2.0, redis_url=None)
    infra = Infra.build(settings, app_name="scorecode-test-pool1p")
    try:
        app = create_app(settings, infra)
        email, password, secret = await make_platform_admin(infra)
        async with Client(app, "admin.localhost") as c:
            r = await c.post(
                "/api/v1/platform/auth/login",
                json={"email": email, "password": password, "totp_code": totp_now(secret)},
            )
            assert r.status_code == 200, r.text
            infra.cache.local.clear()
            assert (await c.get("/api/v1/platform/tenants")).status_code == 200
    finally:
        await infra.close()
