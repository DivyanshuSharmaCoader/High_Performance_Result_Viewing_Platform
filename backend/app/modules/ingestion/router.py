from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.http import InfraDep, Principal, UoW, require
from app.modules.files.service import XLSX
from app.modules.identity.permissions import P
from app.modules.ingestion.models import ImportJob, ImportRow
from app.modules.ingestion.service import ImportService

router = APIRouter(prefix="/api/v1/admin/imports", tags=["imports"])

ImportKind = Literal["students"]
ImportStatus = Literal[
    "uploaded",
    "parsing",
    "needs_mapping",
    "validating",
    "validated",
    "committing",
    "committed",
    "failed",
    "cancelled",
]


class FieldOut(BaseModel):
    key: str
    label: str
    required: bool
    help: str


class IssueOut(BaseModel):
    code: str
    severity: Literal["error", "warning", "info"]
    msg: str
    field: str | None = None


class ImportOut(BaseModel):
    id: uuid.UUID
    kind: ImportKind
    status: ImportStatus
    file_name: str | None
    created_at: datetime
    updated_at: datetime
    created_by_name: str | None
    committed_at: datetime | None
    committed_by_name: str | None
    params: dict[str, Any]
    sheet_name: str | None
    sheets: list[str]
    columns: list[str]
    header_row: int | None
    mapping: dict[str, int]
    fields: list[FieldOut]
    file_issues: list[IssueOut]
    rows_total: int
    rows_valid: int
    rows_warning: int
    rows_error: int
    summary: dict[str, Any]
    error_code: str | None
    error_detail: str | None
    supersedes_id: uuid.UUID | None
    resumed: bool = False


class ImportListItem(BaseModel):
    id: uuid.UUID
    kind: ImportKind
    status: ImportStatus
    file_name: str | None
    created_at: datetime
    created_by_name: str | None
    rows_total: int
    rows_error: int
    summary: dict[str, Any]


class RowOut(BaseModel):
    row_no: int
    raw: list[str]
    normalized: dict[str, Any] | None
    issues: list[IssueOut]
    status: Literal["pending", "valid", "warning", "error", "skipped"]


class RowsPage(BaseModel):
    items: list[RowOut]
    next_after: int | None


class MappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mapping: dict[str, int | None] = Field(max_length=50)
    header_row: int | None = Field(default=None, ge=1, le=1000)
    sheet_name: str | None = Field(default=None, max_length=100)


class CommitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skip_errors: bool = False


SAFE_PARAMS = ("mode", "session_id", "skip_errors")


async def _out(uow: Any, service: ImportService, job: ImportJob, *, resumed: bool = False) -> ImportOut:
    await uow.flush()
    await uow.session.refresh(job)  # server-side timestamps after the UPDATE
    names = await service.user_names(uow, {job.created_by, job.committed_by})
    summary = dict(job.summary or {})
    return ImportOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        file_name=job.file_name,
        created_at=job.created_at,
        updated_at=job.updated_at,
        created_by_name=names.get(job.created_by) if job.created_by else None,
        committed_at=job.committed_at,
        committed_by_name=names.get(job.committed_by) if job.committed_by else None,
        params={k: v for k, v in (job.params or {}).items() if k in SAFE_PARAMS},
        sheet_name=job.sheet_name,
        sheets=summary.pop("sheets", []),
        columns=job.columns or [],
        header_row=job.header_row,
        mapping=job.mapping or {},
        fields=[
            FieldOut(key=f.key, label=f.label, required=f.required, help=f.help)
            for f in service.profile(job.kind).fields
        ],
        file_issues=[IssueOut(**i) for i in job.file_issues or []],
        rows_total=job.rows_total,
        rows_valid=job.rows_valid,
        rows_warning=job.rows_warning,
        rows_error=job.rows_error,
        summary=summary,
        error_code=job.error_code,
        error_detail=job.error_detail,
        supersedes_id=job.supersedes_id,
        resumed=resumed,
    )


