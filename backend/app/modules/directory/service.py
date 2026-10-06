"""Student directory use cases (P6.2, docs/07 §2.4, docs/12).

* Only ``active`` students count towards ``max_students``; every status change that enters or leaves
  ``active`` moves the usage counter in the same transaction (row-locked, so parallel requests and
  imports can't overshoot the limit).
* Enrollment numbers are normalised once (upper case, no spaces) and become the student's login id, so
  they're frozen once an account exists — activation codes are bound to them.
* A student is in at most one cohort per program per session; assigning another cohort of the same
  program and session *moves* the student.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import Select, and_, delete, func, or_, select, tuple_

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import Conflict, InvalidState, NotFound, ValidationFailed
from app.core.http import Principal
from app.core.integrity import ConstraintMessage, flush_checked
from app.core.pagination import clamp_limit, decode_cursor, encode_cursor
from app.modules.academics.models import AcademicSession, Cohort, Program
from app.modules.audit.service import Actor, diff, record
from app.modules.directory.models import STUDENT_STATUSES, CohortMembership, Student
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EntitlementService
from app.modules.identity.models import User
from app.modules.identity.sessions import SessionService

MESSAGES = {
    "uq_students__tenant_enrollment": ConstraintMessage(
        "A student with this enrollment number already exists.", "enrollment_no"
    ),
    "uq_cohort_memberships__one_per_program_session": ConstraintMessage(
        "This student is already in another cohort of the same program for that session.", "cohort_id"
    ),
}

ENROLLMENT_RE = re.compile(r"^[A-Z0-9][A-Z0-9/._-]{0,39}$")
EDITABLE = (
    "enrollment_no",
    "full_name",
    "date_of_birth",
    "email",
    "phone",
    "guardian_name",
    "admission_year",
)
SNAPSHOT = (*EDITABLE, "status")


def normalise_enrollment(raw: str) -> str:
    """``" 1023 03001 "`` → ``"102303001"``; ``"cse/21/045"`` → ``"CSE/21/045"``."""
    value = "".join(str(raw).split()).upper()
    if not value:
        raise ValidationFailed("Enter an enrollment number.", field="enrollment_no")
    if not ENROLLMENT_RE.match(value):
        raise ValidationFailed(
            "Enrollment numbers can use letters, digits and / . _ - (up to 40 characters).",
            field="enrollment_no",
        )
    return value


def clean_name(raw: str) -> str:
    value = " ".join(str(raw).split())
    if not value:
        raise ValidationFailed("Enter the student's name.", field="full_name")
    return value[:200]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass
class StudentData:
    enrollment_no: str
    full_name: str
    date_of_birth: date | None = None
    email: str | None = None
    phone: str | None = None
    guardian_name: str | None = None
    admission_year: int | None = None

    def normalised(self) -> StudentData:
        return StudentData(
            enrollment_no=normalise_enrollment(self.enrollment_no),
            full_name=clean_name(self.full_name),
            date_of_birth=self.date_of_birth,
            email=(self.email or "").strip().lower() or None,
            phone=" ".join((self.phone or "").split()) or None,
            guardian_name=" ".join((self.guardian_name or "").split()) or None,
            admission_year=self.admission_year,
        )


@dataclass(frozen=True)
class MembershipView:
    cohort_id: uuid.UUID
    cohort_code: str
    cohort_name: str
    session_id: uuid.UUID
    session_code: str
    session_is_current: bool
    program_id: uuid.UUID
    program_code: str


@dataclass
class StudentView:
    student: Student
    account: str  # none | pending | active | disabled
    memberships: list[MembershipView] = field(default_factory=list)


@dataclass(frozen=True)
class StudentFilters:
    q: str | None = None
    status: str | None = None
    cohort_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    account: str | None = None  # none | pending | active


def _snapshot(s: Student) -> dict[str, Any]:
    return {f: getattr(s, f) for f in SNAPSHOT}


class StudentService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra
        self.ent = EntitlementService(infra)

    # ---- reads ----------------------------------------------------------------------------------
    async def get(self, uow: UnitOfWork, student_id: uuid.UUID, *, lock: bool = False) -> Student:
        stmt = select(Student).where(Student.id == student_id)
        if lock:
            stmt = stmt.with_for_update()
        row = (await uow.session.scalars(stmt)).one_or_none()
        if row is None:
            raise NotFound("Student not found")
        return row

    def _filtered(self, filters: StudentFilters) -> Select[Student]:
        stmt = select(Student)
        if filters.status:
            if filters.status not in STUDENT_STATUSES:
                raise ValidationFailed("Unknown status.", field="status")
            stmt = stmt.where(Student.status == filters.status)
        if filters.q and filters.q.strip():
            q = " ".join(filters.q.split()).lower()
            like = f"%{_escape_like(q)}%"
            enroll_prefix = f"{_escape_like(''.join(q.split()).upper())}%"
            stmt = stmt.where(
                or_(
                    func.lower(Student.full_name).like(like, escape="\\"),
                    Student.enrollment_no.like(enroll_prefix, escape="\\"),
                    func.lower(Student.email).like(like, escape="\\"),
                )
            )
        if filters.cohort_id or filters.session_id or filters.program_id:
            member = select(CohortMembership.student_id)
            if filters.cohort_id:
                member = member.where(CohortMembership.cohort_id == filters.cohort_id)
            if filters.session_id:
                member = member.where(CohortMembership.session_id == filters.session_id)
            if filters.program_id:
                member = member.where(CohortMembership.program_id == filters.program_id)
            stmt = stmt.where(Student.id.in_(member))
        if filters.account:
            if filters.account == "none":
                stmt = stmt.where(Student.user_id.is_(None))
            elif filters.account in ("pending", "active", "disabled"):
                status = {"pending": "invited", "active": "active", "disabled": "disabled"}[filters.account]
                stmt = stmt.where(Student.user_id.in_(select(User.id).where(User.status == status)))
            else:
                raise ValidationFailed("Unknown account filter.", field="account")
        return stmt

    async def search(
        self, uow: UnitOfWork, filters: StudentFilters, *, cursor: str | None, limit: int | None
    ) -> tuple[list[StudentView], str | None, int]:
        n = clamp_limit(limit)
        base = self._filtered(filters)
        total = (await uow.session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        stmt = base.order_by(Student.enrollment_no, Student.id).limit(n + 1)
        after = decode_cursor(cursor)
        if after:
            try:
                stmt = stmt.where(
                    tuple_(Student.enrollment_no, Student.id) > (str(after[0]), uuid.UUID(after[1]))
                )
            except (IndexError, ValueError) as exc:
                raise ValidationFailed("Invalid cursor.", field="cursor") from exc
        rows = list((await uow.session.scalars(stmt)).all())
        next_cursor = None
        if len(rows) > n:
            rows = rows[:n]
            next_cursor = encode_cursor([rows[-1].enrollment_no, str(rows[-1].id)])
        return await self._views(uow, rows), next_cursor, int(total)

    async def detail(self, uow: UnitOfWork, student_id: uuid.UUID) -> StudentView:
        return (await self._views(uow, [await self.get(uow, student_id)]))[0]

    async def _views(self, uow: UnitOfWork, rows: Sequence[Student]) -> list[StudentView]:
        if not rows:
            return []
        ids = [r.id for r in rows]
        user_ids = [r.user_id for r in rows if r.user_id]
        accounts: dict[uuid.UUID, str] = {}
        if user_ids:
            for uid, status in (
                await uow.session.execute(select(User.id, User.status).where(User.id.in_(user_ids)))
            ).all():
                accounts[uid] = {"invited": "pending"}.get(status, status)
        memberships: dict[uuid.UUID, list[MembershipView]] = {i: [] for i in ids}
        stmt = (
            select(
                CohortMembership.student_id,
                Cohort.id,
                Cohort.code,
                Cohort.name,
                AcademicSession.id,
                AcademicSession.code,
                AcademicSession.is_current,
                AcademicSession.starts_on,
                Program.id,
                Program.code,
            )
            .join(Cohort, Cohort.id == CohortMembership.cohort_id)
            .join(AcademicSession, AcademicSession.id == CohortMembership.session_id)
            .join(Program, Program.id == CohortMembership.program_id)
            .where(CohortMembership.student_id.in_(ids))
            .order_by(AcademicSession.starts_on.desc(), Program.code)
        )
        for sid, cid, ccode, cname, sess_id, sess_code, current, _starts, pid, pcode in (
            await uow.session.execute(stmt)
        ).all():
            memberships[sid].append(
                MembershipView(cid, ccode, cname, sess_id, sess_code, bool(current), pid, pcode)
            )
        return [
            StudentView(r, accounts.get(r.user_id, "none") if r.user_id else "none", memberships[r.id])
            for r in rows
        ]

    async def counts(self, uow: UnitOfWork) -> dict[str, int]:
        rows = (
            await uow.session.execute(select(Student.status, func.count()).group_by(Student.status))
        ).all()
        out = dict.fromkeys(STUDENT_STATUSES, 0)
        out.update({status: int(n) for status, n in rows})
        return out

    # ---- writes ---------------------------------------------------------------------------------
    async def create(
        self,
        uow: UnitOfWork,
        principal: Principal | None,
        data: StudentData,
        *,
        cohort_ids: Iterable[uuid.UUID] = (),
        audit: bool = True,
    ) -> Student:
        clean = data.normalised()
        _check_year(clean.admission_year)
        await self.ent.consume(uow, F.MAX_STUDENTS, 1)
        student = Student(tenant_id=uow.require_tenant(), status="active", **clean.__dict__)
        uow.session.add(student)
        await flush_checked(uow, MESSAGES)
        for cohort_id in cohort_ids:
            await self._assign(uow, student, cohort_id)
        if audit and principal is not None:
            await record(
                uow,
                Actor.from_principal(principal),
                "student.created",
                entity_type="student",
                entity_id=student.id,
                summary=f"Added student {student.enrollment_no} — {student.full_name}",
                after=_snapshot(student),
            )
        return student

    async def update(
        self,
        uow: UnitOfWork,
        principal: Principal,
        student_id: uuid.UUID,
        data: StudentData,
        *,
        version: int,
    ) -> Student:
        student = await self.get(uow, student_id, lock=True)
        if student.version != version:
            raise Conflict(
                "Someone else changed this student while you were editing. Reload to see their changes.",
                current_version=student.version,
            )
        before = _snapshot(student)
        changed = self.apply(student, data.normalised())
        if "enrollment_no" in changed and student.user_id is not None:
            raise InvalidState(
                "The enrollment number is this student's login, so it can't change once an account or "
                "activation code exists."
            )
        if not changed:
            return student
        await self._sync_account_name(uow, student)
        student.version += 1
        await flush_checked(uow, MESSAGES)
        d_before, d_after = diff(before, _snapshot(student))
        await record(
            uow,
            Actor.from_principal(principal),
            "student.updated",
            entity_type="student",
            entity_id=student.id,
            summary=f"Updated student {student.enrollment_no}",
            before=d_before,
            after=d_after,
        )
        return student

    @staticmethod
    def apply(student: Student, clean: StudentData) -> set[str]:
        """Copy normalised fields onto ``student``; returns the names of the fields that changed."""
        _check_year(clean.admission_year)
        changed = set()
        for name in EDITABLE:
            value = getattr(clean, name)
            if getattr(student, name) != value:
                setattr(student, name, value)
                changed.add(name)
        return changed

    async def _sync_account_name(self, uow: UnitOfWork, student: Student) -> None:
        if student.user_id is None:
            return
        user = (await uow.session.scalars(select(User).where(User.id == student.user_id))).one()
        user.full_name = student.full_name
        user.email = student.email

    async def set_status(
        self, uow: UnitOfWork, principal: Principal, student_id: uuid.UUID, status: str, *, reason: str | None
    ) -> Student:
        if status not in STUDENT_STATUSES:
            raise ValidationFailed("Unknown status.", field="status")
        student = await self.get(uow, student_id, lock=True)
        previous = student.status
        if previous == status:
            return student
        if status == "active":
            await self.ent.consume(uow, F.MAX_STUDENTS, 1)
        elif previous == "active":
            await self.ent.release(uow, F.MAX_STUDENTS, 1)
        student.status = status
        student.archived_at = utcnow() if status == "archived" else None
        student.version += 1
        await self._sync_account_status(uow, student)
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            f"student.{'archived' if status == 'archived' else 'status_changed'}",
            entity_type="student",
            entity_id=student.id,
            summary=f"{student.enrollment_no}: {previous} → {status}",
            before={"status": previous},
            after={"status": status},
            reason=reason,
        )
        return student

    async def _sync_account_status(self, uow: UnitOfWork, student: Student) -> None:
        """Archived and withdrawn students can't sign in; graduates keep access to their results."""
        if student.user_id is None:
            return
        user = (
            await uow.session.scalars(select(User).where(User.id == student.user_id).with_for_update())
        ).one()
        if student.status in ("archived", "withdrawn"):
            if user.status != "disabled":
                user.status = "disabled"
                await SessionService(self.infra).revoke_all_for_user(uow, user.id)
        elif user.status == "disabled":
            user.status = "active" if user.password_hash else "invited"

    # ---- cohorts --------------------------------------------------------------------------------
    async def _cohort(self, uow: UnitOfWork, cohort_id: uuid.UUID) -> Cohort:
        cohort = (await uow.session.scalars(select(Cohort).where(Cohort.id == cohort_id))).one_or_none()
        if cohort is None:
            raise NotFound("Cohort not found")
        if cohort.archived_at is not None:
            raise ValidationFailed("That cohort is archived.", field="cohort_id")
        return cohort

    async def _assign(self, uow: UnitOfWork, student: Student, cohort_id: uuid.UUID) -> str | None:
        """Put ``student`` in the cohort, moving them out of a sibling cohort (same program & session).

        Returns the code of the cohort they left, if any."""
        cohort = await self._cohort(uow, cohort_id)
        existing = (
            await uow.session.execute(
                select(CohortMembership.cohort_id, Cohort.code)
                .join(Cohort, Cohort.id == CohortMembership.cohort_id)
                .where(
                    CohortMembership.student_id == student.id,
                    CohortMembership.session_id == cohort.session_id,
                    CohortMembership.program_id == cohort.program_id,
                )
            )
        ).first()
        if existing and existing[0] == cohort.id:
            return None
        if existing:
            await uow.session.execute(
                delete(CohortMembership).where(
                    CohortMembership.student_id == student.id, CohortMembership.cohort_id == existing[0]
                )
            )
        uow.session.add(
            CohortMembership(
                tenant_id=student.tenant_id,
                cohort_id=cohort.id,
                student_id=student.id,
                session_id=cohort.session_id,
                program_id=cohort.program_id,
            )
        )
        await flush_checked(uow, MESSAGES)
        return existing[1] if existing else None

    async def assign_cohort(
        self, uow: UnitOfWork, principal: Principal, student_id: uuid.UUID, cohort_id: uuid.UUID
    ) -> None:
        student = await self.get(uow, student_id, lock=True)
        cohort = await self._cohort(uow, cohort_id)
        left = await self._assign(uow, student, cohort.id)
        await record(
            uow,
            Actor.from_principal(principal),
            "student.cohort_assigned",
            entity_type="student",
            entity_id=student.id,
            summary=(
                f"Moved {student.enrollment_no} from {left} to {cohort.code}"
                if left
                else f"Added {student.enrollment_no} to {cohort.code}"
            ),
            after={"cohort_id": str(cohort.id)},
        )

    async def remove_cohort(
        self, uow: UnitOfWork, principal: Principal, student_id: uuid.UUID, cohort_id: uuid.UUID
    ) -> None:
        student = await self.get(uow, student_id)
        cohort = (await uow.session.scalars(select(Cohort).where(Cohort.id == cohort_id))).one_or_none()
        if cohort is None:
            raise NotFound("Cohort not found")
        result = await uow.session.execute(
            delete(CohortMembership).where(
                CohortMembership.student_id == student.id, CohortMembership.cohort_id == cohort.id
            )
        )
        if not getattr(result, "rowcount", 0):
            raise NotFound("This student isn't in that cohort")
        await record(
            uow,
            Actor.from_principal(principal),
            "student.cohort_removed",
            entity_type="student",
            entity_id=student.id,
            summary=f"Removed {student.enrollment_no} from {cohort.code}",
            before={"cohort_id": str(cohort.id)},
        )

    async def add_to_cohort(
        self, uow: UnitOfWork, principal: Principal, cohort_id: uuid.UUID, student_ids: Sequence[uuid.UUID]
    ) -> dict[str, int]:
        cohort = await self._cohort(uow, cohort_id)
        wanted = list(dict.fromkeys(student_ids))
        students = list(
            (await uow.session.scalars(select(Student).where(Student.id.in_(wanted)).with_for_update())).all()
        )
        if len(students) != len(wanted):
            raise NotFound("Some of those students weren't found")
        added = moved = unchanged = 0
        for student in students:
            already = (
                await uow.session.execute(
                    select(CohortMembership.cohort_id).where(
                        and_(
                            CohortMembership.student_id == student.id,
                            CohortMembership.cohort_id == cohort.id,
                        )
                    )
                )
            ).first()
            if already:
                unchanged += 1
                continue
            left = await self._assign(uow, student, cohort.id)
            if left:
                moved += 1
            else:
                added += 1
        if added or moved:
            await record(
                uow,
                Actor.from_principal(principal),
                "cohort.members_added",
                entity_type="cohort",
                entity_id=cohort.id,
                summary=f"{cohort.code}: {added} added, {moved} moved in from sibling cohorts",
                after={"added": added, "moved": moved},
            )
        return {"added": added, "moved": moved, "unchanged": unchanged}


def _check_year(year: int | None) -> None:
    if year is not None and not 1950 <= year <= 2100:
        raise ValidationFailed("Enter a year between 1950 and 2100.", field="admission_year")
