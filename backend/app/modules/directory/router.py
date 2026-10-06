from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.http import InfraDep, Principal, UoW, require
from app.core.pagination import Page
from app.modules.directory import onboarding as _onboarding  # noqa: F401  (registers the checklist step)
from app.modules.directory.activation import ActivationService
from app.modules.directory.service import StudentData, StudentFilters, StudentService, StudentView
from app.modules.identity.permissions import P

router = APIRouter(prefix="/api/v1/admin", tags=["students"])

StudentStatus = Literal["active", "graduated", "withdrawn", "archived"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StudentIn(In):
    enrollment_no: str = Field(min_length=1, max_length=60)
    full_name: str = Field(min_length=1, max_length=200)
    date_of_birth: date | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    guardian_name: str | None = Field(default=None, max_length=200)
    admission_year: int | None = Field(default=None, ge=1950, le=2100)

    def data(self) -> StudentData:
        return StudentData(
            enrollment_no=self.enrollment_no,
            full_name=self.full_name,
            date_of_birth=self.date_of_birth,
            email=str(self.email) if self.email else None,
            phone=self.phone,
            guardian_name=self.guardian_name,
            admission_year=self.admission_year,
        )


class StudentCreateIn(StudentIn):
    cohort_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


class StudentUpdateIn(StudentIn):
    version: int = Field(ge=1)


class StudentStatusIn(In):
    status: StudentStatus
    reason: str | None = Field(default=None, max_length=500)


class CohortAssignIn(In):
    cohort_id: uuid.UUID


class CohortMembersIn(In):
    student_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class MembershipOut(BaseModel):
    cohort_id: uuid.UUID
    cohort_code: str
    cohort_name: str
    session_id: uuid.UUID
    session_code: str
    session_is_current: bool
    program_id: uuid.UUID
    program_code: str


class StudentOut(BaseModel):
    id: uuid.UUID
    enrollment_no: str
    full_name: str
    date_of_birth: date | None
    email: str | None
    phone: str | None
    guardian_name: str | None
    admission_year: int | None
    status: StudentStatus
    account: Literal["none", "pending", "active", "disabled"]
    version: int
    created_at: datetime
    archived_at: datetime | None
    memberships: list[MembershipOut]

    @classmethod
    def of(cls, view: StudentView) -> StudentOut:
        s = view.student
        return cls(
            id=s.id,
            enrollment_no=s.enrollment_no,
            full_name=s.full_name,
            date_of_birth=s.date_of_birth,
            email=s.email,
            phone=s.phone,
            guardian_name=s.guardian_name,
            admission_year=s.admission_year,
            status=s.status,
            account=view.account,
            version=s.version,
            created_at=s.created_at,
            archived_at=s.archived_at,
            memberships=[MembershipOut(**m.__dict__) for m in view.memberships],
        )


class StudentCountsOut(BaseModel):
    active: int
    graduated: int
    withdrawn: int
    archived: int


class CohortMembersOut(BaseModel):
    added: int
    moved: int
    unchanged: int


@router.get("/students")
async def list_students(
    uow: UoW,
    infra: InfraDep,
    q: str | None = Query(default=None, max_length=100),
    status: StudentStatus | None = None,
    cohort_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    program_id: uuid.UUID | None = None,
    account: Literal["none", "pending", "active", "disabled"] | None = None,
    cursor: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    _: Principal = require(P.STUDENTS_VIEW),
) -> Page[StudentOut]:
    filters = StudentFilters(
        q=q, status=status, cohort_id=cohort_id, session_id=session_id, program_id=program_id, account=account
    )
    views, next_cursor, total = await StudentService(infra).search(uow, filters, cursor=cursor, limit=limit)
    return Page[StudentOut](items=[StudentOut.of(v) for v in views], next_cursor=next_cursor, total=total)


@router.get("/students/counts")
async def student_counts(
    uow: UoW, infra: InfraDep, _: Principal = require(P.STUDENTS_VIEW)
) -> StudentCountsOut:
    return StudentCountsOut(**await StudentService(infra).counts(uow))


@router.post("/students", status_code=201)
async def create_student(
    body: StudentCreateIn, uow: UoW, infra: InfraDep, principal: Principal = require(P.STUDENTS_MANAGE)
) -> StudentOut:
    service = StudentService(infra)
    student = await service.create(uow, principal, body.data(), cohort_ids=body.cohort_ids)
    return StudentOut.of(await service.detail(uow, student.id))


@router.get("/students/{student_id}")
async def get_student(
    student_id: uuid.UUID, uow: UoW, infra: InfraDep, _: Principal = require(P.STUDENTS_VIEW)
) -> StudentOut:
    return StudentOut.of(await StudentService(infra).detail(uow, student_id))


@router.put("/students/{student_id}")
async def update_student(
    student_id: uuid.UUID,
    body: StudentUpdateIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.STUDENTS_MANAGE),
) -> StudentOut:
    service = StudentService(infra)
    await service.update(uow, principal, student_id, body.data(), version=body.version)
    return StudentOut.of(await service.detail(uow, student_id))


