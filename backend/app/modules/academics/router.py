from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.http import InfraDep, Principal, UoW, require
from app.modules.academics import onboarding as _onboarding  # noqa: F401  (registers the checklist step)
from app.modules.academics.models import AcademicSession, Cohort, Course, Department, Program
from app.modules.academics.service import AcademicsService
from app.modules.identity.permissions import P

router = APIRouter(prefix="/api/v1/admin", tags=["academics"])

View = P.ACADEMICS_VIEW
Manage = P.ACADEMICS_MANAGE


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- schemas ------------------------------------------------------------------------------------


class SessionIn(In):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=100)
    starts_on: date
    ends_on: date


class SessionCreateIn(SessionIn):
    make_current: bool = False


class SessionOut(Out):
    id: uuid.UUID
    code: str
    name: str
    starts_on: date
    ends_on: date
    is_current: bool
    archived_at: datetime | None


class TermIn(In):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=100)
    sequence: int | None = Field(default=None, ge=1, le=50)
    starts_on: date | None = None
    ends_on: date | None = None


class TermOut(Out):
    id: uuid.UUID
    session_id: uuid.UUID
    code: str
    name: str
    sequence: int
    starts_on: date | None
    ends_on: date | None


class CopyIn(In):
    source_session_id: uuid.UUID


class CopyOut(BaseModel):
    terms: int
    cohorts: int


class DepartmentIn(In):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=150)


class DepartmentOut(Out):
    id: uuid.UUID
    code: str
    name: str
    archived_at: datetime | None


class ProgramIn(In):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=150)
    department_id: uuid.UUID | None = None
    level: str | None = Field(default=None, max_length=60)
    duration_terms: int | None = Field(default=None, ge=1, le=20)


class ProgramOut(Out):
    id: uuid.UUID
    code: str
    name: str
    department_id: uuid.UUID | None
    level: str | None
    duration_terms: int | None
    archived_at: datetime | None


class CohortCreateIn(In):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=150)
    program_id: uuid.UUID
    session_id: uuid.UUID


class CohortUpdateIn(In):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=150)


class CohortOut(Out):
    id: uuid.UUID
    code: str
    name: str
    program_id: uuid.UUID
    session_id: uuid.UUID
    archived_at: datetime | None


class CourseIn(In):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    department_id: uuid.UUID | None = None
    credits: Decimal | None = Field(default=None, ge=0, le=40, max_digits=4, decimal_places=1)


class CourseOut(Out):
    id: uuid.UUID
    code: str
    name: str
    department_id: uuid.UUID | None
    credits: Decimal | None
    archived_at: datetime | None


class CourseList(BaseModel):
    items: list[CourseOut]
    total: int
    limit: int
    offset: int


class ArchiveIn(In):
    archived: bool


class StructureCounts(BaseModel):
    sessions: int
    departments: int
    programs: int
    cohorts: int
    courses: int


# ---- sessions & terms ---------------------------------------------------------------------------


@router.get("/academic-structure/summary")
async def summary(uow: UoW, infra: InfraDep, _: Principal = require(View)) -> StructureCounts:
    return StructureCounts(**await AcademicsService(infra).counts(uow))


@router.get("/academic-sessions")
async def list_sessions(
    uow: UoW, infra: InfraDep, include_archived: bool = False, _: Principal = require(View)
) -> list[SessionOut]:
    rows = await AcademicsService(infra).list_sessions(uow, include_archived=include_archived)
    return [SessionOut.model_validate(r) for r in rows]


