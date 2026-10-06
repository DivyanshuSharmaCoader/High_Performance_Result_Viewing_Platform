"""Grading schemes (P7.3): append-only versions (grant + trigger), defaults, entitlements, preview."""

from __future__ import annotations

import copy

import asyncpg
import pytest

from app.modules.entitlements.catalogue import F
from app.modules.entitlements.models import TenantFeatureOverride
from app.modules.entitlements.service import EntitlementService
from app.modules.grading.templates import BY_KEY
from tests.conftest import PG_HOST, PG_PORT
from tests.helpers import Client, client_as, make_tenant

pytestmark = pytest.mark.integration

BASE = "/api/v1/admin/grading-schemes"
CREDIT = BY_KEY["credit_10_point"].config
BANDS = BY_KEY["board_9_point"].config


async def _create(c: Client, name: str, config: dict) -> dict:
    r = await c.post(BASE, json={"name": name, "config": config})
    assert r.status_code == 201, r.text
    return r.json()


async def test_versions_are_append_only_even_for_the_table_owner(app, infra, migrated_db: str) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        scheme = await _create(c, "Bands", BANDS)
    for user, password, error in (
        ("scorecode_app", "app-dev-pw", "permission denied"),
        ("scorecode_migrator", "migrator-dev-pw", "immutable"),
    ):
        conn = await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=user, password=password, database=migrated_db
        )
        try:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(t.id))
                with pytest.raises(asyncpg.PostgresError, match=error):
                    await conn.execute(
                        "UPDATE grading_scheme_versions SET note = 'rewritten' WHERE id = $1",
                        __import__("uuid").UUID(scheme["version_id"]),
                    )
        finally:
            await conn.close()


async def test_create_list_version_and_default(app, infra) -> None:
    t = await make_tenant(infra, plan="enterprise")
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        first = await _create(c, "Undergraduate scale", CREDIT)
        assert first["version"] == 1 and first["is_default"] is True  # first scheme becomes the default
        assert first["strategy"] == "credit_gpa" and first["strategy_label"] == "Credits and SGPA"
        assert [v["version"] for v in first["versions"]] == [1]
        assert first["versions"][0]["created_by_name"] == "Owner Person"
        second = await _create(c, "School bands", BANDS)
        assert second["is_default"] is False

        dup = await c.post(BASE, json={"name": "  school   BANDS ", "config": BANDS})
        assert dup.status_code == 409 and dup.json()["field"] == "name"

        url = f"{BASE}/{second['id']}/versions"
        same = await c.post(url, json={"config": BANDS, "based_on": 1})
        assert same.status_code == 200 and same.json()["saved"] is False and same.json()["version"] == 1
        changed = copy.deepcopy(BANDS)
        changed["pass_rules"]["paper_pass_percentage"] = "35"
        saved = await c.post(
            url, json={"config": changed, "based_on": 1, "note": "Board raised the pass mark"}
        )
        body = saved.json()
        assert body["saved"] is True and body["version"] == 2
        assert body["config"]["pass_rules"]["paper_pass_percentage"] == "35"
        assert [v["note"] for v in body["versions"]] == ["Board raised the pass mark", None]
        stale = await c.post(url, json={"config": BANDS, "based_on": 1})
        assert stale.status_code == 409 and stale.json()["current_version"] == 2
        kind = await c.post(url, json={"config": CREDIT, "based_on": 2})
        assert kind.status_code == 422 and "can't change its kind" in kind.json()["detail"]

        broken = copy.deepcopy(BANDS)
        broken["bands"][2]["min_percentage"] = "95"
        bad = await c.post(url, json={"config": broken, "based_on": 2})
        assert bad.status_code == 422 and bad.json()["field"] == "config"
        assert "highest to lowest" in bad.json()["detail"]
        typo = copy.deepcopy(BANDS)
        typo["bands"][0]["min_percentage"] = "101"
        bad = await c.post(url, json={"config": typo, "based_on": 2})
        assert bad.json()["field"] == "config.bands.0.min_percentage"

        archive_default = await c.put(f"{BASE}/{first['id']}/archived", json={"archived": True})
        assert archive_default.status_code == 409
        made = await c.post(f"{BASE}/{second['id']}/default")
        assert made.json()["is_default"] is True
        archived = await c.put(f"{BASE}/{first['id']}/archived", json={"archived": True})
        assert archived.json()["archived_at"] is not None
        listed = (await c.get(BASE)).json()
        assert [s["name"] for s in listed] == ["School bands"]
        assert len((await c.get(BASE, params={"include_archived": True})).json()) == 2
        frozen = await c.post(f"{BASE}/{first['id']}/versions", json={"config": CREDIT, "based_on": 1})
        assert frozen.status_code == 409

        renamed = await c.put(
            f"{BASE}/{second['id']}", json={"name": "Secondary bands", "description": "Classes 9–10"}
        )
        assert renamed.json()["name"] == "Secondary bands" and renamed.json()["version"] == 2

        onboarding = (await c.get("/api/v1/admin/onboarding")).json()
        steps = {s["key"]: s for s in onboarding["steps"]}
        assert steps["grading"]["done"] is True and steps["grading"]["detail"] == "Default: Secondary bands"
        assert steps["students"]["done"] is False
        audit = (await c.get("/api/v1/admin/audit-logs", params={"entity_id": second["id"]})).json()["items"]
        assert {"grading_scheme.created", "grading_scheme.version_saved", "grading_scheme.made_default"} <= {
            e["action"] for e in audit
        }


