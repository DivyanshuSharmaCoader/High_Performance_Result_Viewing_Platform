"""``scorecode seed`` — demo tenants created exactly like customers, through the provisioning service.

* Thapar Institute of Engineering & Technology — Enterprise plan, credit/SGPA grading (D25: name only,
  generated monogram, 100% synthetic students).
* Demo Public School — Free plan (shows limits).
* Demo Coaching Academy — Growth plan.

Idempotent: tenants that already exist are left alone. Development/demo only: refuses to run in production.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select, text

from app.core.config import Environment, get_settings
from app.core.container import Infra
from app.modules.audit.service import Actor
from app.modules.tenancy.service import OwnerSpec, ProvisionRequest, provision_tenant, slug_taken

DEMO_PASSWORD = "scorecode-demo-2026"  # noqa: S105 - documented demo credential, never used in production
DEMO_PLATFORM_EMAIL = "ops@scorecode.example.com"
DEMO_PLATFORM_TOTP = "SCORECODEDEMOTOTPSECRETKEYAAAAAA"  # base32 (A–Z, 2–7); dev/demo only


@dataclass(frozen=True)
class DemoTenant:
    slug: str
    name: str
    type: str
    plan: str
    owner_email: str
    owner_name: str
    primary: str
    accent: str


DEMO_TENANTS = (
    DemoTenant(
        "thapar",
        "Thapar Institute of Engineering & Technology",
        "university",
        "enterprise",
        "registrar@thapar.example.com",
        "Office of the Registrar",
        "#8c1d18",
        "#1f4e79",
    ),
    DemoTenant(
        "demoschool",
        "Demo Public School",
        "school",
        "free",
        "principal@demoschool.example.com",
        "Priya Malhotra",
        "#2952cc",
        "#0f766e",
    ),
    DemoTenant(
        "democoaching",
        "Demo Coaching Academy",
        "coaching",
        "growth",
        "director@democoaching.example.com",
        "Arjun Mehta",
        "#6d28d9",
        "#b45309",
    ),
)

Seeder = Callable[[Infra, uuid.UUID, DemoTenant, int], Awaitable[None]]
_extra_seeders: list[Seeder] = []


def register_seeder(fn: Seeder) -> Seeder:
    """Later phases add demo data (structure, students, exams) per tenant without editing this file."""
    _extra_seeders.append(fn)
    return fn


async def seed_tenants(infra: Infra, *, students_per_tenant: int = 120) -> list[str]:
    created: list[str] = []
    password_hash = await infra.passwords.hash(DEMO_PASSWORD)
    for demo in DEMO_TENANTS:
        async with infra.db.uow() as uow:
            if await slug_taken(uow, demo.slug):
                continue
            await provision_tenant(
                uow,
                ProvisionRequest(
                    slug=demo.slug,
                    name=demo.name,
                    type=demo.type,
                    plan_code=demo.plan,
                    owner=OwnerSpec(
                        email=demo.owner_email, full_name=demo.owner_name, password_hash=password_hash
                    ),
                    primary_color=demo.primary,
                    accent_color=demo.accent,
                ),
                Actor.system("seed"),
            )
            created.append(demo.slug)
    for demo in DEMO_TENANTS:
        async with infra.db.uow() as uow:
            row = (
                await uow.session.execute(text("SELECT id FROM resolve_tenant(:s, NULL)"), {"s": demo.slug})
            ).one()
        for seeder in _extra_seeders:
            await seeder(infra, row.id, demo, students_per_tenant)
    return created


async def seed_platform_user(infra: Infra) -> bool:
    from app.modules.identity.models import PlatformUser
    from app.modules.platform.bootstrap import create_platform_user

    async with infra.db.platform_uow() as uow:
        exists = (
            await uow.session.scalars(
                select(PlatformUser.id).where(PlatformUser.email == DEMO_PLATFORM_EMAIL)
            )
        ).first()
    if exists:
        return False
    await create_platform_user(
        infra,
        DEMO_PLATFORM_EMAIL,
        "ScoreCode Operations (demo)",
        DEMO_PASSWORD,
        totp_secret=DEMO_PLATFORM_TOTP,
    )
    return True


async def run_seed(*, students_per_tenant: int = 120) -> None:
    settings = get_settings()
    if settings.env is Environment.PRODUCTION:
        raise SystemExit("Refusing to seed demo data in production.")
    from app.jobs_registry import load_job_handlers

    load_job_handlers()
    infra = Infra.build(settings, app_name="scorecode-seed")
    try:
        created = await seed_tenants(infra, students_per_tenant=students_per_tenant)
        platform_created = await seed_platform_user(infra)
    finally:
        await infra.close()
    base = settings.base_domain
    print("Demo tenants:", ", ".join(created) or "already present")
    for demo in DEMO_TENANTS:
        print(
            f"  {settings.tenant_origin(demo.slug)}  owner {demo.owner_email} / {DEMO_PASSWORD}  ({demo.plan})"
        )
    print(f"Platform console: {settings.public_origin(f'{settings.platform_subdomain}.{base}')}")
    print(
        f"  {DEMO_PLATFORM_EMAIL} / {DEMO_PASSWORD}  TOTP secret {DEMO_PLATFORM_TOTP}"
        + ("" if platform_created else " (already existed)")
    )
