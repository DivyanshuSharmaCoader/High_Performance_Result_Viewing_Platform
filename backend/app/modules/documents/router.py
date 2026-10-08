"""Marksheet downloads and administration (P11.3, P11.4).

Students reach only their own marksheet: the student comes from the session, never from the request. Every
link is a signed object-storage URL that expires in two minutes, so a copied link soon stops working.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.errors import NotFound
from app.core.http import InfraDep, Principal, UoW, require
from app.modules.documents.service import MarksheetLink, MarksheetService, verify_url
from app.modules.identity.permissions import P
from app.modules.publishing.models import Publication, PublishedResult
from app.modules.publishing.router import NO_STORE
from app.modules.publishing.service import PublishingService
from app.modules.verification.codes import grouped
from app.modules.verification.service import VerificationService

student_router = APIRouter(prefix="/api/v1/me/results", tags=["my results"])
admin_router = APIRouter(
    prefix="/api/v1/admin/exams/{exam_id}/publications/{publication_id}", tags=["publications"]
)


class VerificationOut(BaseModel):
    code: str = Field(description="Grouped for display, e.g. 7KQ3-M9XD-…")
    url: str


class MarksheetOut(BaseModel):
    status: Literal["pending", "rendered", "failed"]
    url: str | None = Field(
        default=None, description="Signed download link; expires after expires_in seconds"
    )
    filename: str | None = None
    expires_in: int | None = None
    verification: VerificationOut | None = None


class RetryOut(BaseModel):
    queued: int


class RevokeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=1000)


class RevokedOut(BaseModel):
    revoked: bool = True


def _out(link: MarksheetLink, code: str | None, infra: InfraDep) -> MarksheetOut:
    return MarksheetOut(
        status=link.status,
        url=link.url,
        filename=link.filename,
        expires_in=link.expires_in,
        verification=VerificationOut(code=grouped(code), url=verify_url(infra, code)) if code else None,
    )


@student_router.get("/{publication_id}/marksheet")
async def my_marksheet(
    publication_id: uuid.UUID,
    response: Response,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.ME_RESULTS),
) -> MarksheetOut:
    response.headers["Cache-Control"] = NO_STORE
    publishing = PublishingService(infra)
    mine = await publishing.my_result(uow, principal, publication_id)  # 404 unless live and this student's
    student_id = await publishing.student_id(uow, principal)
    link = await MarksheetService(infra).link(uow, mine.publication, student_id, mine.payload)
    code = await VerificationService.code_for(uow, publication_id, student_id)
    return _out(link, code, infra)


async def _publication(uow: UoW, exam_id: uuid.UUID, publication_id: uuid.UUID) -> Publication:
    pub = (
        await uow.session.scalars(
            select(Publication).where(Publication.id == publication_id, Publication.exam_id == exam_id)
        )
    ).one_or_none()
    if pub is None:
        raise NotFound("Publication not found")
    return pub


@admin_router.get("/marksheets/{student_id}")
async def student_marksheet(
    exam_id: uuid.UUID,
    publication_id: uuid.UUID,
    student_id: uuid.UUID,
    response: Response,
    uow: UoW,
    infra: InfraDep,
    _: Principal = require(P.RESULTS_VIEW),
) -> MarksheetOut:
    response.headers["Cache-Control"] = NO_STORE
    pub = await _publication(uow, exam_id, publication_id)
    payload = (
        await uow.session.scalars(
            select(PublishedResult.payload).where(
                PublishedResult.publication_id == pub.id, PublishedResult.student_id == student_id
            )
        )
    ).one_or_none()
    if payload is None:
        raise NotFound("This student isn't in this publication.")
    link = await MarksheetService(infra).link(uow, pub, student_id, payload)
    return _out(link, await VerificationService.code_for(uow, pub.id, student_id), infra)


@admin_router.post("/marksheets/retry")
async def retry_marksheets(
    exam_id: uuid.UUID,
    publication_id: uuid.UUID,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.PUBLICATIONS_MANAGE),
) -> RetryOut:
    pub = await _publication(uow, exam_id, publication_id)
    return RetryOut(queued=await MarksheetService(infra).retry_failed(uow, principal, pub.id))


@admin_router.post("/verification/{student_id}/revoke")
async def revoke_verification(
    exam_id: uuid.UUID,
    publication_id: uuid.UUID,
    student_id: uuid.UUID,
    body: RevokeIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.PUBLICATIONS_MANAGE),
) -> RevokedOut:
    pub = await _publication(uow, exam_id, publication_id)
    await VerificationService(infra).revoke(uow, principal, pub.id, student_id, body.reason)
    return RevokedOut()
