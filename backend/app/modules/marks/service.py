"""Marks entry (P8.1, P8.2, P8.4; docs/03 W6).

Who may change what:
* administrators (``marks.enter_all``) — any paper × cohort while marks entry is open or closed, unless
  the paper × cohort is locked;
* faculty (``marks.enter_assigned``) — only papers × cohorts assigned to them, only while entry is open
  and their submission is still open (or was returned to them).

Saves are all-or-nothing and optimistic: each changed row carries the version the client last saw; if any
row moved on in the meantime nothing is saved and the current values come back (HTTP 409).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import Conflict, InvalidState, NotFound, PermissionDenied, ValidationFailed
from app.core.http import Principal
from app.modules.academics.models import Cohort, Course
from app.modules.audit.service import Actor, record
from app.modules.directory.models import CohortMembership, Student
from app.modules.examinations.models import (
    ExamCohort,
    Examination,
    ExamPaper,
    PaperAssignment,
    PaperSubmission,
)
from app.modules.identity.models import User
from app.modules.identity.permissions import P
from app.modules.marks.models import ATTENDANCE, MarkEntry
from app.modules.results.staleness import marks_changed

ROSTER_STATUSES = ("active", "graduated")
MAX_AUDITED_CHANGES = 200


@dataclass(frozen=True)
class Change:
    student_id: uuid.UUID
    attendance: str
    components: dict[str, str | None]
    version: int | None  # None = the client believes there is no entry yet


@dataclass
class Sheet:
    exam: Examination
    paper: ExamPaper
    course: Course
    cohort: Cohort
    submission: PaperSubmission | None
    students: list[Student]
    entries: dict[uuid.UUID, MarkEntry]
    can_edit: bool
    can_submit: bool
    can_return: bool
    names: dict[uuid.UUID, str] = field(default_factory=dict)

    @property
    def complete(self) -> int:
        return sum(
            1
            for s in self.students
            if (e := self.entries.get(s.id)) is not None and is_complete(e, self.paper)
        )


def is_complete(entry: MarkEntry, paper: ExamPaper) -> bool:
    if entry.attendance != "present":
        return True
    return all(entry.components.get(c["code"]) not in (None, "") for c in paper.components)


def parse_mark(raw: Any, component: dict[str, Any]) -> str | None:
    """A component value as a canonical decimal string, or None for blank. Raises ValidationFailed."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        raise ValidationFailed(f"“{raw}” isn't a number.", field=component["code"]) from None
    if not value.is_finite():
        raise ValidationFailed(f"“{raw}” isn't a number.", field=component["code"])
    if value.as_tuple().exponent < -2:  # type: ignore[operator]
        raise ValidationFailed("Use at most two decimal places.", field=component["code"])
    maximum = Decimal(component["max"])
    if value < 0 or value > maximum:
        raise ValidationFailed(
            f"{component['label']}: {value.normalize():f} is outside 0–{maximum.normalize():f}.",
            field=component["code"],
        )
    return format(value.normalize(), "f")  # canonical: "35.50" and "35.5" are the same mark


