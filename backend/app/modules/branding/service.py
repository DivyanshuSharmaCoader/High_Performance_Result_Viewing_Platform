"""Data-driven branding (docs/09 §6): one frontend build for all tenants, themed by tokens from
``GET /api/v1/tenant/config``. Brand colours are contrast-checked on save; semantic colours are fixed."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import ValidationFailed
from app.core.tenant import TenantContext
from app.modules.branding.models import TenantBranding
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EffectiveEntitlements
from app.modules.tenancy.models import Tenant, TenantSettings

DEFAULT_PRIMARY = "#2952cc"
DEFAULT_ACCENT = "#0f766e"
CONFIG_TTL_S = 300
CONFIG_LOCAL_TTL_S = 15


def _channel(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def best_text_on(bg: str) -> str:
    return "#ffffff" if contrast(bg, "#ffffff") >= contrast(bg, "#111827") else "#111827"


def darken_until(color: str, against: str = "#ffffff", target: float = 4.5) -> str:
    """Darken ``color`` until it reaches ``target`` contrast against ``against`` (for text/links)."""
    h = color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    for _ in range(100):
        candidate = f"#{r:02x}{g:02x}{b:02x}"
        if contrast(candidate, against) >= target:
            return candidate
        r, g, b = int(r * 0.92), int(g * 0.92), int(b * 0.92)
    return "#111827"


def validate_brand_color(value: str, field: str) -> str:
    v = value.strip().lower()
    if len(v) != 7 or not v.startswith("#") or any(c not in "0123456789abcdef" for c in v[1:]):
        raise ValidationFailed("Use a 6-digit hex colour like #2952cc.", field=field)
    # Buttons use the brand colour as background with white/near-black text: require AA for one of them.
    if max(contrast(v, "#ffffff"), contrast(v, "#111827")) < 4.5:
        raise ValidationFailed(
            "This colour doesn't leave enough contrast for readable button text. Choose a darker or lighter shade.",
            field=field,
        )
    return v


def theme_tokens(primary: str, accent: str, font: str) -> dict[str, str]:
    return {
        "primary": primary,
        "primary_contrast": best_text_on(primary),
        "primary_ink": darken_until(primary),
        "accent": accent,
        "accent_contrast": best_text_on(accent),
        "font_family": font,
    }


def _config_key(tenant: TenantContext) -> str:
    return tenant.cache_key("config")


class BrandingService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    async def get(self, uow: UnitOfWork) -> TenantBranding:
        return (await uow.session.scalars(select(TenantBranding))).one()

    async def public_config(
        self, uow: UnitOfWork, tenant: TenantContext, ent: EffectiveEntitlements
    ) -> dict[str, Any]:
        cached: dict[str, Any] | None = await self.infra.cache.get(
            _config_key(tenant), local_ttl_s=CONFIG_LOCAL_TTL_S
        )
        if cached is not None:
            return cached
        b = await self.get(uow)
        settings = (await uow.session.scalars(select(TenantSettings))).one()
        custom = ent.has(F.CUSTOM_BRANDING)
        primary = b.primary_color if custom else DEFAULT_PRIMARY
        accent = b.accent_color if custom else DEFAULT_ACCENT
        font = b.font_family if custom else "Inter"
        config = {
            "tenant": {"slug": tenant.slug, "name": tenant.name},
            "branding": {
                "display_name": b.display_name,
                "short_name": b.short_name,
                "logo_url": "/api/v1/tenant/logo" if b.logo_file_id else None,
                "logo_version": b.version,
                "login_heading": b.login_heading if custom else None,
                "login_message": b.login_message if custom else None,
                "footer_text": b.footer_text,
                "support_email": b.support_email or settings.contact_email,
                "show_powered_by": b.show_powered_by or not ent.has(F.REMOVE_POWERED_BY),
                "tokens": theme_tokens(primary, accent, font),
            },
            "settings": {
                "student_activation_mode": settings.student_activation_mode,
                "locale": settings.locale,
            },
        }
        await self.infra.cache.set(_config_key(tenant), config, CONFIG_TTL_S, local_ttl_s=CONFIG_LOCAL_TTL_S)
        return config

    async def invalidate(self, uow: UnitOfWork, tenant: TenantContext) -> None:
        await uow.session.execute(
            update(Tenant)
            .where(Tenant.id == tenant.tenant_id)
            .values(config_version=Tenant.config_version + 1)
        )
        key = _config_key(tenant)
        uow.after_commit(lambda: self.infra.cache.delete(key))
