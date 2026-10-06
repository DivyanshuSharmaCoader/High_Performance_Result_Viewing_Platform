"""Tenant resolution (isolation layer L1) and tenant provisioning (P4.3).

Resolution reads through the ``resolve_tenant()`` SECURITY DEFINER function — the runtime role can look
up *one* tenant by host but can never list tenants. Results are cached briefly (positive 60 s, negative
10 s) because host→tenant mappings change rarely.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text

from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import Conflict, ValidationFailed
from app.core.ids import uuid7
from app.core.tenant import SLUG_RE, HostInfo, TenantContext
from app.modules.audit.service import Actor, record
from app.modules.branding.models import TenantBranding
from app.modules.entitlements.models import USAGE_METRICS, Plan, TenantSubscription, TenantUsageCounter
from app.modules.identity.models import User, UserRole
from app.modules.tenancy.models import TENANT_TYPES, Tenant, TenantSettings

RESERVED_SLUGS = frozenset(
    {
        "www",
        "admin",
        "api",
        "app",
        "verify",
        "status",
        "mail",
        "smtp",
        "ftp",
        "files",
        "cdn",
        "static",
        "assets",
        "help",
        "support",
        "docs",
        "blog",
        "billing",
        "login",
        "signup",
        "auth",
        "dashboard",
        "scorecode",
        "test",
        "demo",
        "staging",
        "dev",
        "root",
        "system",
        "platform",
        "security",
        "abuse",
        "postmaster",
        "hostmaster",
        "webmaster",
        "info",
        "news",
        "about",
    }
)

POSITIVE_TTL_S = 60
NEGATIVE_TTL_S = 10


def _host_key(host: str) -> str:
    return f"tenant:host:{host}"


@dataclass(frozen=True)
class ResolvedTenant:
    context: TenantContext
    config_version: int


class TenantResolver:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    async def resolve(self, host: HostInfo) -> ResolvedTenant | None:
        key = _host_key(host.host)
        cached: dict[str, Any] | None = await self.infra.cache.get(key)
        if cached is not None:
            if not cached.get("found"):
                return None
            return _from_cache(cached, host.host)
        async with self.infra.db.uow() as uow:
            row = (
                await uow.session.execute(
                    text("SELECT id, slug, name, status, config_version FROM resolve_tenant(:slug, :domain)"),
                    {"slug": host.slug, "domain": None if host.slug else host.host},
                )
            ).one_or_none()
        if row is None:
            await self.infra.cache.set(key, {"found": False}, NEGATIVE_TTL_S)
            return None
        data = {
            "found": True,
            "id": str(row.id),
            "slug": row.slug,
            "name": row.name,
            "status": row.status,
            "config_version": row.config_version,
        }
        await self.infra.cache.set(key, data, POSITIVE_TTL_S)
        return _from_cache(data, host.host)

    async def invalidate(self, slug: str) -> None:
        await self.infra.cache.delete(_host_key(f"{slug}.{self.infra.settings.base_domain}"))


def _from_cache(data: dict[str, Any], host: str) -> ResolvedTenant:
    return ResolvedTenant(
        context=TenantContext(
            tenant_id=uuid.UUID(data["id"]),
            slug=data["slug"],
            name=data["name"],
            status=data["status"],
            host=host,
        ),
        config_version=int(data["config_version"]),
    )


def validate_slug(slug: str) -> str:
    slug = slug.strip().lower()
    if not SLUG_RE.match(slug):
        raise ValidationFailed(
            "Use 3–31 lowercase letters, numbers or single hyphens, starting and ending with a letter or number.",
            field="slug",
        )
    if slug in RESERVED_SLUGS:
        raise ValidationFailed("This address is reserved. Please choose another.", field="slug")
    return slug


async def slug_taken(uow: UnitOfWork, slug: str) -> bool:
    return bool((await uow.session.execute(text("SELECT tenant_slug_taken(:s)"), {"s": slug})).scalar_one())


# ---- provisioning -------------------------------------------------------------------------------

ProvisionHook = Callable[[UnitOfWork, Tenant, Actor], Awaitable[None]]
_provision_hooks: list[ProvisionHook] = []


def on_tenant_provisioned(fn: ProvisionHook) -> ProvisionHook:
    """Modules register defaults for new tenants (e.g. grading schemes) without tenancy importing them."""
    _provision_hooks.append(fn)
    return fn


@dataclass(frozen=True)
class OwnerSpec:
    email: str
    full_name: str
    password_hash: str


@dataclass(frozen=True)
class ProvisionRequest:
    slug: str
    name: str
    type: str
    plan_code: str
    owner: OwnerSpec
    timezone: str = "Asia/Kolkata"
    subscription_status: str = "active"
    primary_color: str = "#2952cc"
    accent_color: str = "#0f766e"


async def provision_tenant(uow: UnitOfWork, req: ProvisionRequest, actor: Actor) -> Tenant:
    """Create a tenant and everything it needs, in the caller's single transaction.

    Used by self-serve sign-up and by the seed command — Thapar and demo tenants are created exactly
    like customers (docs/06 §7).
    """
    slug = validate_slug(req.slug)
    if req.type not in TENANT_TYPES:
        raise ValidationFailed("Unknown institution type.", field="type")
    if await slug_taken(uow, slug):
        raise Conflict("This address is already taken.", field="slug")
    tenant_id = uuid7()
    await uow.set_tenant(tenant_id)
    plan = (
        await uow.session.scalars(select(Plan).where(Plan.code == req.plan_code, Plan.active))
    ).one_or_none()
    if plan is None:
        raise ValidationFailed(f"Unknown plan {req.plan_code!r}.")
    tenant = Tenant(id=tenant_id, slug=slug, name=req.name.strip(), type=req.type, timezone=req.timezone)
    uow.session.add(tenant)
    await uow.flush()
    uow.session.add(TenantSettings(tenant_id=tenant_id, official_name=req.name.strip()))
    uow.session.add(
        TenantBranding(
            tenant_id=tenant_id,
            display_name=req.name.strip()[:120],
            primary_color=req.primary_color,
            accent_color=req.accent_color,
        )
    )
    uow.session.add(TenantSubscription(tenant_id=tenant_id, plan_id=plan.id, status=req.subscription_status))
    for metric in USAGE_METRICS:
        uow.session.add(TenantUsageCounter(tenant_id=tenant_id, metric=metric, value=0))
    owner = User(
        tenant_id=tenant_id,
        kind="staff",
        login_id=req.owner.email.strip().lower(),
        email=req.owner.email.strip().lower(),
        full_name=req.owner.full_name.strip(),
        password_hash=req.owner.password_hash,
        status="active",
    )
    uow.session.add(owner)
    await uow.flush()
    uow.session.add(UserRole(tenant_id=tenant_id, user_id=owner.id, role="institution_owner"))
    await uow.session.execute(
        text(
            "UPDATE tenant_usage_counters SET value = 1 WHERE tenant_id = :t AND metric IN ('staff_users','admin_users')"
        ),
        {"t": tenant_id},
    )
    for hook in _provision_hooks:
        await hook(uow, tenant, actor)
    await record(
        uow,
        actor,
        "tenant.created",
        entity_type="tenant",
        entity_id=tenant_id,
        summary=f"Institution '{tenant.name}' created on the {plan.name} plan",
        after={"slug": slug, "name": tenant.name, "type": req.type, "plan": plan.code},
    )
    return tenant
