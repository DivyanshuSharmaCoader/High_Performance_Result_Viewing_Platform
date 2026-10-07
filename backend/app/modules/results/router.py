from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.http import InfraDep, Principal, UoW, require
from app.core.idempotency import idempotent
from app.modules.grading.models import GradingScheme, GradingSchemeVersion
from app.modules.identity.permissions import P
from app.modules.results.models import ResultRun
from app.modules.results.service import PROCESSABLE, Overview, ResultsService, StudentRow

router = APIRouter(prefix="/api/v1/admin/exams/{exam_id}/results", tags=["results"])

RunStatus = Literal["running", "completed", "failed", "stale", "approved", "published"]
ExamOutcome = Literal["pass", "fail", "absent", "withheld", "incomplete"]


class ResultSchemeRef(BaseModel):
    name: str
    version: int


class ResultRunOut(BaseModel):
    id: uuid.UUID
    revision: int
    status: RunStatus
    created_at: datetime
    finished_at: datetime | None
    started_by_name: str | None
    error_detail: str | None
    students: int
    input_hash: str | None
    content_hash: str | None
    scheme: ResultSchemeRef | None
    override_reason: str | None
    stats: dict[str, Any]
    anomalies: list[dict[str, Any]]


class ResultRunBrief(BaseModel):
    id: uuid.UUID
    revision: int
    status: RunStatus
    created_at: datetime
    started_by_name: str | None


class ResultApprovalOut(BaseModel):
    id: uuid.UUID
    decision: Literal["approved", "rejected", "revoked"]
    decided_by_name: str | None
    created_at: datetime
    comment: str | None
    revision: int | None
    content_hash: str


class ResultUnsubmitted(BaseModel):
    course_code: str
    cohort_code: str
    status: str


class ResultActions(BaseModel):
    can_process: bool
    can_discard: bool
    can_approve: bool
    can_reject: bool
    can_revoke: bool
    approve_blocked_reason: str | None


class ResultsOverviewOut(BaseModel):
    exam_id: uuid.UUID
    exam_name: str
    exam_status: str
    approval_mode: Literal["single", "maker_checker"]
    run: ResultRunOut | None
    runs: list[ResultRunBrief]
    approvals: list[ResultApprovalOut]
    unsubmitted: list[ResultUnsubmitted]
    actions: ResultActions


class ResultPaperOut(BaseModel):
    exam_paper_id: uuid.UUID
    outcome: str
    attendance: str | None
    components: dict[str, Any]
    total: Decimal | None
    max_total: Decimal
    percentage: Decimal | None
    grade: str | None
    grade_point: Decimal | None
    credits: Decimal | None
    failed_components: list[str]
    missing_components: list[str]


class ResultStudentOut(BaseModel):
    student_id: uuid.UUID
    enrollment_no: str
    full_name: str
    cohort_code: str
    outcome: ExamOutcome
    total: Decimal | None
    max_total: Decimal | None
    percentage: Decimal | None
    grade: str | None
    grade_point: Decimal | None
    sgpa: Decimal | None
    credits_attempted: Decimal | None
    credits_earned: Decimal | None
    rank: int | None
    notes: list[str]
    papers: list[ResultPaperOut]


class ResultStudentsPage(BaseModel):
    run_id: uuid.UUID
    items: list[ResultStudentOut]
    next_after: str | None


class ResultProcessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    override_reason: str | None = Field(default=None, max_length=500)


class ResultApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=1000)


class ResultRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=1000)


class ResultReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=1000)


def _student(row: StudentRow) -> ResultStudentOut:
    r = row.result
    return ResultStudentOut(
        student_id=r.student_id,
        enrollment_no=row.enrollment_no,
        full_name=row.full_name,
        cohort_code=row.cohort_code,
        outcome=r.outcome,
        total=r.total,
        max_total=r.max_total,
        percentage=r.percentage,
        grade=r.grade,
        grade_point=r.grade_point,
        sgpa=r.sgpa,
        credits_attempted=r.credits_attempted,
        credits_earned=r.credits_earned,
        rank=r.rank,
        notes=list(r.notes or []),
        papers=[
            ResultPaperOut(
                exam_paper_id=p.exam_paper_id,
                outcome=p.outcome,
                attendance=p.attendance,
                components=dict(p.components or {}),
                total=p.total,
                max_total=p.max_total,
                percentage=p.percentage,
                grade=p.grade,
                grade_point=p.grade_point,
                credits=p.credits,
                failed_components=list(p.failed_components or []),
                missing_components=list(p.missing_components or []),
            )
            for p in row.papers
        ],
    )


async def _scheme(uow: Any, run: ResultRun) -> ResultSchemeRef | None:
    row = (
        await uow.session.execute(
            select(GradingScheme.name, GradingSchemeVersion.version)
            .join(GradingScheme, GradingScheme.id == GradingSchemeVersion.scheme_id)
            .where(GradingSchemeVersion.id == run.grading_scheme_version_id)
        )
    ).first()
    return ResultSchemeRef(name=row[0], version=row[1]) if row else None


