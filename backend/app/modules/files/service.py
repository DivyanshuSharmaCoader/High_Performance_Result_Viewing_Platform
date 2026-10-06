"""File uploads and generated files (docs/10 §6): allow-listed types, magic-byte sniffing, size caps,
tenant-prefixed object keys, storage accounting, signed download URLs."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import NotFound, PayloadTooLarge, UnsupportedMedia
from app.core.storage import tenant_object_key
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EntitlementService
from app.modules.files.models import StoredFile


@dataclass(frozen=True)
class FileType:
    extension: str
    content_type: str


PNG = FileType(".png", "image/png")
JPEG = FileType(".jpg", "image/jpeg")
WEBP = FileType(".webp", "image/webp")
XLSX = FileType(".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
CSV = FileType(".csv", "text/csv")
PDF = FileType(".pdf", "application/pdf")

IMAGE_TYPES = (PNG, JPEG, WEBP)
SPREADSHEET_TYPES = (XLSX, CSV)


def sniff(data: bytes) -> FileType | None:
    """Identify a file by its leading bytes; extensions and client content-types are never trusted."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return WEBP
    if data.startswith(b"%PDF-"):
        return PDF
    if data.startswith(b"PK\x03\x04"):
        # OOXML container; confirmed as a workbook by the parser ([Content_Types].xml, no macros).
        return XLSX
    head = data[:4096]
    if b"\x00" in head:
        return None
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        try:
            head.decode("cp1252")
        except UnicodeDecodeError:
            return None
    lowered = head.lstrip().lower()
    if lowered.startswith((b"<svg", b"<?xml", b"<!doctype", b"<html", b"<script")):
        return None  # markup is never accepted (SVG/HTML can carry scripts)
    return CSV


def validate_upload(data: bytes, allowed: tuple[FileType, ...], max_bytes: int) -> FileType:
    if len(data) == 0:
        raise UnsupportedMedia("The file is empty.")
    if len(data) > max_bytes:
        raise PayloadTooLarge(f"Files can be at most {max_bytes // (1024 * 1024)} MB.", max_bytes=max_bytes)
    kind = sniff(data)
    if kind is None or kind not in allowed:
        names = ", ".join(t.extension.lstrip(".").upper() for t in allowed)
        raise UnsupportedMedia(f"This file type isn't supported. Upload one of: {names}.")
    return kind


class FileService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    async def store(
        self,
        uow: UnitOfWork,
        *,
        data: bytes,
        kind: str,
        file_type: FileType,
        original_name: str | None,
        uploaded_by: uuid.UUID | None,
    ) -> StoredFile:
        tenant_id = uow.require_tenant()
        await EntitlementService(self.infra).consume(uow, F.MAX_STORAGE_MB, len(data))
        key = tenant_object_key(tenant_id, kind, file_type.extension)
        record = StoredFile(
            tenant_id=tenant_id,
            object_key=key,
            kind=kind,
            content_type=file_type.content_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).digest(),
            original_name=(original_name or "")[:255] or None,
            uploaded_by=uploaded_by,
        )
        uow.session.add(record)
        await uow.flush()
        # Write bytes before commit: if the upload fails the transaction rolls back (no dangling row).
        await self.infra.storage.put(key, data, file_type.content_type)
        return record

    async def get(self, uow: UnitOfWork, file_id: uuid.UUID) -> StoredFile:
        row = (await uow.session.scalars(select(StoredFile).where(StoredFile.id == file_id))).one_or_none()
        if row is None:
            raise NotFound("File not found")
        return row

    async def read_bytes(self, uow: UnitOfWork, file_id: uuid.UUID) -> bytes:
        return await self.infra.storage.get((await self.get(uow, file_id)).object_key)

    def signed_url(self, stored: StoredFile, *, filename: str | None = None, ttl_s: int | None = None) -> str:
        return self.infra.storage.presigned_get(stored.object_key, filename=filename, ttl_s=ttl_s)
