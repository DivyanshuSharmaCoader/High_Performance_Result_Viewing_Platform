from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.http import InfraDep, Principal, UoW, require
from app.modules.examinations.service import ExamService, ExamView
from app.modules.examinations.states import available
from app.modules.identity.permissions import P

router = APIRouter(prefix="/api/v1/admin/exams", tags=["exams"])

ExamKind = Literal["unit_test", "term", "semester", "supplementary", "other"]
ExamStatusLit = Literal[
    "draft",
    "marks_entry_open",
    "marks_entry_closed",
    "processed",
    "approved",
    "scheduled",
    "published",
    "correction_draft",
    "withdrawn",
    "archived",
]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ExamCreateIn(In):
    name: str = Field(min_length=1, max_length=150)
    kind: ExamKind = "term"
    term_id: uuid.UUID
    grading_scheme_id: uuid.UUID | None = None
    cohort_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    marks_deadline: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ExamUpdateIn(In):
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=150)
    kind: ExamKind
    grading_scheme_id: uuid.UUID
    marks_deadline: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ExamCohortsIn(In):
    cohort_ids: list[uuid.UUID] = Field(max_length=200)


class ExamComponentIn(In):
    code: str = Field(min_length=1, max_length=12)
    label: str = Field(min_length=1, max_length=40)
    max: Decimal
    min_pass: Decimal | None = None


class ExamPaperIn(In):
    components: list[ExamComponentIn] = Field(min_length=1, max_length=10)
    pass_total: Decimal | None = Field(default=None, ge=0)
    credits: Decimal | None = Field(default=None, ge=0, le=40)


class ExamPaperCreateIn(ExamPaperIn):
    course_id: uuid.UUID
    use_course_credits: bool = True


class ExamAssignmentsIn(In):
    cohort_id: uuid.UUID
    user_ids: list[uuid.UUID] = Field(max_length=20)


class ExamTransitionIn(In):
    action: Literal["open_entry", "close_entry", "reopen_entry"]
    reason: str | None = Field(default=None, max_length=500)


class ExamTermRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    session_id: uuid.UUID
    session_code: str


class ExamListItem(BaseModel):
    id: uuid.UUID
    name: str
    kind: ExamKind
    status: ExamStatusLit
    term: ExamTermRef
    grading_scheme_name: str
    papers: int
    cohorts: int
    marks_deadline: datetime | None
    updated_at: datetime


class ExamCohortOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    program_code: str
    students: int


class ExamComponentOut(BaseModel):
    code: str
    label: str
    max: Decimal
    min_pass: Decimal | None


class ExamAssignmentOut(BaseModel):
    cohort_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str


class ExamSubmissionOut(BaseModel):
    cohort_id: uuid.UUID
    status: Literal["open", "submitted", "returned", "locked"]
    submitted_at: datetime | None


class ExamPaperOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    course_code: str
    course_name: str
    position: int
    components: list[ExamComponentOut]
    max_total: Decimal
    pass_total: Decimal | None
    credits: Decimal | None
    assignments: list[ExamAssignmentOut]
    submissions: list[ExamSubmissionOut]


class ExamCheckOut(BaseModel):
    key: str
    ok: bool
    message: str


class ExamActionOut(BaseModel):
    action: str
    label: str
    needs_reason: bool


class ExamOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: ExamKind
    status: ExamStatusLit
    version: int
    term: ExamTermRef
    grading_scheme_id: uuid.UUID
    grading_scheme_name: str
    grading_scheme_version_id: uuid.UUID | None
    marks_deadline: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    cohorts: list[ExamCohortOut]
    papers: list[ExamPaperOut]
    checks: list[ExamCheckOut]
    actions: list[ExamActionOut]


def _term(term: Any, session: Any) -> ExamTermRef:
    return ExamTermRef(
        id=term.id, code=term.code, name=term.name, session_id=session.id, session_code=session.code
    )


async def _out(uow: Any, service: ExamService, exam_id: uuid.UUID) -> ExamOut:
    await uow.flush()
    view: ExamView = await service.detail(uow, exam_id)
    await uow.session.refresh(view.exam)
    e = view.exam
    return ExamOut(
        id=e.id,
        name=e.name,
        kind=e.kind,
        status=e.status,
        version=e.version,
        term=_term(view.term, view.session),
        grading_scheme_id=e.grading_scheme_id,
        grading_scheme_name=view.scheme.name,
        grading_scheme_version_id=e.grading_scheme_version_id,
        marks_deadline=e.marks_deadline,
        notes=e.notes,
        created_at=e.created_at,
        updated_at=e.updated_at,
        cohorts=[
            ExamCohortOut(id=c.id, code=c.code, name=c.name, program_code=p.code, students=n)
            for c, p, n in view.cohorts
        ],
        papers=[
            ExamPaperOut(
                id=p.id,
                course_id=c.id,
                course_code=c.code,
                course_name=c.name,
                position=p.position,
                components=[ExamComponentOut(**x) for x in p.components],
                max_total=p.max_total,
                pass_total=p.pass_total,
                credits=p.credits,
                assignments=[
                    ExamAssignmentOut(
                        cohort_id=a.cohort_id, user_id=a.user_id, full_name=view.faculty.get(a.user_id, "")
                    )
                    for a in view.assignments
                    if a.exam_paper_id == p.id
                ],
                submissions=[
                    ExamSubmissionOut(cohort_id=s.cohort_id, status=s.status, submitted_at=s.submitted_at)
                    for s in view.submissions
                    if s.exam_paper_id == p.id
                ],
            )
            for p, c in view.papers
        ],
        checks=[ExamCheckOut(key=k.key, ok=k.ok, message=k.message) for k in view.checks],
        actions=[
            ExamActionOut(action=t.action.value, label=t.label, needs_reason=t.needs_reason)
            for t in available(e.status)
        ],
    )