async def _overview(uow: Any, principal: Principal, view: Overview) -> ResultsOverviewOut:
    run, exam = view.run, view.exam
    revisions = {r.id: r.revision for r in view.runs}
    running = run is not None and run.status == "running"
    blocked = None
    if (
        view.maker_checker
        and run is not None
        and run.status == "completed"
        and run.started_by == principal.user_id
    ):
        blocked = "Another administrator has to approve results you processed."
    awaiting = exam.status == "processed" and run is not None and run.status == "completed"
    return ResultsOverviewOut(
        exam_id=exam.id,
        exam_name=exam.name,
        exam_status=exam.status,
        approval_mode="maker_checker" if view.maker_checker else "single",
        run=(
            ResultRunOut(
                id=run.id,
                revision=run.revision,
                status=run.status,
                created_at=run.created_at,
                finished_at=run.finished_at,
                started_by_name=view.names.get(run.started_by) if run.started_by else None,
                error_detail=run.error_detail,
                students=run.students,
                input_hash=run.input_hash,
                content_hash=run.content_hash,
                scheme=await _scheme(uow, run),
                override_reason=(run.override or {}).get("reason"),
                stats=run.stats or {},
                anomalies=run.anomalies or [],
            )
            if run
            else None
        ),
        runs=[
            ResultRunBrief(
                id=r.id,
                revision=r.revision,
                status=r.status,
                created_at=r.created_at,
                started_by_name=view.names.get(r.started_by) if r.started_by else None,
            )
            for r in view.runs
        ],
        approvals=[
            ResultApprovalOut(
                id=a.id,
                decision=a.decision,
                decided_by_name=view.names.get(a.decided_by),
                created_at=a.created_at,
                comment=a.comment,
                revision=revisions.get(a.result_run_id),
                content_hash=a.content_hash,
            )
            for a in view.approvals
        ],
        unsubmitted=[ResultUnsubmitted(**u) for u in view.unsubmitted],
        actions=ResultActions(
            can_process=principal.has(P.RESULTS_PROCESS) and exam.status in PROCESSABLE and not running,
            can_discard=principal.has(P.RESULTS_PROCESS) and exam.status == "processed" and not running,
            can_approve=principal.has(P.RESULTS_APPROVE) and awaiting and blocked is None,
            can_reject=principal.has(P.RESULTS_APPROVE) and awaiting,
            can_revoke=principal.has(P.RESULTS_APPROVE) and exam.status == "approved",
            approve_blocked_reason=blocked,
        ),
    )


async def _fresh_overview(
    uow: Any, infra: Any, principal: Principal, exam_id: uuid.UUID
) -> ResultsOverviewOut:
    await uow.flush()
    return await _overview(uow, principal, await ResultsService(infra).overview(uow, exam_id))


@router.get("")
async def results_overview(
    exam_id: uuid.UUID, uow: UoW, infra: InfraDep, principal: Principal = require(P.RESULTS_VIEW)
) -> ResultsOverviewOut:
    return await _fresh_overview(uow, infra, principal, exam_id)


@router.post("/process", status_code=202, response_model=ResultsOverviewOut)
async def process_results(
    exam_id: uuid.UUID,
    body: ResultProcessIn,
    request: Request,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.RESULTS_PROCESS),
) -> Any:
    service = ResultsService(infra)
    await service.exam(uow, exam_id)  # another tenant's (or no) exam is a 404 before anything else

    async def work() -> ResultsOverviewOut:
        await service.request(uow, principal, exam_id, override_reason=body.override_reason)
        return await _fresh_overview(uow, infra, principal, exam_id)

    return await idempotent(uow, request, body.model_dump(mode="json"), work, status_code=202)


@router.post("/discard")
async def discard_results(
    exam_id: uuid.UUID,
    body: ResultReasonIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.RESULTS_PROCESS),
) -> ResultsOverviewOut:
    await ResultsService(infra).discard(uow, principal, exam_id, body.reason)
    return await _fresh_overview(uow, infra, principal, exam_id)


@router.get("/students")
async def result_students(
    exam_id: uuid.UUID,
    uow: UoW,
    infra: InfraDep,
    run_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
    outcome: ExamOutcome | None = None,
    cohort_id: uuid.UUID | None = None,
    after: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = require(P.RESULTS_VIEW),
) -> ResultStudentsPage:
    run, rows, next_after = await ResultsService(infra).students(
        uow, exam_id, run_id, q=q, outcome=outcome, cohort_id=cohort_id, after=after, limit=limit
    )
    return ResultStudentsPage(run_id=run.id, items=[_student(r) for r in rows], next_after=next_after)


@router.get("/students/{student_id}")
async def result_student(
    exam_id: uuid.UUID,
    student_id: uuid.UUID,
    uow: UoW,
    infra: InfraDep,
    run_id: uuid.UUID | None = None,
    principal: Principal = require(P.RESULTS_VIEW),
) -> ResultStudentOut:
    _run, row = await ResultsService(infra).student(uow, exam_id, run_id, student_id)
    return _student(row)


@router.post("/approve")
async def approve_results(
    exam_id: uuid.UUID,
    body: ResultApproveIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.RESULTS_APPROVE),
) -> ResultsOverviewOut:
    await ResultsService(infra).approve(uow, principal, exam_id, body.run_id, body.comment)
    return await _fresh_overview(uow, infra, principal, exam_id)


@router.post("/reject")
async def reject_results(
    exam_id: uuid.UUID,
    body: ResultRejectIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.RESULTS_APPROVE),
) -> ResultsOverviewOut:
    await ResultsService(infra).reject(uow, principal, exam_id, body.run_id, body.reason)
    return await _fresh_overview(uow, infra, principal, exam_id)


@router.post("/revoke")
async def revoke_approval(
    exam_id: uuid.UUID,
    body: ResultReasonIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.RESULTS_APPROVE),
) -> ResultsOverviewOut:
    await ResultsService(infra).revoke(uow, principal, exam_id, body.reason)
    return await _fresh_overview(uow, infra, principal, exam_id)