async def test_credit_schemes_need_the_feature(app, infra) -> None:
    t = await make_tenant(infra)
    async with infra.db.platform_uow() as uow:
        uow.session.add(
            TenantFeatureOverride(tenant_id=t.id, feature_key=F.CREDIT_GRADING, value=False, reason="test")
        )
    await EntitlementService(infra).invalidate(t.id)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        r = await c.post(BASE, json={"name": "Credits", "config": CREDIT})
        assert r.status_code == 402 and r.json()["code"] == "feature-not-in-plan"
        assert (await c.post(BASE, json={"name": "Bands", "config": BANDS})).status_code == 201


async def test_templates_and_preview_calculator(app, infra) -> None:
    t = await make_tenant(infra)
    async with Client(app, t.host) as c:
        await c.login(t.owner_email)
        templates = (await c.get(f"{BASE}/templates")).json()
        assert [x["key"] for x in templates] == [
            "board_9_point",
            "credit_10_point",
            "marks_with_ranks",
            "simple_letters",
        ]
        body = {
            "config": CREDIT,
            "papers": [
                {
                    "id": "UCS301",
                    "credits": "4",
                    "components": [
                        {"code": "MST", "max": "25"},
                        {"code": "EST", "max": "45", "min_pass": "18"},
                        {"code": "SESS", "max": "30"},
                    ],
                },
                {"id": "UHU005", "credits": "3", "components": [{"code": "T", "max": "100"}]},
            ],
            "marks": {
                "UCS301": {"components": {"MST": "22", "EST": "40", "SESS": "28"}},
                "UHU005": {"attendance": "absent"},
            },
        }
        r = await c.post(f"{BASE}/preview", json=body)
        assert r.status_code == 200, r.text
        result = r.json()
        # UCS301 90 → O (10) × 4; UHU005 absent → 0 × 3 → SGPA 40/7 = 5.714… → 5.71; one paper absent → fail
        assert result["outcome"] == "fail" and result["sgpa"] == "5.71"
        assert [(p["paper_id"], p["grade"]) for p in result["papers"]] == [("UCS301", "O"), ("UHU005", "AB")]
        too_high = {**body, "marks": {"UCS301": {"components": {"MST": "26", "EST": "40", "SESS": "28"}}}}
        r = await c.post(f"{BASE}/preview", json=too_high)
        assert r.status_code == 422 and r.json()["field"] == "marks"
        r = await c.post(f"{BASE}/preview", json={**body, "config": {"strategy": "nope"}})
        assert r.status_code == 422 and r.json()["field"] == "config.strategy"


async def test_faculty_cannot_see_or_change_grading_schemes(app, infra) -> None:
    t = await make_tenant(infra)
    faculty = await client_as(app, infra, t, "faculty")
    async with faculty:
        assert (await faculty.get(BASE)).status_code == 403
        assert (await faculty.post(BASE, json={"name": "X", "config": BANDS})).status_code == 403