@router.put("/students/{student_id}/status")
async def set_student_status(
    student_id: uuid.UUID,
    body: StudentStatusIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.STUDENTS_MANAGE),
) -> StudentOut:
    service = StudentService(infra)
    await service.set_status(uow, principal, student_id, body.status, reason=body.reason)
    return StudentOut.of(await service.detail(uow, student_id))


@router.post("/students/{student_id}/cohorts")
async def assign_cohort(
    student_id: uuid.UUID,
    body: CohortAssignIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.STUDENTS_MANAGE),
) -> StudentOut:
    service = StudentService(infra)
    await service.assign_cohort(uow, principal, student_id, body.cohort_id)
    return StudentOut.of(await service.detail(uow, student_id))


@router.delete("/students/{student_id}/cohorts/{cohort_id}")
async def remove_cohort(
    student_id: uuid.UUID,
    cohort_id: uuid.UUID,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.STUDENTS_MANAGE),
) -> StudentOut:
    service = StudentService(infra)
    await service.remove_cohort(uow, principal, student_id, cohort_id)
    return StudentOut.of(await service.detail(uow, student_id))


@router.post("/cohorts/{cohort_id}/students")
async def add_cohort_members(
    cohort_id: uuid.UUID,
    body: CohortMembersIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.STUDENTS_MANAGE),
) -> CohortMembersOut:
    return CohortMembersOut(
        **await StudentService(infra).add_to_cohort(uow, principal, cohort_id, body.student_ids)
    )


class ActivationCodesIn(In):
    cohort_id: uuid.UUID | None = None
    student_ids: list[uuid.UUID] = Field(default_factory=list, max_length=2000)
    replace_existing: bool = False


class IssuedCodeOut(BaseModel):
    student_id: uuid.UUID
    enrollment_no: str
    full_name: str
    cohort_code: str | None
    code: str
    expires_at: datetime


class SkippedOut(BaseModel):
    student_id: uuid.UUID
    enrollment_no: str
    full_name: str
    reason: Literal["already_active", "has_code", "not_active_student"]


class ActivationCodesOut(BaseModel):
    cohort_code: str | None
    issued: list[IssuedCodeOut]
    skipped: list[SkippedOut]


@router.post("/activation-codes")
async def issue_activation_codes(
    body: ActivationCodesIn, uow: UoW, infra: InfraDep, principal: Principal = require(P.STUDENTS_MANAGE)
) -> ActivationCodesOut:
    """Codes appear only in this response (only hashes are stored); keep the page open to print slips."""
    issued, skipped, cohort_code = await ActivationService(infra).issue(
        uow,
        principal,
        cohort_id=body.cohort_id,
        student_ids=body.student_ids,
        replace_existing=body.replace_existing,
    )
    return ActivationCodesOut(
        cohort_code=cohort_code,
        issued=[IssuedCodeOut(**i.__dict__) for i in issued],
        skipped=[SkippedOut(**s.__dict__) for s in skipped],
    )
