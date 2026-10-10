from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.core.http import InfraDep, Principal, UoW, require
from app.modules.exports.models import DataExport
from app.modules.exports.service import ExportService
from app.modules.identity.permissions import P

router = APIRouter(prefix="/api/v1/admin/exports", tags=["data export"])


class DataExportOut(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "running", "ready", "failed", "expired"]
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None
    size_bytes: int | None
    counts: dict[str, Any] | None


class ExportLinkOut(BaseModel):
    url: str
    filename: str


def _out(x: DataExport) -> DataExportOut:
    return DataExportOut(
        id=x.id,
        status=x.status,
        created_at=x.created_at,
        finished_at=x.finished_at,
        expires_at=x.expires_at,
        size_bytes=x.size_bytes,
        counts=x.counts,
    )


@router.get("")
async def list_exports(
    uow: UoW, infra: InfraDep, _: Principal = require(P.DATA_EXPORT)
) -> list[DataExportOut]:
    return [_out(x) for x in await ExportService.recent(uow)]


@router.post("", status_code=202)
async def request_export(
    uow: UoW, infra: InfraDep, principal: Principal = require(P.DATA_EXPORT)
) -> DataExportOut:
    export = await ExportService(infra).request(uow, principal)
    await uow.flush()
    await uow.session.refresh(export)
    return _out(export)


@router.post("/{export_id}/link")
async def export_link(
    export_id: uuid.UUID,
    response: Response,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.DATA_EXPORT),
) -> ExportLinkOut:
    response.headers["Cache-Control"] = "private, no-store"
    link = await ExportService(infra).link(uow, principal, export_id)
    return ExportLinkOut(url=link.url, filename=link.filename)