def _xlsx(data: bytes, filename: str) -> Response:
    ascii_name = filename.encode("ascii", "ignore").decode() or "download.xlsx"
    return Response(
        content=data,
        media_type=XLSX.content_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


@router.post("", status_code=202)
async def upload_import(
    uow: UoW,
    infra: InfraDep,
    file: UploadFile = File(...),
    kind: ImportKind = Form(...),
    mode: Literal["upsert", "create_only"] = Form("upsert"),
    session_id: uuid.UUID | None = Form(None),
    supersedes_id: uuid.UUID | None = Form(None),
    principal: Principal = require(P.IMPORTS_MANAGE),
) -> ImportOut:
    data = await file.read(infra.settings.max_upload_bytes + 1)
    service = ImportService(infra)
    result = await service.upload(
        uow,
        principal,
        kind=kind,
        data=data,
        filename=file.filename,
        params={"mode": mode, "session_id": session_id},
        supersedes_id=supersedes_id,
    )
    return await _out(uow, service, result.job, resumed=result.resumed)


@router.get("")
async def list_imports(
    uow: UoW,
    infra: InfraDep,
    kind: ImportKind | None = None,
    _: Principal = require(P.IMPORTS_MANAGE),
) -> list[ImportListItem]:
    service = ImportService(infra)
    jobs = await service.recent(uow, kind)
    names = await service.user_names(uow, {j.created_by for j in jobs})
    return [
        ImportListItem(
            id=j.id,
            kind=j.kind,
            status=j.status,
            file_name=j.file_name,
            created_at=j.created_at,
            created_by_name=names.get(j.created_by) if j.created_by else None,
            rows_total=j.rows_total,
            rows_error=j.rows_error,
            summary={k: v for k, v in (j.summary or {}).items() if k != "sheets"},
        )
        for j in jobs
    ]


@router.get("/template.xlsx")
async def download_template(
    uow: UoW, infra: InfraDep, kind: ImportKind = "students", _: Principal = require(P.IMPORTS_MANAGE)
) -> Response:
    data, name = await ImportService(infra).template(uow, kind)
    return _xlsx(data, name)


@router.get("/{import_id}")
async def get_import(
    import_id: uuid.UUID, uow: UoW, infra: InfraDep, _: Principal = require(P.IMPORTS_MANAGE)
) -> ImportOut:
    service = ImportService(infra)
    return await _out(uow, service, await service.get(uow, import_id))


@router.get("/{import_id}/rows")
async def list_import_rows(
    import_id: uuid.UUID,
    uow: UoW,
    infra: InfraDep,
    status: Literal["valid", "warning", "error", "skipped", "problems"] | None = None,
    after: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=1, le=200),
    _: Principal = require(P.IMPORTS_MANAGE),
) -> RowsPage:
    rows, next_after = await ImportService(infra).rows(
        uow, import_id, status=status, after=after, limit=limit
    )
    return RowsPage(items=[_row(r) for r in rows], next_after=next_after)


def _row(r: ImportRow) -> RowOut:
    return RowOut(
        row_no=r.row_no,
        raw=[str(c) for c in r.raw],
        normalized=r.normalized,
        issues=[IssueOut(**i) for i in r.issues or []],
        status=r.status,
    )


@router.put("/{import_id}/mapping", status_code=202)
async def set_mapping(
    import_id: uuid.UUID,
    body: MappingIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.IMPORTS_MANAGE),
) -> ImportOut:
    service = ImportService(infra)
    job = await service.set_mapping(
        uow,
        principal,
        import_id,
        mapping=body.mapping,
        header_row=body.header_row,
        sheet_name=body.sheet_name,
    )
    return await _out(uow, service, job)


@router.post("/{import_id}/revalidate", status_code=202)
async def revalidate(
    import_id: uuid.UUID, uow: UoW, infra: InfraDep, principal: Principal = require(P.IMPORTS_MANAGE)
) -> ImportOut:
    service = ImportService(infra)
    return await _out(uow, service, await service.revalidate(uow, principal, import_id))


@router.post("/{import_id}/commit", status_code=202)
async def commit_import(
    import_id: uuid.UUID,
    body: CommitIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.IMPORTS_MANAGE),
) -> ImportOut:
    service = ImportService(infra)
    job = await service.request_commit(uow, principal, import_id, skip_errors=body.skip_errors)
    return await _out(uow, service, job)


@router.post("/{import_id}/cancel")
async def cancel_import(
    import_id: uuid.UUID, uow: UoW, infra: InfraDep, principal: Principal = require(P.IMPORTS_MANAGE)
) -> ImportOut:
    service = ImportService(infra)
    return await _out(uow, service, await service.cancel(uow, principal, import_id))


@router.get("/{import_id}/report.xlsx")
async def download_report(
    import_id: uuid.UUID, uow: UoW, infra: InfraDep, _: Principal = require(P.IMPORTS_MANAGE)
) -> Response:
    data, name = await ImportService(infra).error_report(uow, import_id)
    return _xlsx(data, name)
