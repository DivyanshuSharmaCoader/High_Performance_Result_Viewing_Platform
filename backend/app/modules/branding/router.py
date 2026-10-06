from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, File, Request, Response, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.http import InfraDep, Principal, TenantDep, UoW, public, require
from app.core.tenant import Realm
from app.modules.audit.service import Actor, diff, record
from app.modules.branding.service import BrandingService, validate_brand_color
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EntitlementService
from app.modules.files.service import IMAGE_TYPES, FileService, validate_upload
from app.modules.identity.permissions import P

router = APIRouter(prefix="/api/v1", tags=["branding"])


@router.get("/tenant/config", dependencies=[public(Realm.TENANT)])
async def tenant_config(request: Request, uow: UoW, tenant: TenantDep, infra: InfraDep) -> Response:
    """Public branding + settings for the SPA bootstrap (cacheable with ETag)."""
    ent = await EntitlementService(infra).effective(uow)
    config = await BrandingService(infra).public_config(uow, tenant, ent)
    body = json.dumps({**config, "features": ent.values}, separators=(",", ":"), default=str)
    etag = '"' + hashlib.sha256(body.encode()).hexdigest()[:32] + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "private, max-age=60"})
    return Response(
        body,
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "private, max-age=60"},
    )


@router.get("/tenant/logo", dependencies=[public(Realm.TENANT)])
async def tenant_logo(uow: UoW, infra: InfraDep) -> RedirectResponse:
    branding = await BrandingService(infra).get(uow)
    if branding.logo_file_id is None:
        raise NotFound("No logo")
    stored = await FileService(infra).get(uow, branding.logo_file_id)
    url = FileService(infra).signed_url(stored, ttl_s=3600)
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "private, max-age=600"})


class BrandingOut(BaseModel):
    display_name: str
    short_name: str | None
    has_logo: bool
    primary_color: str
    accent_color: str
    font_family: str
    login_heading: str | None
    login_message: str | None
    footer_text: str | None
    support_email: str | None
    show_powered_by: bool
    version: int
    custom_branding_available: bool
    remove_powered_by_available: bool


class BrandingIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int
    display_name: str = Field(min_length=2, max_length=120)
    short_name: str | None = Field(default=None, max_length=24)
    primary_color: str | None = None
    accent_color: str | None = None
    font_family: str | None = None
    login_heading: str | None = Field(default=None, max_length=120)
    login_message: str | None = Field(default=None, max_length=600)
    footer_text: str | None = Field(default=None, max_length=300)
    support_email: EmailStr | None = None
    show_powered_by: bool | None = None


async def _branding_out(uow: UoW, infra: InfraDep) -> BrandingOut:
    b = await BrandingService(infra).get(uow)
    ent = await EntitlementService(infra).effective(uow)
    return BrandingOut(
        display_name=b.display_name,
        short_name=b.short_name,
        has_logo=b.logo_file_id is not None,
        primary_color=b.primary_color,
        accent_color=b.accent_color,
        font_family=b.font_family,
        login_heading=b.login_heading,
        login_message=b.login_message,
        footer_text=b.footer_text,
        support_email=b.support_email,
        show_powered_by=b.show_powered_by,
        version=b.version,
        custom_branding_available=ent.has(F.CUSTOM_BRANDING),
        remove_powered_by_available=ent.has(F.REMOVE_POWERED_BY),
    )


@router.get("/admin/branding")
async def get_branding(uow: UoW, infra: InfraDep, _: Principal = require(P.BRANDING_MANAGE)) -> BrandingOut:
    return await _branding_out(uow, infra)


FONT_CHOICES = ("Inter", "Source Sans 3", "Noto Sans", "IBM Plex Sans", "Merriweather Sans")