@router.get("")
async def list_exams(
    uow: UoW,
    infra: InfraDep,
    status: ExamStatusLit | None = None,
    term_id: uuid.UUID | None = None,
    _: Principal = require(P.EXAMS_VIEW),
) -> list[ExamListItem]:
    rows = await ExamService(infra).search(uow, status=status, term_id=term_id)
    return [
        ExamListItem(
            id=e.id,
            name=e.name,
            kind=e.kind,
            status=e.status,
            term=_term(t, s),
            grading_scheme_name=scheme_name,
            papers=papers,
            cohorts=cohorts,
            marks_deadline=e.marks_deadline,
            updated_at=e.updated_at,
        )
        for e, t, s, scheme_name, papers, cohorts in rows
    ]


@router.post("", status_code=201)
async def create_exam(
    body: ExamCreateIn, uow: UoW, infra: InfraDep, principal: Principal = require(P.EXAMS_MANAGE)
) -> ExamOut:
    service = ExamService(infra)
    exam = await service.create(
        uow,
        principal,
        name=body.name,
        kind=body.kind,
        term_id=body.term_id,
        grading_scheme_id=body.grading_scheme_id,
        cohort_ids=body.cohort_ids,
        marks_deadline=body.marks_deadline,
        notes=body.notes,
    )
    return await _out(uow, service, exam.id)


@router.get("/{exam_id}")
async def get_exam(
    exam_id: uuid.UUID, uow: UoW, infra: InfraDep, _: Principal = require(P.EXAMS_VIEW)
) -> ExamOut:
    return await _out(uow, ExamService(infra), exam_id)


@router.put("/{exam_id}")
async def update_exam(
    exam_id: uuid.UUID,
    body: ExamUpdateIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.EXAMS_MANAGE),
) -> ExamOut:
    service = ExamService(infra)
    await service.update(
        uow,
        principal,
        exam_id,
        version=body.version,
        name=body.name,
        kind=body.kind,
        grading_scheme_id=body.grading_scheme_id,
        marks_deadline=body.marks_deadline,
        notes=body.notes,
    )
    return await _out(uow, service, exam_id)


@router.delete("/{exam_id}", status_code=204)
async def delete_exam(
    exam_id: uuid.UUID, uow: UoW, infra: InfraDep, principal: Principal = require(P.EXAMS_MANAGE)
) -> Response:
    await ExamService(infra).delete(uow, principal, exam_id)
    return Response(status_code=204)


@router.put("/{exam_id}/cohorts")
async def set_cohorts(
    exam_id: uuid.UUID,
    body: ExamCohortsIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.EXAMS_MANAGE),
) -> ExamOut:
    service = ExamService(infra)
    await service.set_cohorts(uow, principal, exam_id, body.cohort_ids)
    return await _out(uow, service, exam_id)


@router.post("/{exam_id}/papers", status_code=201)
async def add_paper(
    exam_id: uuid.UUID,
    body: ExamPaperCreateIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.EXAMS_MANAGE),
) -> ExamOut:
    service = ExamService(infra)
    await service.add_paper(
        uow,
        principal,
        exam_id,
        course_id=body.course_id,
        components=[c.model_dump() for c in body.components],
        pass_total=body.pass_total,
        credits=body.credits,
        use_course_credits=body.use_course_credits,
    )
    return await _out(uow, service, exam_id)


@router.put("/{exam_id}/papers/{paper_id}")
async def update_paper(
    exam_id: uuid.UUID,
    paper_id: uuid.UUID,
    body: ExamPaperIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.EXAMS_MANAGE),
) -> ExamOut:
    service = ExamService(infra)
    await service.update_paper(
        uow,
        principal,
        exam_id,
        paper_id,
        components=[c.model_dump() for c in body.components],
        pass_total=body.pass_total,
        credits=body.credits,
    )
    return await _out(uow, service, exam_id)


@router.delete("/{exam_id}/papers/{paper_id}")
async def remove_paper(
    exam_id: uuid.UUID,
    paper_id: uuid.UUID,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.EXAMS_MANAGE),
) -> ExamOut:
    service = ExamService(infra)
    await service.remove_paper(uow, principal, exam_id, paper_id)
    return await _out(uow, service, exam_id)


@router.put("/{exam_id}/papers/{paper_id}/assignments")
async def set_assignments(
    exam_id: uuid.UUID,
    paper_id: uuid.UUID,
    body: ExamAssignmentsIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.EXAMS_MANAGE),
) -> ExamOut:
    service = ExamService(infra)
    await service.set_assignments(
        uow, principal, exam_id, paper_id, cohort_id=body.cohort_id, user_ids=body.user_ids
    )
    return await _out(uow, service, exam_id)


@router.post("/{exam_id}/transitions")
async def transition(
    exam_id: uuid.UUID,
    body: ExamTransitionIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.EXAMS_MANAGE),
) -> ExamOut:
    service = ExamService(infra)
    await service.transition(uow, principal, exam_id, body.action, reason=body.reason)
    return await _out(uow, service, exam_id)
