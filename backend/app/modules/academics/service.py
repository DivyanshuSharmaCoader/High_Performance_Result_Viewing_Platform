"""Academic structure use cases. Every write is audited in the same transaction; codes are unique per
tenant (cohort codes per session); records are archived, not deleted, once anything may reference them."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy import func, select, update

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import InvalidState, NotFound, ValidationFailed
from app.core.http import Principal
from app.core.integrity import ConstraintMessage, flush_checked
from app.modules.academics.models import AcademicSession, Cohort, Course, Department, Program, Term
from app.modules.audit.service import Actor, diff, record
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EntitlementService

M = TypeVar("M", AcademicSession, Term, Department, Program, Cohort, Course)

MESSAGES = {
    "uq_academic_sessions__tenant_code": ConstraintMessage(
        "A session with this code already exists.", "code"
    ),
    "uq_terms__tenant_session_code": ConstraintMessage(
        "This session already has a term with this code.", "code"
    ),
    "uq_departments__tenant_code": ConstraintMessage("A department with this code already exists.", "code"),
    "uq_programs__tenant_code": ConstraintMessage("A program with this code already exists.", "code"),
    "uq_cohorts__tenant_session_code": ConstraintMessage(
        "This session already has a cohort with this code.", "code"
    ),
    "uq_courses__tenant_code": ConstraintMessage("A course with this code already exists.", "code"),
}

ENTITY_LABEL = {
    AcademicSession: "session",
    Term: "term",
    Department: "department",
    Program: "program",
    Cohort: "cohort",
    Course: "course",
}

SNAPSHOT_FIELDS: dict[type, tuple[str, ...]] = {
    AcademicSession: ("code", "name", "starts_on", "ends_on", "is_current", "archived_at"),
    Term: ("code", "name", "sequence", "starts_on", "ends_on"),
    Department: ("code", "name", "archived_at"),
    Program: ("code", "name", "department_id", "level", "duration_terms", "archived_at"),
    Cohort: ("code", "name", "program_id", "session_id", "archived_at"),
    Course: ("code", "name", "department_id", "credits", "archived_at"),
}


def normalise_code(code: str) -> str:
    value = " ".join(code.strip().split()).upper()
    if not value:
        raise ValidationFailed("Enter a code.", field="code")
    return value


def snapshot(obj: Any) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in SNAPSHOT_FIELDS[type(obj)]}


class AcademicsService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    # ---- generic helpers ------------------------------------------------------------------------
    async def get(self, uow: UnitOfWork, model: type[M], obj_id: uuid.UUID, *, lock: bool = False) -> M:
        stmt = select(model).where(model.id == obj_id)
        if lock:
            stmt = stmt.with_for_update()
        obj = (await uow.session.scalars(stmt)).one_or_none()
        if obj is None:
            raise NotFound(f"{ENTITY_LABEL[model].capitalize()} not found")
        return obj

    async def _created(self, uow: UnitOfWork, principal: Principal, obj: Any) -> None:
        uow.session.add(obj)
        await flush_checked(uow, MESSAGES)
        label = ENTITY_LABEL[type(obj)]
        await record(
            uow,
            Actor.from_principal(principal),
            f"{label}.created",
            entity_type=label,
            entity_id=obj.id,
            summary=f"Created {label} {obj.code} — {obj.name}",
            after=snapshot(obj),
        )

    async def _updated(self, uow: UnitOfWork, principal: Principal, obj: Any, before: dict[str, Any]) -> None:
        await flush_checked(uow, MESSAGES)
        d_before, d_after = diff(before, snapshot(obj))
        if d_after:
            label = ENTITY_LABEL[type(obj)]
            await record(
                uow,
                Actor.from_principal(principal),
                f"{label}.updated",
                entity_type=label,
                entity_id=obj.id,
                summary=f"Updated {label} {obj.code}",
                before=d_before,
                after=d_after,
            )

    async def set_archived(
        self, uow: UnitOfWork, principal: Principal, model: type[M], obj_id: uuid.UUID, archived: bool
    ) -> M:
        obj = await self.get(uow, model, obj_id, lock=True)
        if not hasattr(obj, "archived_at"):
            raise InvalidState("This record can't be archived.")
        if archived == (obj.archived_at is not None):
            return obj
        if archived and isinstance(obj, AcademicSession) and obj.is_current:
            raise InvalidState("Make another session current before archiving this one.")
        if not archived and isinstance(obj, Department):
            await self._check_department_quota(uow, adding=1)
        obj.archived_at = utcnow() if archived else None
        label = ENTITY_LABEL[model]
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            f"{label}.{'archived' if archived else 'restored'}",
            entity_type=label,
            entity_id=obj.id,
            summary=f"{'Archived' if archived else 'Restored'} {label} {obj.code}",
        )
        return obj

    # ---- sessions & terms -----------------------------------------------------------------------
    async def list_sessions(
        self, uow: UnitOfWork, *, include_archived: bool = False
    ) -> list[AcademicSession]:
        stmt = select(AcademicSession).order_by(AcademicSession.starts_on.desc())
        if not include_archived:
            stmt = stmt.where(AcademicSession.archived_at.is_(None))
        return list((await uow.session.scalars(stmt)).all())

    async def create_session(
        self,
        uow: UnitOfWork,
        principal: Principal,
        *,
        code: str,
        name: str,
        starts_on: date,
        ends_on: date,
        make_current: bool,
    ) -> AcademicSession:
        if starts_on >= ends_on:
            raise ValidationFailed("The session must end after it starts.", field="ends_on")
        has_any = (
            await uow.session.execute(select(func.count()).select_from(AcademicSession))
        ).scalar_one() > 0
        obj = AcademicSession(
            tenant_id=uow.require_tenant(),
            code=normalise_code(code),
            name=name.strip(),
            starts_on=starts_on,
            ends_on=ends_on,
            is_current=False,
        )
        await self._created(uow, principal, obj)
        if make_current or not has_any:
            await self.make_current(uow, principal, obj.id)
        return obj

    async def update_session(
        self,
        uow: UnitOfWork,
        principal: Principal,
        session_id: uuid.UUID,
        *,
        code: str,
        name: str,
        starts_on: date,
        ends_on: date,
    ) -> AcademicSession:
        if starts_on >= ends_on:
            raise ValidationFailed("The session must end after it starts.", field="ends_on")
        obj = await self.get(uow, AcademicSession, session_id, lock=True)
        before = snapshot(obj)
        obj.code, obj.name, obj.starts_on, obj.ends_on = (
            normalise_code(code),
            name.strip(),
            starts_on,
            ends_on,
        )
        await self._updated(uow, principal, obj, before)
        return obj

    async def make_current(
        self, uow: UnitOfWork, principal: Principal, session_id: uuid.UUID
    ) -> AcademicSession:
        obj = await self.get(uow, AcademicSession, session_id, lock=True)
        if obj.archived_at is not None:
            raise InvalidState("Restore this session before making it current.")
        if obj.is_current:
            return obj
        await uow.session.execute(
            update(AcademicSession).where(AcademicSession.is_current.is_(True)).values(is_current=False)
        )
        await uow.flush()
        obj.is_current = True
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "session.made_current",
            entity_type="session",
            entity_id=obj.id,
            summary=f"{obj.code} is now the current session",
        )
        return obj

    async def list_terms(self, uow: UnitOfWork, session_id: uuid.UUID) -> list[Term]:
        await self.get(uow, AcademicSession, session_id)
        return list(
            (
                await uow.session.scalars(
                    select(Term).where(Term.session_id == session_id).order_by(Term.sequence)
                )
            ).all()
        )

    async def create_term(
        self,
        uow: UnitOfWork,
        principal: Principal,
        session_id: uuid.UUID,
        *,
        code: str,
        name: str,
        sequence: int | None,
        starts_on: date | None,
        ends_on: date | None,
    ) -> Term:
        session = await self.get(uow, AcademicSession, session_id)
        self._check_term_dates(session, starts_on, ends_on)
        if sequence is None:
            sequence = (
                await uow.session.execute(
                    select(func.coalesce(func.max(Term.sequence), 0)).where(Term.session_id == session_id)
                )
            ).scalar_one() + 1
        obj = Term(
            tenant_id=uow.require_tenant(),
            session_id=session.id,
            code=normalise_code(code),
            name=name.strip(),
            sequence=sequence,
            starts_on=starts_on,
            ends_on=ends_on,
        )
        await self._created(uow, principal, obj)
        return obj

    async def update_term(
        self,
        uow: UnitOfWork,
        principal: Principal,
        term_id: uuid.UUID,
        *,
        code: str,
        name: str,
        sequence: int,
        starts_on: date | None,
        ends_on: date | None,
    ) -> Term:
        obj = await self.get(uow, Term, term_id, lock=True)
        session = await self.get(uow, AcademicSession, obj.session_id)
        self._check_term_dates(session, starts_on, ends_on)
        before = snapshot(obj)
        obj.code, obj.name, obj.sequence = normalise_code(code), name.strip(), sequence
        obj.starts_on, obj.ends_on = starts_on, ends_on
        await self._updated(uow, principal, obj, before)
        return obj

    @staticmethod
    def _check_term_dates(session: AcademicSession, starts_on: date | None, ends_on: date | None) -> None:
        if starts_on and ends_on and starts_on >= ends_on:
            raise ValidationFailed("The term must end after it starts.", field="ends_on")
        for d, field in ((starts_on, "starts_on"), (ends_on, "ends_on")):
            if d and not (session.starts_on <= d <= session.ends_on):
                raise ValidationFailed(
                    f"Term dates must fall within the session ({session.starts_on:%d %b %Y} – {session.ends_on:%d %b %Y}).",
                    field=field,
                )

    async def copy_structure(
        self, uow: UnitOfWork, principal: Principal, target_id: uuid.UUID, source_id: uuid.UUID
    ) -> dict[str, int]:
        """Clone terms and cohorts from a previous session into a new one (docs/03 W3: "copy previous
        session"). Existing codes in the target are skipped, so the action is safe to repeat."""
        if target_id == source_id:
            raise ValidationFailed("Choose a different session to copy from.", field="source_session_id")
        target = await self.get(uow, AcademicSession, target_id, lock=True)
        source = await self.get(uow, AcademicSession, source_id)
        existing_terms = {t.code for t in await self.list_terms(uow, target.id)}
        existing_cohorts = set(
            (await uow.session.scalars(select(Cohort.code).where(Cohort.session_id == target.id))).all()
        )
        terms = cohorts = 0
        for t in await self.list_terms(uow, source.id):
            if t.code in existing_terms:
                continue
            uow.session.add(
                Term(
                    tenant_id=target.tenant_id,
                    session_id=target.id,
                    code=t.code,
                    name=t.name,
                    sequence=t.sequence,
                )
            )
            terms += 1
        source_cohorts = (
            await uow.session.scalars(
                select(Cohort).where(Cohort.session_id == source.id, Cohort.archived_at.is_(None))
            )
        ).all()
        for c in source_cohorts:
            if c.code in existing_cohorts:
                continue
            uow.session.add(
                Cohort(
                    tenant_id=target.tenant_id,
                    session_id=target.id,
                    program_id=c.program_id,
                    code=c.code,
                    name=c.name,
                )
            )
            cohorts += 1
        await flush_checked(uow, MESSAGES)
        await record(
            uow,
            Actor.from_principal(principal),
            "session.structure_copied",
            entity_type="session",
            entity_id=target.id,
            summary=f"Copied {terms} terms and {cohorts} cohorts from {source.code} into {target.code}",
            after={"source_session": str(source.id), "terms": terms, "cohorts": cohorts},
        )
        return {"terms": terms, "cohorts": cohorts}

    # ---- departments ----------------------------------------------------------------------------
    async def _check_department_quota(self, uow: UnitOfWork, adding: int) -> None:
        active = (
            await uow.session.execute(
                select(func.count()).select_from(Department).where(Department.archived_at.is_(None))
            )
        ).scalar_one()
        if active + adding > 1:
            await EntitlementService(self.infra).require(uow, F.MULTIPLE_DEPARTMENTS)

    async def list_departments(self, uow: UnitOfWork, *, include_archived: bool = False) -> list[Department]:
        stmt = select(Department).order_by(Department.name)
        if not include_archived:
            stmt = stmt.where(Department.archived_at.is_(None))
        return list((await uow.session.scalars(stmt)).all())

    async def create_department(
        self, uow: UnitOfWork, principal: Principal, *, code: str, name: str
    ) -> Department:
        await self._check_department_quota(uow, adding=1)
        obj = Department(tenant_id=uow.require_tenant(), code=normalise_code(code), name=name.strip())
        await self._created(uow, principal, obj)
        return obj

    async def update_department(
        self, uow: UnitOfWork, principal: Principal, dept_id: uuid.UUID, *, code: str, name: str
    ) -> Department:
        obj = await self.get(uow, Department, dept_id, lock=True)
        before = snapshot(obj)
        obj.code, obj.name = normalise_code(code), name.strip()
        await self._updated(uow, principal, obj, before)
        return obj

    async def _active_department(self, uow: UnitOfWork, dept_id: uuid.UUID | None) -> uuid.UUID | None:
        if dept_id is None:
            return None
        dept = await self.get(uow, Department, dept_id)
        if dept.archived_at is not None:
            raise ValidationFailed("That department is archived.", field="department_id")
        return dept.id

    # ---- programs -------------------------------------------------------------------------------
    async def list_programs(self, uow: UnitOfWork, *, include_archived: bool = False) -> list[Program]:
        stmt = select(Program).order_by(Program.name)
        if not include_archived:
            stmt = stmt.where(Program.archived_at.is_(None))
        return list((await uow.session.scalars(stmt)).all())

    async def create_program(
        self,
        uow: UnitOfWork,
        principal: Principal,
        *,
        code: str,
        name: str,
        department_id: uuid.UUID | None,
        level: str | None,
        duration_terms: int | None,
    ) -> Program:
        obj = Program(
            tenant_id=uow.require_tenant(),
            code=normalise_code(code),
            name=name.strip(),
            department_id=await self._active_department(uow, department_id),
            level=(level or "").strip() or None,
            duration_terms=duration_terms,
        )
        await self._created(uow, principal, obj)
        return obj

    async def update_program(
        self,
        uow: UnitOfWork,
        principal: Principal,
        program_id: uuid.UUID,
        *,
        code: str,
        name: str,
        department_id: uuid.UUID | None,
        level: str | None,
        duration_terms: int | None,
    ) -> Program:
        obj = await self.get(uow, Program, program_id, lock=True)
        before = snapshot(obj)
        obj.code, obj.name = normalise_code(code), name.strip()
        if department_id != obj.department_id:
            obj.department_id = await self._active_department(uow, department_id)
        obj.level, obj.duration_terms = (level or "").strip() or None, duration_terms
        await self._updated(uow, principal, obj, before)
        return obj

    # ---- cohorts --------------------------------------------------------------------------------
    async def list_cohorts(
        self,
        uow: UnitOfWork,
        *,
        session_id: uuid.UUID | None = None,
        program_id: uuid.UUID | None = None,
        include_archived: bool = False,
    ) -> list[Cohort]:
        stmt = select(Cohort).order_by(Cohort.code)
        if session_id:
            stmt = stmt.where(Cohort.session_id == session_id)
        if program_id:
            stmt = stmt.where(Cohort.program_id == program_id)
        if not include_archived:
            stmt = stmt.where(Cohort.archived_at.is_(None))
        return list((await uow.session.scalars(stmt)).all())

    async def create_cohort(
        self,
        uow: UnitOfWork,
        principal: Principal,
        *,
        code: str,
        name: str,
        program_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> Cohort:
        program = await self.get(uow, Program, program_id)
        session = await self.get(uow, AcademicSession, session_id)
        if program.archived_at is not None:
            raise ValidationFailed("That program is archived.", field="program_id")
        if session.archived_at is not None:
            raise ValidationFailed("That session is archived.", field="session_id")
        obj = Cohort(
            tenant_id=uow.require_tenant(),
            code=normalise_code(code),
            name=name.strip(),
            program_id=program.id,
            session_id=session.id,
        )
        await self._created(uow, principal, obj)
        return obj

    async def update_cohort(
        self, uow: UnitOfWork, principal: Principal, cohort_id: uuid.UUID, *, code: str, name: str
    ) -> Cohort:
        obj = await self.get(uow, Cohort, cohort_id, lock=True)
        before = snapshot(obj)
        obj.code, obj.name = normalise_code(code), name.strip()
        await self._updated(uow, principal, obj, before)
        return obj

    # ---- courses --------------------------------------------------------------------------------
    async def list_courses(
        self,
        uow: UnitOfWork,
        *,
        q: str | None = None,
        department_id: uuid.UUID | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Course], int]:
        stmt = select(Course)
        if q:
            like = f"%{q.strip().lower()}%"
            stmt = stmt.where(func.lower(Course.code).like(like) | func.lower(Course.name).like(like))
        if department_id:
            stmt = stmt.where(Course.department_id == department_id)
        if not include_archived:
            stmt = stmt.where(Course.archived_at.is_(None))
        total = (await uow.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (await uow.session.scalars(stmt.order_by(Course.code).limit(limit).offset(offset))).all()
        return list(rows), int(total)

    async def create_course(
        self,
        uow: UnitOfWork,
        principal: Principal,
        *,
        code: str,
        name: str,
        department_id: uuid.UUID | None,
        credits: Decimal | None,
    ) -> Course:
        obj = Course(
            tenant_id=uow.require_tenant(),
            code=normalise_code(code),
            name=name.strip(),
            department_id=await self._active_department(uow, department_id),
            credits=credits,
        )
        await self._created(uow, principal, obj)
        return obj

    async def update_course(
        self,
        uow: UnitOfWork,
        principal: Principal,
        course_id: uuid.UUID,
        *,
        code: str,
        name: str,
        department_id: uuid.UUID | None,
        credits: Decimal | None,
    ) -> Course:
        obj = await self.get(uow, Course, course_id, lock=True)
        before = snapshot(obj)
        obj.code, obj.name, obj.credits = normalise_code(code), name.strip(), credits
        if department_id != obj.department_id:
            obj.department_id = await self._active_department(uow, department_id)
        await self._updated(uow, principal, obj, before)
        return obj

    async def counts(self, uow: UnitOfWork) -> dict[str, int]:
        out = {}
        for key, model in (
            ("sessions", AcademicSession),
            ("departments", Department),
            ("programs", Program),
            ("cohorts", Cohort),
            ("courses", Course),
        ):
            stmt = select(func.count()).select_from(model)
            if hasattr(model, "archived_at"):
                stmt = stmt.where(model.archived_at.is_(None))
            out[key] = int((await uow.session.execute(stmt)).scalar_one())
        return out
