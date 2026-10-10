"""Marksheets: created with each publication, rendered by the ``pdf`` worker, downloaded through
short-lived signed URLs (docs/03 W10, W12; P11.2–P11.3).

* ``prepare`` runs inside the publication's transaction: a pending document and a verification code per
  student, and render jobs in chunks. Nothing is reachable until the publication is live. A scheduled
  publication renders ahead of go-live, so result day itself does no PDF work.
* ``render`` (the job) reads what it needs in one short transaction, lays out each PDF in a worker thread
  without holding a database connection, then stores each file in its own transaction. A failure is
  retried by the job; documents already rendered are skipped. After the last attempt a document is
  ``failed``, and administrators can retry.
* Downloads are signed object-storage URLs that expire in two minutes. A student's is located only through
  the student linked to their session.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any, cast

import anyio
from sqlalchemy import Table, func, insert, select, update

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import NotFound
from app.core.http import Principal
from app.core.jobs import enqueue
from app.core.logging import get_logger
from app.modules.branding.models import TenantBranding
from app.modules.documents.labels import language_of
from app.modules.documents.models import MarksheetDocument
from app.modules.documents.pool import pool as pdf_pool
from app.modules.documents.render import (
    TEMPLATE_CODE,
    TEMPLATE_VERSION,
    Branding,
    RenderResult,
    render_marksheet,
)
from app.modules.files.service import PDF, FileService
from app.modules.publishing.models import Publication, PublishedResult
from app.modules.publishing.read_cache import LivePublication
from app.modules.tenancy.models import Tenant, TenantSettings
from app.modules.verification.codes import grouped, new_code
from app.modules.verification.models import VerificationRecord

log = get_logger("scorecode.marksheets")

RENDER_CHUNK = 50  # students per job: a few seconds of work, well inside the job lease
INSERT_CHUNK = 1000
DOWNLOAD_TTL_S = 120
DOCS = cast(Table, MarksheetDocument.__table__)
CODES = cast(Table, VerificationRecord.__table__)


@dataclass(frozen=True)
class Progress:
    total: int = 0
    rendered: int = 0
    pending: int = 0
    failed: int = 0


@dataclass(frozen=True)
class MarksheetLink:
    status: str  # pending | rendered | failed
    url: str | None = None
    filename: str | None = None
    expires_in: int | None = None


def verify_url(infra: Infra, code: str) -> str:
    settings = infra.settings
    return f"{settings.public_origin(settings.verify_host)}/v/{code}"


def download_name(payload: dict[str, Any], version: int) -> str:
    def part(text: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:60] or "x"

    exam = payload["exam"]
    name = (
        f"Marksheet-{part(payload['student']['enrollment_no'])}-{part(exam['name'])}-{part(exam['session'])}"
    )
    return f"{name}{f'-v{version}' if version > 1 else ''}.pdf"


class MarksheetService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    # ---- with the publication -------------------------------------------------------------------
    async def prepare(
        self,
        uow: UnitOfWork,
        publication_id: uuid.UUID,
        student_ids: Sequence[uuid.UUID],
        created_by: uuid.UUID | None,
    ) -> None:
        tid = uow.require_tenant()
        base = {"tenant_id": tid, "publication_id": publication_id}
        docs = [
            {**base, "student_id": s, "template_code": TEMPLATE_CODE, "template_version": TEMPLATE_VERSION}
            for s in student_ids
        ]
        codes = [{**base, "student_id": s, "code": new_code()} for s in student_ids]
        for i in range(0, len(docs), INSERT_CHUNK):
            await uow.session.execute(insert(DOCS), docs[i : i + INSERT_CHUNK])
            await uow.session.execute(insert(CODES), codes[i : i + INSERT_CHUNK])
        await self._enqueue(uow, publication_id, list(student_ids), created_by, tag="first")

    async def _enqueue(
        self,
        uow: UnitOfWork,
        publication_id: uuid.UUID,
        student_ids: list[uuid.UUID],
        created_by: uuid.UUID | None,
        *,
        tag: str,
    ) -> int:
        jobs = 0
        for i in range(0, len(student_ids), RENDER_CHUNK):
            chunk = student_ids[i : i + RENDER_CHUNK]
            await enqueue(
                uow,
                "documents.render",
                {"publication_id": str(publication_id), "students": [str(s) for s in chunk]},
                dedupe_key=f"marksheets:{publication_id}:{tag}:{i // RENDER_CHUNK}",
                created_by=created_by,
            )
            jobs += 1
        return jobs

    # ---- the pdf worker -------------------------------------------------------------------------
    async def render(
        self,
        tenant_id: uuid.UUID,
        publication_id: uuid.UUID,
        student_ids: list[uuid.UUID],
        *,
        final_attempt: bool,
    ) -> dict[str, Any]:
        async with self.infra.db.uow(tenant_id) as uow:
            pub = (
                await uow.session.scalars(select(Publication).where(Publication.id == publication_id))
            ).one()
            if pub.status == "cancelled":
                return {"skipped": "cancelled"}
            work = (
                await uow.session.execute(
                    select(PublishedResult.student_id, PublishedResult.payload, VerificationRecord.code)
                    .join(
                        MarksheetDocument,
                        (MarksheetDocument.publication_id == PublishedResult.publication_id)
                        & (MarksheetDocument.student_id == PublishedResult.student_id),
                    )
                    .join(
                        VerificationRecord,
                        (VerificationRecord.publication_id == PublishedResult.publication_id)
                        & (VerificationRecord.student_id == PublishedResult.student_id),
                    )
                    .where(
                        PublishedResult.publication_id == publication_id,
                        PublishedResult.student_id.in_(student_ids),
                        MarksheetDocument.status != "rendered",
                    )
                )
            ).all()
            branding = await self._branding(uow)
            timezone = (await uow.session.scalars(select(Tenant.timezone))).one()
            # Hindi or Punjabi makes the marksheet bilingual (decision D29).
            language = language_of((await uow.session.scalars(select(TenantSettings.locale))).one())
        issued_at: datetime = pub.published_at or pub.scheduled_at or utcnow()
        processes = self.infra.settings.pdf_processes
        outcome = {"rendered": 0, "failed": 0}

        async def layout(payload: dict[str, Any], code: str) -> RenderResult:
            job = partial(
                render_marksheet,
                payload,
                branding=branding,
                verify_url=verify_url(self.infra, code),
                code_display=grouped(code),
                version=pub.version,
                issued_at=issued_at,
                timezone=timezone,
                language=language,
            )
            if processes > 0:
                return await asyncio.get_running_loop().run_in_executor(pdf_pool(processes), job)
            return await anyio.to_thread.run_sync(job)

        async def one(student_id: uuid.UUID, payload: dict[str, Any], code: str) -> None:
            try:
                result = await layout(payload, code)
                if result.refused:  # the built-in template never asks for one; worth knowing if it does
                    log.warning("marksheet_external_resource_refused", count=len(result.refused))
                async with self.infra.db.uow(tenant_id) as uow:
                    stored = await FileService(self.infra).store(
                        uow,
                        data=result.pdf,
                        kind="marksheet",
                        file_type=PDF,
                        original_name=download_name(payload, pub.version),
                        uploaded_by=None,
                        enforce_quota=False,  # bounded by the student and publication caps (docs/12 §4)
                    )
                    await uow.session.execute(
                        self._doc(publication_id, student_id).values(
                            status="rendered",
                            file_id=stored.id,
                            sha256=hashlib.sha256(result.pdf).hexdigest(),
                            rendered_at=utcnow(),
                            attempts=MarksheetDocument.attempts + 1,
                            last_error=None,
                        )
                    )
                outcome["rendered"] += 1
            except Exception as exc:
                outcome["failed"] += 1
                log.exception("marksheet_render_failed", publication_id=str(publication_id))
                async with self.infra.db.uow(tenant_id) as uow:
                    await uow.session.execute(
                        self._doc(publication_id, student_id).values(
                            status="failed" if final_attempt else "pending",
                            attempts=MarksheetDocument.attempts + 1,
                            last_error=type(exc).__name__,  # no message: it could quote student data
                        )
                    )

        # As many at once as there are layout processes; each is stored as soon as it's ready.
        limiter = anyio.CapacityLimiter(max(1, processes))

        async def limited(student_id: uuid.UUID, payload: dict[str, Any], code: str) -> None:
            async with limiter:
                await one(student_id, payload, code)

        async with anyio.create_task_group() as tg:
            for student_id, payload, code in work:
                tg.start_soon(limited, student_id, payload, code)
        rendered, failed = outcome["rendered"], outcome["failed"]
        if failed and not final_attempt:
            raise RuntimeError(f"{failed} of {len(work)} marksheets failed; the job will retry them")
        return {"rendered": rendered, "failed": failed}

    @staticmethod
    def _doc(publication_id: uuid.UUID, student_id: uuid.UUID) -> Any:
        return update(MarksheetDocument).where(
            MarksheetDocument.publication_id == publication_id, MarksheetDocument.student_id == student_id
        )

    async def _branding(self, uow: UnitOfWork) -> Branding:
        settings = (await uow.session.scalars(select(TenantSettings))).one()
        brand = (await uow.session.scalars(select(TenantBranding))).one_or_none()
        logo = None
        if brand is not None and brand.logo_file_id is not None:
            try:
                logo = await FileService(self.infra).read_bytes(uow, brand.logo_file_id)
            except Exception:
                log.warning("marksheet_logo_unavailable")  # a marksheet without the logo beats none
        return Branding(
            address=settings.address,
            affiliation=settings.affiliation,
            color=brand.primary_color if brand else "#2952cc",
            logo=logo,
            footer_text=brand.footer_text if brand else None,
            show_powered_by=brand.show_powered_by if brand else True,
        )

    # ---- administrators -------------------------------------------------------------------------
    @staticmethod
    async def progress(uow: UnitOfWork, publication_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Progress]:
        counts: dict[uuid.UUID, dict[str, int]] = {}
        for pid, status, n in (
            await uow.session.execute(
                select(MarksheetDocument.publication_id, MarksheetDocument.status, func.count())
                .where(MarksheetDocument.publication_id.in_(publication_ids))
                .group_by(MarksheetDocument.publication_id, MarksheetDocument.status)
            )
        ).all():
            counts.setdefault(pid, {})[status] = n
        return {
            pid: Progress(
                total=sum(c.values()), **{k: c.get(k, 0) for k in ("rendered", "pending", "failed")}
            )
            for pid, c in counts.items()
        }

    async def retry_failed(self, uow: UnitOfWork, principal: Principal, publication_id: uuid.UUID) -> int:
        failed = list(
            (
                await uow.session.scalars(
                    select(MarksheetDocument.student_id).where(
                        MarksheetDocument.publication_id == publication_id,
                        MarksheetDocument.status == "failed",
                    )
                )
            ).all()
        )
        if not failed:
            return 0
        await uow.session.execute(
            update(MarksheetDocument)
            .where(MarksheetDocument.publication_id == publication_id, MarksheetDocument.status == "failed")
            .values(status="pending")
        )
        await self._enqueue(
            uow, publication_id, failed, principal.user_id, tag=f"retry-{uuid.uuid4().hex[:8]}"
        )
        return len(failed)

    async def link(
        self,
        uow: UnitOfWork,
        publication: Publication | LivePublication,
        student_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> MarksheetLink:
        doc = (
            await uow.session.scalars(
                select(MarksheetDocument).where(
                    MarksheetDocument.publication_id == publication.id,
                    MarksheetDocument.student_id == student_id,
                )
            )
        ).one_or_none()
        if doc is None:
            raise NotFound("There's no marksheet for this result.")
        if doc.status != "rendered" or doc.file_id is None:
            return MarksheetLink(status=doc.status)
        stored = await FileService(self.infra).get(uow, doc.file_id)
        filename = download_name(payload, publication.version)
        return MarksheetLink(
            status="rendered",
            url=FileService(self.infra).signed_url(stored, filename=filename, ttl_s=DOWNLOAD_TTL_S),
            filename=filename,
            expires_in=DOWNLOAD_TTL_S,
        )
