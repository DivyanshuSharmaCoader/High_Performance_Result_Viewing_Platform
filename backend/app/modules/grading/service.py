"""Grading scheme use cases (P7.3). A scheme's behaviour lives in its versions; saving changes appends a
version, so exams processed earlier keep the exact rules they used."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import Conflict, InvalidState, NotFound, ValidationFailed
from app.core.http import Principal
from app.core.integrity import ConstraintMessage, flush_checked
from app.modules.audit.service import Actor, record
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EntitlementService
from app.modules.grading.engine import GradingConfig, GradingConfigError, config_to_json, parse_config
from app.modules.grading.models import STRATEGIES, GradingScheme, GradingSchemeVersion
from app.modules.tenancy.models import TenantSettings

MESSAGES = {
    "uq_grading_schemes__tenant_name": ConstraintMessage(
        "A grading scheme with this name already exists.", "name"
    ),
}
STRATEGY_LABEL = {
    "percentage_bands": "Percentage bands",
    "credit_gpa": "Credits and SGPA",
    "marks_only": "Marks only",
}


def validated(config: dict[str, Any]) -> GradingConfig:
    """Parse a scheme config; problems come back as ``config.bands.2.min_percentage``-style fields."""
    try:
        return parse_config(config)
    except GradingConfigError as exc:
        errors = []
        for e in exc.errors:
            path = [str(p) for p in e.get("loc", ()) if p not in STRATEGIES]
            errors.append({"field": ".".join(["config", *path]), "message": str(e.get("msg"))})
        raise ValidationFailed(
            str(exc), field=errors[0]["field"] if errors else "config", errors=errors
        ) from exc


@dataclass
class SchemeView:
    scheme: GradingScheme
    latest: GradingSchemeVersion
    is_default: bool
    versions: list[GradingSchemeVersion] = field(default_factory=list)


class GradingService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    async def get(self, uow: UnitOfWork, scheme_id: uuid.UUID, *, lock: bool = False) -> GradingScheme:
        stmt = select(GradingScheme).where(GradingScheme.id == scheme_id)
        if lock:
            stmt = stmt.with_for_update()
        scheme = (await uow.session.scalars(stmt)).one_or_none()
        if scheme is None:
            raise NotFound("Grading scheme not found")
        return scheme

    async def version(self, uow: UnitOfWork, version_id: uuid.UUID) -> GradingSchemeVersion:
        v = (
            await uow.session.scalars(
                select(GradingSchemeVersion).where(GradingSchemeVersion.id == version_id)
            )
        ).one_or_none()
        if v is None:
            raise NotFound("Grading scheme version not found")
        return v

    async def _default_id(self, uow: UnitOfWork) -> uuid.UUID | None:
        return (await uow.session.scalars(select(TenantSettings.default_grading_scheme_id))).one_or_none()

    async def _latest(
        self, uow: UnitOfWork, scheme_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, GradingSchemeVersion]:
        if not scheme_ids:
            return {}
        newest = (
            select(GradingSchemeVersion.scheme_id, func.max(GradingSchemeVersion.version).label("v"))
            .where(GradingSchemeVersion.scheme_id.in_(scheme_ids))
            .group_by(GradingSchemeVersion.scheme_id)
            .subquery()
        )
        rows = await uow.session.scalars(
            select(GradingSchemeVersion).join(
                newest,
                (newest.c.scheme_id == GradingSchemeVersion.scheme_id)
                & (newest.c.v == GradingSchemeVersion.version),
            )
        )
        return {v.scheme_id: v for v in rows.all()}

    async def list(self, uow: UnitOfWork, *, include_archived: bool) -> list[SchemeView]:
        stmt = select(GradingScheme).order_by(GradingScheme.name)
        if not include_archived:
            stmt = stmt.where(GradingScheme.archived_at.is_(None))
        schemes = list((await uow.session.scalars(stmt)).all())
        latest = await self._latest(uow, [s.id for s in schemes])
        default = await self._default_id(uow)
        return [SchemeView(s, latest[s.id], s.id == default) for s in schemes if s.id in latest]

    async def detail(self, uow: UnitOfWork, scheme_id: uuid.UUID) -> SchemeView:
        scheme = await self.get(uow, scheme_id)
        versions = list(
            (
                await uow.session.scalars(
                    select(GradingSchemeVersion)
                    .where(GradingSchemeVersion.scheme_id == scheme.id)
                    .order_by(GradingSchemeVersion.version.desc())
                )
            ).all()
        )
        return SchemeView(scheme, versions[0], scheme.id == await self._default_id(uow), versions)

    async def _check_entitlement(self, uow: UnitOfWork, cfg: GradingConfig) -> None:
        if cfg.strategy == "credit_gpa":
            await EntitlementService(self.infra).require(uow, F.CREDIT_GRADING)

    async def create(
        self,
        uow: UnitOfWork,
        principal: Principal | None,
        *,
        name: str,
        description: str | None,
        config: dict[str, Any],
    ) -> GradingScheme:
        cfg = validated(config)
        await self._check_entitlement(uow, cfg)
        clean_name = " ".join(name.split())
        if not clean_name:
            raise ValidationFailed("Give the scheme a name.", field="name")
        tenant_id = uow.require_tenant()
        scheme = GradingScheme(
            tenant_id=tenant_id,
            name=clean_name,
            strategy=cfg.strategy,
            description=(description or "").strip() or None,
            created_by=principal.user_id if principal else None,
        )
        uow.session.add(scheme)
        await flush_checked(uow, MESSAGES)
        uow.session.add(
            GradingSchemeVersion(
                tenant_id=tenant_id,
                scheme_id=scheme.id,
                version=1,
                config=config_to_json(cfg),
                created_by=scheme.created_by,
            )
        )
        settings = (await uow.session.scalars(select(TenantSettings).with_for_update())).one()
        if settings.default_grading_scheme_id is None:
            settings.default_grading_scheme_id = scheme.id  # the first scheme becomes the default
        await uow.flush()
        if principal is not None:
            await record(
                uow,
                Actor.from_principal(principal),
                "grading_scheme.created",
                entity_type="grading_scheme",
                entity_id=scheme.id,
                summary=f"Created grading scheme “{scheme.name}” ({STRATEGY_LABEL[scheme.strategy]})",
            )
        return scheme

    async def update_details(
        self,
        uow: UnitOfWork,
        principal: Principal,
        scheme_id: uuid.UUID,
        *,
        name: str,
        description: str | None,
    ) -> GradingScheme:
        scheme = await self.get(uow, scheme_id, lock=True)
        clean_name = " ".join(name.split())
        if not clean_name:
            raise ValidationFailed("Give the scheme a name.", field="name")
        before = {"name": scheme.name, "description": scheme.description}
        scheme.name = clean_name
        scheme.description = (description or "").strip() or None
        after = {"name": scheme.name, "description": scheme.description}
        if before != after:
            await flush_checked(uow, MESSAGES)
            await record(
                uow,
                Actor.from_principal(principal),
                "grading_scheme.updated",
                entity_type="grading_scheme",
                entity_id=scheme.id,
                before=before,
                after=after,
            )
        return scheme

    async def add_version(
        self,
        uow: UnitOfWork,
        principal: Principal,
        scheme_id: uuid.UUID,
        *,
        config: dict[str, Any],
        note: str | None,
        based_on: int,
    ) -> tuple[GradingSchemeVersion, bool]:
        """Append version N+1. ``based_on`` is the version the editor started from; if someone saved in
        between, the request is refused instead of silently overwriting their rules."""
        scheme = await self.get(uow, scheme_id, lock=True)
        if scheme.archived_at is not None:
            raise InvalidState("Restore this scheme before changing it.")
        cfg = validated(config)
        if cfg.strategy != scheme.strategy:
            raise ValidationFailed(
                "A scheme can't change its kind. Create a new scheme instead.", field="config"
            )
        await self._check_entitlement(uow, cfg)
        latest = (await self._latest(uow, [scheme.id]))[scheme.id]
        if based_on != latest.version:
            raise Conflict(
                f"Someone saved version {latest.version} while you were editing. Reload to see it.",
                current_version=latest.version,
            )
        data = config_to_json(cfg)
        if data == latest.config:
            return latest, False
        version = GradingSchemeVersion(
            tenant_id=scheme.tenant_id,
            scheme_id=scheme.id,
            version=latest.version + 1,
            config=data,
            note=(note or "").strip()[:200] or None,
            created_by=principal.user_id,
        )
        uow.session.add(version)
        scheme.updated_at = utcnow()
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "grading_scheme.version_saved",
            entity_type="grading_scheme",
            entity_id=scheme.id,
            summary=f"Saved version {version.version} of “{scheme.name}”",
            after={"version": version.version, "note": version.note},
        )
        return version, True

    async def set_archived(
        self, uow: UnitOfWork, principal: Principal, scheme_id: uuid.UUID, archived: bool
    ) -> GradingScheme:
        scheme = await self.get(uow, scheme_id, lock=True)
        if archived == (scheme.archived_at is not None):
            return scheme
        if archived and scheme.id == await self._default_id(uow):
            raise InvalidState("Make another scheme the default before archiving this one.")
        scheme.archived_at = utcnow() if archived else None
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            f"grading_scheme.{'archived' if archived else 'restored'}",
            entity_type="grading_scheme",
            entity_id=scheme.id,
        )
        return scheme

    async def make_default(
        self, uow: UnitOfWork, principal: Principal, scheme_id: uuid.UUID
    ) -> GradingScheme:
        scheme = await self.get(uow, scheme_id)
        if scheme.archived_at is not None:
            raise InvalidState("An archived scheme can't be the default.")
        settings = (await uow.session.scalars(select(TenantSettings).with_for_update())).one()
        if settings.default_grading_scheme_id != scheme.id:
            previous = settings.default_grading_scheme_id
            settings.default_grading_scheme_id = scheme.id
            await uow.flush()
            await record(
                uow,
                Actor.from_principal(principal),
                "grading_scheme.made_default",
                entity_type="grading_scheme",
                entity_id=scheme.id,
                before={"default": str(previous) if previous else None},
                after={"default": str(scheme.id)},
            )
        return scheme