@router.put("/admin/branding")
async def update_branding(
    body: BrandingIn,
    uow: UoW,
    tenant: TenantDep,
    infra: InfraDep,
    principal: Principal = require(P.BRANDING_MANAGE),
) -> BrandingOut:
    svc = BrandingService(infra)
    ent = await EntitlementService(infra).effective(uow)
    b = await svc.get(uow)
    if b.version != body.version:
        raise Conflict("Branding was changed by someone else. Reload to see the latest version.")
    before: dict[str, Any] = {
        k: getattr(b, k)
        for k in (
            "display_name",
            "short_name",
            "primary_color",
            "accent_color",
            "font_family",
            "login_heading",
            "login_message",
            "footer_text",
            "support_email",
            "show_powered_by",
        )
    }
    b.display_name = body.display_name
    b.short_name = body.short_name or None
    b.footer_text = body.footer_text or None
    b.support_email = str(body.support_email) if body.support_email else None
    premium_requested = any(
        v is not None
        for v in (
            body.primary_color,
            body.accent_color,
            body.font_family,
            body.login_heading,
            body.login_message,
        )
    )
    if premium_requested:
        ent.require(F.CUSTOM_BRANDING)
        if body.primary_color is not None:
            b.primary_color = validate_brand_color(body.primary_color, "primary_color")
        if body.accent_color is not None:
            b.accent_color = validate_brand_color(body.accent_color, "accent_color")
        if body.font_family is not None:
            if body.font_family not in FONT_CHOICES:
                raise ValidationFailed("Choose one of the available fonts.", field="font_family")
            b.font_family = body.font_family
        b.login_heading = body.login_heading or None
        b.login_message = body.login_message or None
    if body.show_powered_by is not None:
        if body.show_powered_by is False:
            ent.require(F.REMOVE_POWERED_BY)
        b.show_powered_by = body.show_powered_by
    b.version += 1
    after = {k: getattr(b, k) for k in before}
    d_before, d_after = diff(before, after)
    if d_after:
        await record(
            uow,
            Actor.from_principal(principal),
            "branding.updated",
            entity_type="branding",
            entity_id=tenant.tenant_id,
            before=d_before,
            after=d_after,
        )
    await svc.invalidate(uow, tenant)
    await uow.flush()
    return await _branding_out(uow, infra)


@router.post("/admin/branding/logo")
async def upload_logo(
    uow: UoW,
    tenant: TenantDep,
    infra: InfraDep,
    file: UploadFile = File(...),
    principal: Principal = require(P.BRANDING_MANAGE),
) -> BrandingOut:
    data = await file.read(infra.settings.max_logo_bytes + 1)
    kind = validate_upload(data, IMAGE_TYPES, infra.settings.max_logo_bytes)
    stored = await FileService(infra).store(
        uow,
        data=data,
        kind="logo",
        file_type=kind,
        original_name=file.filename,
        uploaded_by=principal.user_id,
    )
    svc = BrandingService(infra)
    b = await svc.get(uow)
    b.logo_file_id = stored.id
    b.version += 1
    await record(
        uow,
        Actor.from_principal(principal),
        "branding.logo_updated",
        entity_type="branding",
        entity_id=tenant.tenant_id,
        after={"file_id": stored.id, "bytes": stored.size_bytes},
    )
    await svc.invalidate(uow, tenant)
    await uow.flush()
    return await _branding_out(uow, infra)


@router.delete("/admin/branding/logo")
async def remove_logo(
    uow: UoW, tenant: TenantDep, infra: InfraDep, principal: Principal = require(P.BRANDING_MANAGE)
) -> BrandingOut:
    svc = BrandingService(infra)
    b = await svc.get(uow)
    if b.logo_file_id is not None:
        b.logo_file_id = None
        b.version += 1
        await record(
            uow,
            Actor.from_principal(principal),
            "branding.logo_removed",
            entity_type="branding",
            entity_id=tenant.tenant_id,
        )
        await svc.invalidate(uow, tenant)
        await uow.flush()
    return await _branding_out(uow, infra)
