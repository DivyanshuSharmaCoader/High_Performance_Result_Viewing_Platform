from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.core.http import InfraDep, Principal, UoW, require
from app.modules.identity.permissions import P
from app.modules.marks.service import Change, MarksService, Sheet, is_complete

router = APIRouter(prefix="/api/v1", tags=["marks"])

Attendance = Literal["present", "absent", "exempt", "malpractice", "withheld"]
SubmissionStatus = Literal["open", "submitted", "returned", "locked"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChangeIn(In):
    student_id: uuid.UUID
    attendance: Attendance = "present"
    components: dict[str, str | None] = Field(default_factory=dict, max_length=10)
    version: int | None = Field(default=None, ge=1)


class SaveIn(In):
    changes: list[ChangeIn] = Field(min_length=1, max_length=500)


class ReturnIn(In):
    reason: str = Field(min_length=3, max_length=500)


class EntryOut(BaseModel):
    components: dict[str, str]
    attendance: Attendance
    total: Decimal | None
    version: int
    complete: bool
    updated_at: datetime
    updated_by_name: str | None


class SheetStudentOut(BaseModel):
    student_id: uuid.UUID
    enrollment_no: str
    full_name: str
    entry: EntryOut | None


class SheetComponentOut(BaseModel):
    code: str
    label: str
    max: Decimal
    min_pass: Decimal | None


class SheetOut(BaseModel):
    exam_id: uuid.UUID
    exam_name: str
    exam_status: str
    marks_deadline: datetime | None
    paper_id: uuid.UUID
    course_code: str
    course_name: str
    components: list[SheetComponentOut]
    max_total: Decimal
    pass_total: Decimal | None
    cohort_id: uuid.UUID
    cohort_code: str
    cohort_name: str
    submission_status: SubmissionStatus
    submitted_at: datetime | None
    submitted_by_name: str | None
    return_reason: str | None
    can_edit: bool
    can_submit: bool
    can_return: bool
    complete: int
    students: list[SheetStudentOut]


class SavedEntryOut(BaseModel):
    student_id: uuid.UUID
    entry: EntryOut


class WorkItemOut(BaseModel):
    exam_id: uuid.UUID
    exam_name: str
    exam_status: str
    marks_deadline: datetime | None
    paper_id: uuid.UUID
    course_code: str
    course_name: str
    cohort_id: uuid.UUID
    cohort_code: str
    submission_status: SubmissionStatus
    students: int
    entered: int


def _entry(sheet_or_names: Any, e: Any, paper: Any) -> EntryOut:
    names = sheet_or_names
    return EntryOut(
        components=e.components,
        attendance=e.attendance,
        total=e.total,
        version=e.version,
        complete=is_complete(e, paper),
        updated_at=e.updated_at,
        updated_by_name=names.get(e.updated_by) if e.updated_by else None,
    )


def _sheet(s: Sheet) -> SheetOut:
    sub = s.submission
    return SheetOut(
        exam_id=s.exam.id,
        exam_name=s.exam.name,
        exam_status=s.exam.status,
        marks_deadline=s.exam.marks_deadline,
        paper_id=s.paper.id,
        course_code=s.course.code,
        course_name=s.course.name,
        components=[SheetComponentOut(**c) for c in s.paper.components],
        max_total=s.paper.max_total,
        pass_total=s.paper.pass_total,
        cohort_id=s.cohort.id,
        cohort_code=s.cohort.code,
        cohort_name=s.cohort.name,
        submission_status=sub.status if sub else "open",
        submitted_at=sub.submitted_at if sub else None,
        submitted_by_name=s.names.get(sub.submitted_by) if sub and sub.submitted_by else None,
        return_reason=sub.return_reason if sub else None,
        can_edit=s.can_edit,
        can_submit=s.can_submit,
        can_return=s.can_return,
        complete=s.complete,
        students=[
            SheetStudentOut(
                student_id=st.id,
                enrollment_no=st.enrollment_no,
                full_name=st.full_name,
                entry=_entry(s.names, s.entries[st.id], s.paper) if st.id in s.entries else None,
            )
            for st in s.students
        ],
    )


SHEET = "/exams/{exam_id}/papers/{paper_id}/cohorts/{cohort_id}/marks"


@router.get("/marking")
async def my_marking(
    uow: UoW, infra: InfraDep, principal: Principal = require(P.EXAMS_VIEW_ASSIGNED)
) -> list[WorkItemOut]:
    """Papers × cohorts the signed-in person can enter marks for right now."""
    return [
        WorkItemOut(
            exam_id=w["exam"].id,
            exam_name=w["exam"].name,
            exam_status=w["exam"].status,
            marks_deadline=w["exam"].marks_deadline,
            paper_id=w["paper"].id,
            course_code=w["course"].code,
            course_name=w["course"].name,
            cohort_id=w["cohort"].id,
            cohort_code=w["cohort"].code,
            submission_status=w["submission_status"],
            students=w["students"],
            entered=w["entered"],
        )
        for w in await MarksService(infra).my_work(uow, principal)
    ]


@router.get(SHEET)
async def get_sheet(
    exam_id: uuid.UUID,
    paper_id: uuid.UUID,
    cohort_id: uuid.UUID,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.EXAMS_VIEW_ASSIGNED),
) -> SheetOut:
    return _sheet(await MarksService(infra).sheet(uow, principal, exam_id, paper_id, cohort_id))


@router.put(SHEET)
async def save_marks(
    exam_id: uuid.UUID,
    paper_id: uuid.UUID,
    cohort_id: uuid.UUID,
    body: SaveIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.EXAMS_VIEW_ASSIGNED),
) -> list[SavedEntryOut]:
    service = MarksService(infra)
    saved = await service.save(
        uow,
        principal,
        exam_id,
        paper_id,
        cohort_id,
        [Change(c.student_id, c.attendance, c.components, c.version) for c in body.changes],
    )
    await uow.flush()
    sheet = await service.sheet(uow, principal, exam_id, paper_id, cohort_id)
    for e in saved:
        await uow.session.refresh(e)
    return [SavedEntryOut(student_id=e.student_id, entry=_entry(sheet.names, e, sheet.paper)) for e in saved]


@router.post(SHEET + "/submit")
async def submit_paper(
    exam_id: uuid.UUID,
    paper_id: uuid.UUID,
    cohort_id: uuid.UUID,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.EXAMS_VIEW_ASSIGNED),
) -> SheetOut:
    service = MarksService(infra)
    await service.submit(uow, principal, exam_id, paper_id, cohort_id)
    return _sheet(await service.sheet(uow, principal, exam_id, paper_id, cohort_id))


@router.post(SHEET + "/return")
async def return_paper(
    exam_id: uuid.UUID,
    paper_id: uuid.UUID,
    cohort_id: uuid.UUID,
    body: ReturnIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.PAPERS_REVIEW),
) -> SheetOut:
    service = MarksService(infra)
    await service.return_paper(uow, principal, exam_id, paper_id, cohort_id, body.reason)
    return _sheet(await service.sheet(uow, principal, exam_id, paper_id, cohort_id))