class MarksService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    # ---- scope ----------------------------------------------------------------------------------
    async def _context(
        self,
        uow: UnitOfWork,
        exam_id: uuid.UUID,
        paper_id: uuid.UUID,
        cohort_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> tuple[Examination, ExamPaper, Course, Cohort, PaperSubmission | None]:
        stmt = select(Examination).where(Examination.id == exam_id)
        exam = (await uow.session.scalars(stmt.with_for_update() if lock else stmt)).one_or_none()
        if exam is None:
            raise NotFound("Exam not found")
        row = (
            await uow.session.execute(
                select(ExamPaper, Course)
                .join(Course, Course.id == ExamPaper.course_id)
                .where(ExamPaper.id == paper_id, ExamPaper.exam_id == exam.id)
            )
        ).first()
        if row is None:
            raise NotFound("Paper not found")
        cohort = (
            await uow.session.scalars(
                select(Cohort)
                .join(ExamCohort, ExamCohort.cohort_id == Cohort.id)
                .where(ExamCohort.exam_id == exam.id, Cohort.id == cohort_id)
            )
        ).one_or_none()
        if cohort is None:
            raise NotFound("That cohort doesn't sit this exam")
        sub_stmt = select(PaperSubmission).where(
            PaperSubmission.exam_paper_id == row[0].id, PaperSubmission.cohort_id == cohort.id
        )
        submission = (
            await uow.session.scalars(sub_stmt.with_for_update() if lock else sub_stmt)
        ).one_or_none()
        return exam, row[0], row[1], cohort, submission

    async def _assigned(
        self, uow: UnitOfWork, principal: Principal, paper_id: uuid.UUID, cohort_id: uuid.UUID
    ) -> bool:
        return (
            await uow.session.scalars(
                select(PaperAssignment.user_id).where(
                    PaperAssignment.exam_paper_id == paper_id,
                    PaperAssignment.cohort_id == cohort_id,
                    PaperAssignment.user_id == principal.user_id,
                )
            )
        ).first() is not None

    async def _access(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam: Examination,
        paper: ExamPaper,
        cohort: Cohort,
        submission: PaperSubmission | None,
    ) -> tuple[bool, bool, bool]:
        """(can_view, can_edit, can_submit). Faculty who aren't assigned see nothing (404, not 403)."""
        admin = principal.has(P.MARKS_ENTER_ALL)
        assigned = principal.has(P.MARKS_ENTER_ASSIGNED) and await self._assigned(
            uow, principal, paper.id, cohort.id
        )
        if not (admin or assigned):
            return False, False, False
        status = submission.status if submission else "open"
        if status == "locked":
            return True, False, False
        if exam.status == "marks_entry_open":
            editable = admin or status in ("open", "returned")
        elif exam.status in ("marks_entry_closed", "processed", "correction_draft"):
            # After processing, a change sets the results aside (results.staleness). In a correction of
            # published results, administrators change marks while the live version stays visible.
            editable = admin
        else:
            editable = False
        return True, editable, editable and status in ("open", "returned")

    async def roster(self, uow: UnitOfWork, cohort_id: uuid.UUID) -> list[Student]:
        return list(
            (
                await uow.session.scalars(
                    select(Student)
                    .join(CohortMembership, CohortMembership.student_id == Student.id)
                    .where(CohortMembership.cohort_id == cohort_id, Student.status.in_(ROSTER_STATUSES))
                    .order_by(Student.enrollment_no)
                )
            ).all()
        )

    # ---- reads ----------------------------------------------------------------------------------
    async def sheet(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID,
        paper_id: uuid.UUID,
        cohort_id: uuid.UUID,
    ) -> Sheet:
        exam, paper, course, cohort, submission = await self._context(uow, exam_id, paper_id, cohort_id)
        can_view, can_edit, can_submit = await self._access(uow, principal, exam, paper, cohort, submission)
        if not can_view:
            raise NotFound("Paper not found")
        students = await self.roster(uow, cohort.id)
        entries = {
            e.student_id: e
            for e in (
                await uow.session.scalars(
                    select(MarkEntry).where(
                        MarkEntry.exam_paper_id == paper.id, MarkEntry.cohort_id == cohort.id
                    )
                )
            ).all()
        }
        user_ids = {e.updated_by for e in entries.values() if e.updated_by}
        if submission and submission.submitted_by:
            user_ids.add(submission.submitted_by)
        names: dict[uuid.UUID, str] = {}
        if user_ids:
            rows = await uow.session.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))
            names = {uid: name for uid, name in rows.all()}  # noqa: C416
        can_return = (
            principal.has(P.PAPERS_REVIEW) and submission is not None and submission.status == "submitted"
        )
        return Sheet(
            exam,
            paper,
            course,
            cohort,
            submission,
            students,
            entries,
            can_edit,
            can_submit,
            can_return,
            names,
        )

    async def my_work(self, uow: UnitOfWork, principal: Principal) -> list[dict[str, Any]]:
        """Papers × cohorts this person can enter marks for, in exams that are taking marks."""
        admin = principal.has(P.MARKS_ENTER_ALL)
        stmt = (
            select(Examination, ExamPaper, Course, Cohort, PaperSubmission)
            .join(ExamPaper, ExamPaper.exam_id == Examination.id)
            .join(Course, Course.id == ExamPaper.course_id)
            .join(ExamCohort, ExamCohort.exam_id == Examination.id)
            .join(Cohort, Cohort.id == ExamCohort.cohort_id)
            .outerjoin(
                PaperSubmission,
                (PaperSubmission.exam_paper_id == ExamPaper.id) & (PaperSubmission.cohort_id == Cohort.id),
            )
            .where(Examination.status.in_(("marks_entry_open", "marks_entry_closed")))
            .order_by(
                Examination.marks_deadline.asc().nulls_last(), Examination.name, Course.code, Cohort.code
            )
        )
        if not admin:
            if not principal.has(P.MARKS_ENTER_ASSIGNED):
                return []
            stmt = stmt.join(
                PaperAssignment,
                (PaperAssignment.exam_paper_id == ExamPaper.id)
                & (PaperAssignment.cohort_id == Cohort.id)
                & (PaperAssignment.user_id == principal.user_id),
            )
        rows = (await uow.session.execute(stmt)).all()
        if not rows:
            return []
        cohort_ids = {c.id for _e, _p, _k, c, _s in rows}
        paper_ids = {p.id for _e, p, _k, _c, _s in rows}
        size_rows = await uow.session.execute(
            select(CohortMembership.cohort_id, func.count())
            .join(Student, Student.id == CohortMembership.student_id)
            .where(CohortMembership.cohort_id.in_(cohort_ids), Student.status.in_(ROSTER_STATUSES))
            .group_by(CohortMembership.cohort_id)
        )
        sizes = {cid: int(n) for cid, n in size_rows.all()}
        entry_rows = await uow.session.execute(
            select(MarkEntry.exam_paper_id, MarkEntry.cohort_id, func.count())
            .where(MarkEntry.exam_paper_id.in_(paper_ids))
            .group_by(MarkEntry.exam_paper_id, MarkEntry.cohort_id)
        )
        entered = {(pid, cid): int(n) for pid, cid, n in entry_rows.all()}
        return [
            {
                "exam": e,
                "paper": p,
                "course": k,
                "cohort": c,
                "submission_status": s.status if s else "open",
                "students": int(sizes.get(c.id, 0)),
                "entered": int(entered.get((p.id, c.id), 0)),
            }
            for e, p, k, c, s in rows
        ]

    # ---- writes ---------------------------------------------------------------------------------
    async def save(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID,
        paper_id: uuid.UUID,
        cohort_id: uuid.UUID,
        changes: Sequence[Change],
        *,
        source: str = "grid",
    ) -> list[MarkEntry]:
        exam, paper, course, cohort, submission = await self._context(
            uow, exam_id, paper_id, cohort_id, lock=True
        )
        can_view, can_edit, _ = await self._access(uow, principal, exam, paper, cohort, submission)
        if not can_view:
            raise NotFound("Paper not found")
        if not can_edit:
            raise InvalidState(_why_locked(exam, submission))
        roster = {s.id: s for s in await self.roster(uow, cohort.id)}
        if len({c.student_id for c in changes}) != len(changes):
            raise ValidationFailed("Each student can appear only once per save.", field="changes")
        components = {c["code"]: c for c in paper.components}
        existing = {
            e.student_id: e
            for e in (
                await uow.session.scalars(
                    select(MarkEntry)
                    .where(
                        MarkEntry.exam_paper_id == paper.id,
                        MarkEntry.student_id.in_([c.student_id for c in changes]),
                    )
                    .with_for_update()
                )
            ).all()
        }
        conflicts = [
            {
                "student_id": str(c.student_id),
                "current_version": existing[c.student_id].version if c.student_id in existing else None,
            }
            for c in changes
            if (existing[c.student_id].version if c.student_id in existing else None) != c.version
        ]
        if conflicts:
            raise Conflict(
                "Someone else changed some of these marks. Their latest values are loaded; check and save again.",
                conflicts=conflicts,
            )
        saved: list[MarkEntry] = []
        audit: list[dict[str, Any]] = []
        for change in changes:
            student = roster.get(change.student_id)
            if student is None:
                raise ValidationFailed("A student in this save isn't in the cohort.", field="changes")
            if change.attendance not in ATTENDANCE:
                raise ValidationFailed("Unknown attendance code.", field="attendance")
            unknown = set(change.components) - set(components)
            if unknown:
                raise ValidationFailed(f"Unknown component {sorted(unknown)[0]}.", field="components")
            entry = existing.get(change.student_id)
            values = dict(entry.components) if entry else {}
            for code, raw in change.components.items():
                values[code] = parse_mark(raw, components[code])
            if change.attendance != "present":
                values = {}  # an absent/exempt/withheld student has no marks to keep
            values = {k: v for k, v in values.items() if v is not None}
            total = None
            if change.attendance == "present" and all(code in values for code in components):
                total = sum((Decimal(v) for v in values.values()), Decimal(0))
            if entry is None:
                if not values and change.attendance == "present":
                    continue  # nothing to store
                entry = MarkEntry(
                    tenant_id=exam.tenant_id,
                    exam_id=exam.id,
                    exam_paper_id=paper.id,
                    cohort_id=cohort.id,
                    student_id=student.id,
                    components=values,
                    total=total,
                    attendance=change.attendance,
                    version=1,
                    source=source,
                    updated_by=principal.user_id,
                )
                uow.session.add(entry)
                audit.append(
                    {
                        "student": student.enrollment_no,
                        "from": None,
                        "to": _describe(values, change.attendance),
                    }
                )
            else:
                if entry.components == values and entry.attendance == change.attendance:
                    saved.append(entry)
                    continue  # unchanged: no version bump, no audit noise
                audit.append(
                    {
                        "student": student.enrollment_no,
                        "from": _describe(entry.components, entry.attendance),
                        "to": _describe(values, change.attendance),
                    }
                )
                entry.components, entry.total, entry.attendance = values, total, change.attendance
                entry.version += 1
                entry.source, entry.updated_by = source, principal.user_id
            saved.append(entry)
        await uow.flush()
        if audit:
            await record(
                uow,
                Actor.from_principal(principal),
                "marks.entered",
                entity_type="exam",
                entity_id=exam.id,
                summary=f"Saved {len(audit)} mark(s) for {course.code} / {cohort.code}",
                after={
                    "paper": course.code,
                    "cohort": cohort.code,
                    "source": source,
                    "changes": audit[:MAX_AUDITED_CHANGES],
                    "truncated": max(0, len(audit) - MAX_AUDITED_CHANGES),
                },
            )
            await marks_changed(uow, Actor.from_principal(principal), exam)
        return saved

    async def submit(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID,
        paper_id: uuid.UUID,
        cohort_id: uuid.UUID,
    ) -> None:
        exam, paper, course, cohort, submission = await self._context(
            uow, exam_id, paper_id, cohort_id, lock=True
        )
        can_view, _, can_submit = await self._access(uow, principal, exam, paper, cohort, submission)
        if not can_view:
            raise NotFound("Paper not found")
        if submission is None or not can_submit:
            raise InvalidState(_why_locked(exam, submission))
        students = await self.roster(uow, cohort.id)
        entries = {
            e.student_id: e
            for e in (
                await uow.session.scalars(
                    select(MarkEntry).where(
                        MarkEntry.exam_paper_id == paper.id, MarkEntry.cohort_id == cohort.id
                    )
                )
            ).all()
        }
        missing = [
            s.enrollment_no for s in students if s.id not in entries or not is_complete(entries[s.id], paper)
        ]
        if missing:
            raise InvalidState(
                f"{len(missing)} student(s) still need marks or an attendance code, e.g. {', '.join(missing[:3])}."
            )
        submission.status = "submitted"
        submission.submitted_by, submission.submitted_at = principal.user_id, utcnow()
        submission.return_reason = None
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "paper.submitted",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Submitted {course.code} / {cohort.code} ({len(students)} students)",
        )

    async def return_paper(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID,
        paper_id: uuid.UUID,
        cohort_id: uuid.UUID,
        reason: str,
    ) -> None:
        if not principal.has(P.PAPERS_REVIEW):
            raise PermissionDenied()
        exam, _paper, course, cohort, submission = await self._context(
            uow, exam_id, paper_id, cohort_id, lock=True
        )
        if submission is None or submission.status != "submitted":
            raise InvalidState("Only a submitted paper can be returned.")
        if len(reason.strip()) < 3:
            raise ValidationFailed("Tell the faculty member what to fix.", field="reason")
        submission.status = "returned"
        submission.returned_by, submission.returned_at = principal.user_id, utcnow()
        submission.return_reason = reason.strip()
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "paper.returned",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Returned {course.code} / {cohort.code}",
            reason=reason.strip(),
        )


def _describe(values: dict[str, Any], attendance: str) -> str:
    if attendance != "present":
        return attendance
    return ", ".join(f"{k} {v}" for k, v in sorted(values.items())) or "blank"


def _why_locked(exam: Examination, submission: PaperSubmission | None) -> str:
    if submission is not None and submission.status == "locked":
        return "These marks are locked."
    if submission is not None and submission.status == "submitted":
        return "This paper has been submitted. An administrator can return it if changes are needed."
    if exam.status == "draft":
        return "Marks entry hasn't opened for this exam yet."
    if exam.status == "marks_entry_closed":
        return "Marks entry is closed. Ask an administrator to reopen it."
    if exam.status in ("published", "scheduled", "approved"):
        return "These results are approved or published. An administrator can start a correction to change marks."
    return "Marks can't be changed at this stage."
