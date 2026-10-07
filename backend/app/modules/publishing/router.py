from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.http import InfraDep, Principal, UoW, require
from app.core.idempotency import idempotent
from app.modules.identity.permissions import P
from app.modules.publishing.models import Publication
from app.modules.publishing.service import MyResult, PublishingService

admin_router = APIRouter(prefix="/api/v1/admin/exams/{exam_id}/publications", tags=["publications"])
student_router = APIRouter(prefix="/api/v1/me/results", tags=["my results"])

PublicationStatus = Literal["scheduled", "published", "superseded", "withdrawn", "cancelled"]
NO_STORE = (
    "private, no-store"  # personal results on shared computers: never kept by the browser (docs/11 §2.6)
)


class PublicationOut(BaseModel):
    id: uuid.UUID
    version: int
    status: PublicationStatus
    scheduled_at: datetime | None
    published_at: datetime | None
    withdrawn_at: datetime | None
    withdraw_reason: str | None
    students: int
    content_hash: str
    created_at: datetime


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at: datetime | None = Field(default=None, description="Go live at this time; omit to publish now.")


class PublicationReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=1000)


# ---- the student-facing snapshot (payload schema 1) ------------------------------------------------
class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SnapComponent(_Strict):
    code: str
    label: str
    max: str | None
    marks: str | None


class SnapPaper(_Strict):
    course_code: str
    course_name: str
    credits: str | None
    attendance: str | None
    outcome: str
    total: str | None
    max_total: str | None
    percentage: str | None
    grade: str | None
    grade_point: str | None
    failed_components: list[str]
    missing_components: list[str]
    components: list[SnapComponent]


class SnapResult(_Strict):
    outcome: Literal["pass", "fail", "absent", "withheld", "incomplete"]
    total: str | None
    max_total: str | None
    percentage: str | None
    grade: str | None
    grade_point: str | None
    sgpa: str | None
    credits_attempted: str | None
    credits_earned: str | None
    rank: int | None
    notes: list[str]


class SnapCohort(_Strict):
    code: str
    name: str


class SnapStudent(_Strict):
    enrollment_no: str
    full_name: str
    cohort: SnapCohort
    program: str | None


class SnapExam(_Strict):
    name: str
    kind: str
    term: str
    session: str


class SnapInstitution(_Strict):
    name: str
    display_name: str


class SnapScheme(_Strict):
    name: str
    strategy: str


class ResultPayload(_Strict):
    schema_: int = Field(alias="schema")
    institution: SnapInstitution
    exam: SnapExam
    scheme: SnapScheme
    student: SnapStudent
    result: SnapResult
    papers: list[SnapPaper]


class MyResultOut(BaseModel):
    publication_id: uuid.UUID
    version: int
    published_at: datetime
    revised: bool
    payload: ResultPayload


class MyResultItem(BaseModel):
    publication_id: uuid.UUID
    published_at: datetime
    revised: bool
    exam: SnapExam
    outcome: str
    percentage: str | None
    grade: str | None
    sgpa: str | None


class MyStatsOut(BaseModel):
    available: bool
    stats: dict[str, Any] | None = None


def _pub(p: Publication) -> PublicationOut:
    return PublicationOut(
        id=p.id,
        version=p.version,
        status=p.status,
        scheduled_at=p.scheduled_at,
        published_at=p.published_at,
        withdrawn_at=p.withdrawn_at,
        withdraw_reason=p.withdraw_reason,
        students=p.students,
        content_hash=p.content_hash,
        created_at=p.created_at,
    )


def _mine(r: MyResult) -> MyResultOut:
    assert r.publication.published_at is not None
    return MyResultOut(
        publication_id=r.publication.id,
        version=r.publication.version,
        published_at=r.publication.published_at,
        revised=r.revised,
        payload=ResultPayload.model_validate(r.payload),
    )


# ---- administrators ---------------------------------------------------------------------------------
@admin_router.get("")
async def list_publications(
    exam_id: uuid.UUID, uow: UoW, infra: InfraDep, _: Principal = require(P.RESULTS_VIEW)
) -> list[PublicationOut]:
    service = PublishingService(infra)
    await service.exam(uow, exam_id)
    return [_pub(p) for p in await service.publications(uow, exam_id)]


@admin_router.post("", status_code=201, response_model=PublicationOut)
async def publish_results(
    exam_id: uuid.UUID,
    body: PublishIn,
    request: Request,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.PUBLICATIONS_MANAGE),
) -> Any:
    service = PublishingService(infra)
    await service.exam(uow, exam_id)  # another tenant's (or no) exam is a 404 before anything else

    async def work() -> PublicationOut:
        pub = await service.publish(uow, principal, exam_id, at=body.at)
        await uow.flush()
        await uow.session.refresh(pub)
        return _pub(pub)

    return await idempotent(uow, request, body.model_dump(mode="json"), work, status_code=201)


@admin_router.post("/{publication_id}/cancel")
async def cancel_publication(
    exam_id: uuid.UUID,
    publication_id: uuid.UUID,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.PUBLICATIONS_MANAGE),
) -> PublicationOut:
    pub = await PublishingService(infra).cancel(uow, principal, exam_id, publication_id)
    return _pub(pub)


@admin_router.post("/{publication_id}/withdraw")
async def withdraw_publication(
    exam_id: uuid.UUID,
    publication_id: uuid.UUID,
    body: PublicationReasonIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.PUBLICATIONS_MANAGE),
) -> PublicationOut:
    pub = await PublishingService(infra).withdraw(uow, principal, exam_id, publication_id, body.reason)
    return _pub(pub)


# ---- students (identity from the session only) --------------------------------------------------------
@student_router.get("")
async def my_results(
    response: Response, uow: UoW, infra: InfraDep, principal: Principal = require(P.ME_RESULTS)
) -> list[MyResultItem]:
    response.headers["Cache-Control"] = NO_STORE
    out = []
    for r in await PublishingService(infra).my_results(uow, principal):
        p = ResultPayload.model_validate(r.payload)
        assert r.publication.published_at is not None
        out.append(
            MyResultItem(
                publication_id=r.publication.id,
                published_at=r.publication.published_at,
                revised=r.revised,
                exam=p.exam,
                outcome=p.result.outcome,
                percentage=p.result.percentage,
                grade=p.result.grade,
                sgpa=p.result.sgpa,
            )
        )
    return out


@student_router.get("/latest")
async def my_latest_result(
    response: Response, uow: UoW, infra: InfraDep, principal: Principal = require(P.ME_RESULTS)
) -> MyResultOut | None:
    response.headers["Cache-Control"] = NO_STORE
    results = await PublishingService(infra).my_results(uow, principal)
    return _mine(results[0]) if results else None


@student_router.get("/{publication_id}")
async def my_result(
    publication_id: uuid.UUID,
    response: Response,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.ME_RESULTS),
) -> MyResultOut:
    response.headers["Cache-Control"] = NO_STORE
    return _mine(await PublishingService(infra).my_result(uow, principal, publication_id))


@student_router.get("/{publication_id}/stats")
async def my_result_stats(
    publication_id: uuid.UUID,
    response: Response,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.ME_RESULTS),
) -> MyStatsOut:
    response.headers["Cache-Control"] = NO_STORE
    stats = await PublishingService(infra).my_stats(uow, principal, publication_id)
    return MyStatsOut(available=stats is not None, stats=stats)