@router.post("/academic-sessions", status_code=201)
async def create_session(
    body: SessionCreateIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> SessionOut:
    obj = await AcademicsService(infra).create_session(
        uow,
        principal,
        code=body.code,
        name=body.name,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        make_current=body.make_current,
    )
    return SessionOut.model_validate(obj)


@router.put("/academic-sessions/{session_id}")
async def update_session(
    session_id: uuid.UUID, body: SessionIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> SessionOut:
    obj = await AcademicsService(infra).update_session(
        uow,
        principal,
        session_id,
        code=body.code,
        name=body.name,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
    )
    return SessionOut.model_validate(obj)


@router.post("/academic-sessions/{session_id}/make-current")
async def make_current(
    session_id: uuid.UUID, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> SessionOut:
    return SessionOut.model_validate(await AcademicsService(infra).make_current(uow, principal, session_id))


@router.put("/academic-sessions/{session_id}/archived")
async def archive_session(
    session_id: uuid.UUID, body: ArchiveIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> SessionOut:
    obj = await AcademicsService(infra).set_archived(
        uow, principal, AcademicSession, session_id, body.archived
    )
    return SessionOut.model_validate(obj)


@router.post("/academic-sessions/{session_id}/copy-structure")
async def copy_structure(
    session_id: uuid.UUID, body: CopyIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> CopyOut:
    return CopyOut(
        **await AcademicsService(infra).copy_structure(uow, principal, session_id, body.source_session_id)
    )


@router.get("/academic-sessions/{session_id}/terms")
async def list_terms(
    session_id: uuid.UUID, uow: UoW, infra: InfraDep, _: Principal = require(View)
) -> list[TermOut]:
    return [TermOut.model_validate(t) for t in await AcademicsService(infra).list_terms(uow, session_id)]


@router.post("/academic-sessions/{session_id}/terms", status_code=201)
async def create_term(
    session_id: uuid.UUID, body: TermIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> TermOut:
    obj = await AcademicsService(infra).create_term(
        uow,
        principal,
        session_id,
        code=body.code,
        name=body.name,
        sequence=body.sequence,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
    )
    return TermOut.model_validate(obj)


@router.put("/terms/{term_id}")
async def update_term(
    term_id: uuid.UUID, body: TermIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> TermOut:
    obj = await AcademicsService(infra).update_term(
        uow,
        principal,
        term_id,
        code=body.code,
        name=body.name,
        sequence=body.sequence or 1,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
    )
    return TermOut.model_validate(obj)


# ---- departments --------------------------------------------------------------------------------


@router.get("/departments")
async def list_departments(
    uow: UoW, infra: InfraDep, include_archived: bool = False, _: Principal = require(View)
) -> list[DepartmentOut]:
    rows = await AcademicsService(infra).list_departments(uow, include_archived=include_archived)
    return [DepartmentOut.model_validate(r) for r in rows]


@router.post("/departments", status_code=201)
async def create_department(
    body: DepartmentIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> DepartmentOut:
    obj = await AcademicsService(infra).create_department(uow, principal, code=body.code, name=body.name)
    return DepartmentOut.model_validate(obj)


@router.put("/departments/{department_id}")
async def update_department(
    department_id: uuid.UUID,
    body: DepartmentIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(Manage),
) -> DepartmentOut:
    obj = await AcademicsService(infra).update_department(
        uow, principal, department_id, code=body.code, name=body.name
    )
    return DepartmentOut.model_validate(obj)


@router.put("/departments/{department_id}/archived")
async def archive_department(
    department_id: uuid.UUID,
    body: ArchiveIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(Manage),
) -> DepartmentOut:
    obj = await AcademicsService(infra).set_archived(uow, principal, Department, department_id, body.archived)
    return DepartmentOut.model_validate(obj)


# ---- programs -----------------------------------------------------------------------------------


@router.get("/programs")
async def list_programs(
    uow: UoW, infra: InfraDep, include_archived: bool = False, _: Principal = require(View)
) -> list[ProgramOut]:
    rows = await AcademicsService(infra).list_programs(uow, include_archived=include_archived)
    return [ProgramOut.model_validate(r) for r in rows]


@router.post("/programs", status_code=201)
async def create_program(
    body: ProgramIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> ProgramOut:
    obj = await AcademicsService(infra).create_program(
        uow,
        principal,
        code=body.code,
        name=body.name,
        department_id=body.department_id,
        level=body.level,
        duration_terms=body.duration_terms,
    )
    return ProgramOut.model_validate(obj)


@router.put("/programs/{program_id}")
async def update_program(
    program_id: uuid.UUID, body: ProgramIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> ProgramOut:
    obj = await AcademicsService(infra).update_program(
        uow,
        principal,
        program_id,
        code=body.code,
        name=body.name,
        department_id=body.department_id,
        level=body.level,
        duration_terms=body.duration_terms,
    )
    return ProgramOut.model_validate(obj)


@router.put("/programs/{program_id}/archived")
async def archive_program(
    program_id: uuid.UUID, body: ArchiveIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> ProgramOut:
    obj = await AcademicsService(infra).set_archived(uow, principal, Program, program_id, body.archived)
    return ProgramOut.model_validate(obj)


# ---- cohorts ------------------------------------------------------------------------------------


@router.get("/cohorts")
async def list_cohorts(
    uow: UoW,
    infra: InfraDep,
    session_id: uuid.UUID | None = None,
    program_id: uuid.UUID | None = None,
    include_archived: bool = False,
    _: Principal = require(View),
) -> list[CohortOut]:
    rows = await AcademicsService(infra).list_cohorts(
        uow, session_id=session_id, program_id=program_id, include_archived=include_archived
    )
    return [CohortOut.model_validate(r) for r in rows]


@router.post("/cohorts", status_code=201)
async def create_cohort(
    body: CohortCreateIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> CohortOut:
    obj = await AcademicsService(infra).create_cohort(
        uow, principal, code=body.code, name=body.name, program_id=body.program_id, session_id=body.session_id
    )
    return CohortOut.model_validate(obj)


@router.put("/cohorts/{cohort_id}")
async def update_cohort(
    cohort_id: uuid.UUID,
    body: CohortUpdateIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(Manage),
) -> CohortOut:
    obj = await AcademicsService(infra).update_cohort(
        uow, principal, cohort_id, code=body.code, name=body.name
    )
    return CohortOut.model_validate(obj)


@router.put("/cohorts/{cohort_id}/archived")
async def archive_cohort(
    cohort_id: uuid.UUID, body: ArchiveIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> CohortOut:
    obj = await AcademicsService(infra).set_archived(uow, principal, Cohort, cohort_id, body.archived)
    return CohortOut.model_validate(obj)


# ---- courses ------------------------------------------------------------------------------------


@router.get("/courses")
async def list_courses(
    uow: UoW,
    infra: InfraDep,
    q: str | None = Query(default=None, max_length=100),
    department_id: uuid.UUID | None = None,
    include_archived: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: Principal = require(View),
) -> CourseList:
    rows, total = await AcademicsService(infra).list_courses(
        uow, q=q, department_id=department_id, include_archived=include_archived, limit=limit, offset=offset
    )
    return CourseList(
        items=[CourseOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("/courses", status_code=201)
async def create_course(
    body: CourseIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> CourseOut:
    obj = await AcademicsService(infra).create_course(
        uow, principal, code=body.code, name=body.name, department_id=body.department_id, credits=body.credits
    )
    return CourseOut.model_validate(obj)


@router.put("/courses/{course_id}")
async def update_course(
    course_id: uuid.UUID, body: CourseIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> CourseOut:
    obj = await AcademicsService(infra).update_course(
        uow,
        principal,
        course_id,
        code=body.code,
        name=body.name,
        department_id=body.department_id,
        credits=body.credits,
    )
    return CourseOut.model_validate(obj)


@router.put("/courses/{course_id}/archived")
async def archive_course(
    course_id: uuid.UUID, body: ArchiveIn, uow: UoW, infra: InfraDep, principal: Principal = require(Manage)
) -> CourseOut:
    obj = await AcademicsService(infra).set_archived(uow, principal, Course, course_id, body.archived)
    return CourseOut.model_validate(obj)
