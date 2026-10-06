"""Authorization matrix (P3.6, docs/15 §4.2): every tenant route × every role.

Expected outcome is derived from each route's declared permissions and the role→permission map:
denied roles must get exactly 403; allowed roles must never get 401/403; anonymous callers get 401.
"""

from __future__ import annotations

import uuid

import pytest

from app.modules.identity.permissions import permissions_for
from tests.helpers import client_as, make_tenant
from tests.integration.test_isolation import SAMPLE_BODIES
from tests.routes import api_routes

pytestmark = pytest.mark.integration

ROLES = ("institution_owner", "institution_admin", "faculty", "student", "anonymous")
# Routes whose success has side effects on the caller's own session; exercised elsewhere.
SKIP = {("POST", "/api/v1/auth/logout-all")}


@pytest.mark.parametrize("role", ROLES)
async def test_authorization_matrix(app, infra, role: str) -> None:
    t = await make_tenant(infra, plan="enterprise")
    routes = [r for r in api_routes(app) if r.realm == "tenant" and (r.method, r.path) not in SKIP]
    assert len(routes) >= 15, "route discovery looks broken"
    granted = permissions_for([role]) if role != "anonymous" else frozenset()
    c = await client_as(app, infra, t, role)
    failures = []
    async with c:
        for route in routes:
            url = route.url({p: uuid.uuid4() for p in route.params})
            body = SAMPLE_BODIES.get((route.method, route.path), {})
            if route.method == "GET":
                r = await c.get(url)
            elif route.method == "DELETE":
                r = await c.delete(url)
            else:
                r = await getattr(c, route.method.lower())(url, json=body)
            if role == "anonymous":
                expected_ok = r.status_code == 401
            elif route.permissions <= granted:
                expected_ok = r.status_code not in (401, 403)
            else:
                expected_ok = r.status_code == 403
            if not expected_ok:
                failures.append(f"{role}: {route.method} {route.path} → {r.status_code}")
    assert not failures, "\n".join(failures)
