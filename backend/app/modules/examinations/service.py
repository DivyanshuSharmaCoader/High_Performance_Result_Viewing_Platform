"""Examination setup and lifecycle (P7.4, P7.5, docs/03 W5)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select

from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import Conflict, InvalidState, NotFound, ValidationFailed
from app.core.http import Principal
from app.core.integrity import ConstraintMessage, flush_checked
from app.modules.academics.models import AcademicSession, Cohort, Course, Program, Term
from app.modules.audit.service import Actor, record
from app.modules.directory.models import CohortMembership
from app.modules.examinations.components import max_total, parse_components, to_json
from app.modules.examinations.models import (
    EXAM_KINDS,
    ExamCohort,
    Examination,
    ExamPaper,
    PaperAssignment,
    PaperSubmission,
)
from app.modules.examinations.states import SETUP_EDITABLE, ExamStatus, transition_for
from app.modules.grading.models import GradingScheme
from app.modules.identity.models import User, UserRole
from app.modules.tenancy.models import TenantSettings

MESSAGES = {
    "uq_examinations__tenant_term_name": ConstraintMessage(
        "This term already has an exam with this name.", "name"
    ),
    "uq_exam_papers__tenant_exam_course": ConstraintMessage(
        "This course is already a paper in the exam.", "course_id"
    ),
}


@dataclass
class Check:
    key: str
    ok: bool
    message: str


@dataclass
class ExamView:
    exam: Examination
    term: Term
    session: AcademicSession
    scheme: GradingScheme
    cohorts: list[tuple[Cohort, Program, int]] = field(default_factory=list)  # cohort, program, students
    papers: list[tuple[ExamPaper, Course]] = field(default_factory=list)
    assignments: list[PaperAssignment] = field(default_factory=list)
    submissions: list[PaperSubmission] = field(default_factory=list)
    faculty: dict[uuid.UUID, str] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)


def _snapshot(exam: Examination) -> dict[str, Any]:
    return {
        "name": exam.name,
        "kind": exam.kind,
        "grading_scheme_id": str(exam.grading_scheme_id),
        "marks_deadline": exam.marks_deadline.isoformat() if exam.marks_deadline else None,
        "notes": exam.notes,
    }


class ExamService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    # ---- lookups --------------------------------------------------------------------------------
    async def get(self, uow: UnitOfWork, exam_id: uuid.UUID, *, lock: bool = False) -> Examination:
        stmt = select(Examination).where(Examination.id == exam_id)
        if lock:
            stmt = stmt.with_for_update()
        exam = (await uow.session.scalars(stmt)).one_or_none()
        if exam is None:
            raise NotFound("Exam not found")
        return exam

    async def paper(self, uow: UnitOfWork, exam: Examination, paper_id: uuid.UUID) -> ExamPaper:
        p = (
            await uow.session.scalars(
                select(ExamPaper).where(ExamPaper.id == paper_id, ExamPaper.exam_id == exam.id)
            )
        ).one_or_none()
        if p is None:
            raise NotFound("Paper not found")
        return p

    async def _term(self, uow: UnitOfWork, term_id: uuid.UUID) -> tuple[Term, AcademicSession]:
        row = (
            await uow.session.execute(
                select(Term, AcademicSession)
                .join(AcademicSession, AcademicSession.id == Term.session_id)
                .where(Term.id == term_id)
            )
        ).first()
        if row is None:
            raise ValidationFailed("That term doesn't exist.", field="term_id")
        return row[0], row[1]

    async def _scheme(self, uow: UnitOfWork, scheme_id: uuid.UUID | None) -> GradingScheme:
        if scheme_id is None:
            scheme_id = (
                await uow.session.scalars(select(TenantSettings.default_grading_scheme_id))
            ).one_or_none()
            if scheme_id is None:
                raise ValidationFailed(
                    "Create a grading scheme first, or choose one.", field="grading_scheme_id"
                )
        scheme = (
            await uow.session.scalars(select(GradingScheme).where(GradingScheme.id == scheme_id))
        ).one_or_none()
        if scheme is None:
            raise ValidationFailed("That grading scheme doesn't exist.", field="grading_scheme_id")
        if scheme.archived_at is not None:
            raise ValidationFailed("That grading scheme is archived.", field="grading_scheme_id")
        return scheme

    @staticmethod
    def _require_setup(exam: Examination, what: str) -> None:
        if ExamStatus(exam.status) not in SETUP_EDITABLE:
            raise InvalidState(f"{what} can't change once results have been processed.")

    # ---- reads ----------------------------------------------------------------------------------
    async def search(
        self, uow: UnitOfWork, *, status: str | None, term_id: uuid.UUID | None
    ) -> list[tuple[Examination, Term, AcademicSession, str, int, int]]:
        papers = select(ExamPaper.exam_id, func.count().label("n")).group_by(ExamPaper.exam_id).subquery()
        cohorts = select(ExamCohort.exam_id, func.count().label("n")).group_by(ExamCohort.exam_id).subquery()
        stmt = (
            select(
                Examination,
                Term,
                AcademicSession,
                GradingScheme.name,
                func.coalesce(papers.c.n, 0),
                func.coalesce(cohorts.c.n, 0),
            )
            .join(Term, Term.id == Examination.term_id)
            .join(AcademicSession, AcademicSession.id == Term.session_id)
            .join(GradingScheme, GradingScheme.id == Examination.grading_scheme_id)
            .outerjoin(papers, papers.c.exam_id == Examination.id)
            .outerjoin(cohorts, cohorts.c.exam_id == Examination.id)
            .order_by(AcademicSession.starts_on.desc(), Term.sequence.desc(), Examination.created_at.desc())
        )
        if status:
            stmt = stmt.where(Examination.status == status)
        if term_id:
            stmt = stmt.where(Examination.term_id == term_id)
        return [tuple(r) for r in (await uow.session.execute(stmt)).all()]

    async def detail(self, uow: UnitOfWork, exam_id: uuid.UUID) -> ExamView:
        exam = await self.get(uow, exam_id)
        term, session = await self._term(uow, exam.term_id)
        scheme = (
            await uow.session.scalars(select(GradingScheme).where(GradingScheme.id == exam.grading_scheme_id))
        ).one()
        students = (
            select(CohortMembership.cohort_id, func.count().label("n"))
            .group_by(CohortMembership.cohort_id)
            .subquery()
        )
        cohorts = [
            (c, p, int(n))
            for c, p, n in (
                await uow.session.execute(
                    select(Cohort, Program, func.coalesce(students.c.n, 0))
                    .join(ExamCohort, ExamCohort.cohort_id == Cohort.id)
                    .join(Program, Program.id == Cohort.program_id)
                    .outerjoin(students, students.c.cohort_id == Cohort.id)
                    .where(ExamCohort.exam_id == exam.id)
                    .order_by(Cohort.code)
                )
            ).all()
        ]
        papers = [
            (p, c)
            for p, c in (
                await uow.session.execute(
                    select(ExamPaper, Course)
                    .join(Course, Course.id == ExamPaper.course_id)
                    .where(ExamPaper.exam_id == exam.id)
                    .order_by(ExamPaper.position, Course.code)
                )
            ).all()
        ]
        assignments = list(
            (
                await uow.session.scalars(select(PaperAssignment).where(PaperAssignment.exam_id == exam.id))
            ).all()
        )
        submissions = list(
            (
                await uow.session.scalars(select(PaperSubmission).where(PaperSubmission.exam_id == exam.id))
            ).all()
        )
        faculty: dict[uuid.UUID, str] = {}
        if assignments:
            ids = {a.user_id for a in assignments}
            rows = await uow.session.execute(select(User.id, User.full_name).where(User.id.in_(ids)))
            faculty = {uid: name for uid, name in rows.all()}  # noqa: C416
        view = ExamView(exam, term, session, scheme, cohorts, papers, assignments, submissions, faculty)
        view.checks = self._checks(view)
        return view

    @staticmethod
    def _checks(view: ExamView) -> list[Check]:
        """What must be true before marks entry opens (shown as a checklist in the workspace)."""
        empty = [c.code for c, _p, n in view.cohorts if n == 0]
        return [
            Check("cohorts", bool(view.cohorts), "Add the cohorts sitting this exam."),
            Check(
                "students",
                bool(view.cohorts) and not empty,
                "Every cohort has students." if not empty else f"No students yet in {', '.join(empty)}.",
            ),
            Check("papers", bool(view.papers), "Add at least one paper with its components."),
            Check("grading", view.scheme.archived_at is None, "The grading scheme is active."),
        ]

    # ---- writes ---------------------------------------------------------------------------------
    async def _validate_cohorts(
        self, uow: UnitOfWork, session: AcademicSession, cohort_ids: Sequence[uuid.UUID]
    ) -> list[Cohort]:
        wanted = list(dict.fromkeys(cohort_ids))
        if not wanted:
            return []
        cohorts = list((await uow.session.scalars(select(Cohort).where(Cohort.id.in_(wanted)))).all())
        if len(cohorts) != len(wanted):
            raise ValidationFailed("Some of those cohorts don't exist.", field="cohort_ids")
        for c in cohorts:
            if c.session_id != session.id:
                raise ValidationFailed(
                    f"Cohort {c.code} belongs to another session; choose cohorts from {session.code}.",
                    field="cohort_ids",
                )
            if c.archived_at is not None:
                raise ValidationFailed(f"Cohort {c.code} is archived.", field="cohort_ids")
        return cohorts

    async def create(
        self,
        uow: UnitOfWork,
        principal: Principal,
        *,
        name: str,
        kind: str,
        term_id: uuid.UUID,
        grading_scheme_id: uuid.UUID | None,
        cohort_ids: Sequence[uuid.UUID],
        marks_deadline: datetime | None,
        notes: str | None,
    ) -> Examination:
        clean = " ".join(name.split())
        if not clean:
            raise ValidationFailed("Give the exam a name.", field="name")
        if kind not in EXAM_KINDS:
            raise ValidationFailed("Choose the kind of exam.", field="kind")
        term, session = await self._term(uow, term_id)
        if session.archived_at is not None:
            raise ValidationFailed("That session is archived.", field="term_id")
        scheme = await self._scheme(uow, grading_scheme_id)
        cohorts = await self._validate_cohorts(uow, session, cohort_ids)
        exam = Examination(
            tenant_id=uow.require_tenant(),
            term_id=term.id,
            name=clean,
            kind=kind,
            status=ExamStatus.DRAFT.value,
            grading_scheme_id=scheme.id,
            marks_deadline=marks_deadline,
            notes=(notes or "").strip() or None,
            created_by=principal.user_id,
        )
        uow.session.add(exam)
        await flush_checked(uow, MESSAGES)
        uow.session.add_all(
            ExamCohort(tenant_id=exam.tenant_id, exam_id=exam.id, cohort_id=c.id) for c in cohorts
        )
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "exam.created",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Created exam “{exam.name}” ({term.name}, {session.code})",
            after=_snapshot(exam),
        )
        return exam

    async def update(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID,
        *,
        version: int,
        name: str,
        kind: str,
        grading_scheme_id: uuid.UUID,
        marks_deadline: datetime | None,
        notes: str | None,
    ) -> Examination:
        exam = await self.get(uow, exam_id, lock=True)
        if exam.version != version:
            raise Conflict(
                "Someone else changed this exam while you were editing. Reload to see their changes.",
                current_version=exam.version,
            )
        before = _snapshot(exam)
        clean = " ".join(name.split())
        if not clean:
            raise ValidationFailed("Give the exam a name.", field="name")
        if kind not in EXAM_KINDS:
            raise ValidationFailed("Choose the kind of exam.", field="kind")
        if grading_scheme_id != exam.grading_scheme_id:
            self._require_setup(exam, "The grading scheme")
            exam.grading_scheme_id = (await self._scheme(uow, grading_scheme_id)).id
        exam.name, exam.kind = clean, kind
        exam.marks_deadline = marks_deadline
        exam.notes = (notes or "").strip() or None
        after = _snapshot(exam)
        if after != before:
            exam.version += 1
            await flush_checked(uow, MESSAGES)
            await record(
                uow,
                Actor.from_principal(principal),
                "exam.updated",
                entity_type="exam",
                entity_id=exam.id,
                before={k: v for k, v in before.items() if after[k] != v},
                after={k: v for k, v in after.items() if before[k] != v},
            )
        return exam

    async def delete(self, uow: UnitOfWork, principal: Principal, exam_id: uuid.UUID) -> None:
        exam = await self.get(uow, exam_id, lock=True)
        if exam.status != ExamStatus.DRAFT.value:
            raise InvalidState("Only draft exams can be deleted.")
        await record(
            uow,
            Actor.from_principal(principal),
            "exam.deleted",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Deleted draft exam “{exam.name}”",
        )
        await uow.session.delete(exam)
        await uow.flush()

    async def set_cohorts(
        self, uow: UnitOfWork, principal: Principal, exam_id: uuid.UUID, cohort_ids: Sequence[uuid.UUID]
    ) -> None:
        exam = await self.get(uow, exam_id, lock=True)
        self._require_setup(exam, "Cohorts")
        _term, session = await self._term(uow, exam.term_id)
        wanted = {c.id for c in await self._validate_cohorts(uow, session, cohort_ids)}
        current = set(
            (
                await uow.session.scalars(select(ExamCohort.cohort_id).where(ExamCohort.exam_id == exam.id))
            ).all()
        )
        removed, added = current - wanted, wanted - current
        if removed and exam.status != ExamStatus.DRAFT.value:
            raise InvalidState("Cohorts can only be removed while the exam is a draft.")
        if removed:
            await uow.session.execute(
                delete(ExamCohort).where(ExamCohort.exam_id == exam.id, ExamCohort.cohort_id.in_(removed))
            )
        uow.session.add_all(ExamCohort(tenant_id=exam.tenant_id, exam_id=exam.id, cohort_id=c) for c in added)
        await uow.flush()
        if exam.status != ExamStatus.DRAFT.value and added:
            await self._ensure_submissions(uow, exam)
        if added or removed:
            await record(
                uow,
                Actor.from_principal(principal),
                "exam.cohorts_changed",
                entity_type="exam",
                entity_id=exam.id,
                after={"added": len(added), "removed": len(removed)},
            )

    async def add_paper(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID,
        *,
        course_id: uuid.UUID,
        components: list[dict[str, Any]],
        pass_total: Decimal | None,
        credits: Decimal | None,
        use_course_credits: bool,
    ) -> ExamPaper:
        exam = await self.get(uow, exam_id, lock=True)
        self._require_setup(exam, "Papers")
        course = (await uow.session.scalars(select(Course).where(Course.id == course_id))).one_or_none()
        if course is None:
            raise ValidationFailed("That course doesn't exist.", field="course_id")
        if course.archived_at is not None:
            raise ValidationFailed("That course is archived.", field="course_id")
        comps = parse_components(components)
        total = max_total(comps)
        if pass_total is not None and pass_total > total:
            raise ValidationFailed(
                f"The pass mark can't be more than the total ({total}).", field="pass_total"
            )
        position = (
            await uow.session.execute(
                select(func.coalesce(func.max(ExamPaper.position), 0)).where(ExamPaper.exam_id == exam.id)
            )
        ).scalar_one()
        paper = ExamPaper(
            tenant_id=exam.tenant_id,
            exam_id=exam.id,
            course_id=course.id,
            position=int(position) + 1,
            components=to_json(comps),
            max_total=total,
            pass_total=pass_total,
            credits=course.credits if use_course_credits else credits,
        )
        uow.session.add(paper)
        await flush_checked(uow, MESSAGES)
        if exam.status != ExamStatus.DRAFT.value:
            await self._ensure_submissions(uow, exam)
        await record(
            uow,
            Actor.from_principal(principal),
            "exam.paper_added",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Added paper {course.code} ({total} marks)",
            after={"course": course.code, "components": paper.components},
        )
        return paper

    async def update_paper(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID,
        paper_id: uuid.UUID,
        *,
        components: list[dict[str, Any]],
        pass_total: Decimal | None,
        credits: Decimal | None,
    ) -> ExamPaper:
        exam = await self.get(uow, exam_id, lock=True)
        self._require_setup(exam, "Papers")
        paper = await self.paper(uow, exam, paper_id)
        comps = parse_components(components)
        total = max_total(comps)
        if pass_total is not None and pass_total > total:
            raise ValidationFailed(
                f"The pass mark can't be more than the total ({total}).", field="pass_total"
            )
        before = {"components": paper.components, "pass_total": paper.pass_total, "credits": paper.credits}
        paper.components, paper.max_total, paper.pass_total, paper.credits = (
            to_json(comps),
            total,
            pass_total,
            credits,
        )
        await uow.flush()
        after = {"components": paper.components, "pass_total": paper.pass_total, "credits": paper.credits}
        if before != after:
            await record(
                uow,
                Actor.from_principal(principal),
                "exam.paper_updated",
                entity_type="exam",
                entity_id=exam.id,
                before={k: (str(v) if isinstance(v, Decimal) else v) for k, v in before.items()},
                after={k: (str(v) if isinstance(v, Decimal) else v) for k, v in after.items()},
            )
        return paper

    async def remove_paper(
        self, uow: UnitOfWork, principal: Principal, exam_id: uuid.UUID, paper_id: uuid.UUID
    ) -> None:
        exam = await self.get(uow, exam_id, lock=True)
        if exam.status != ExamStatus.DRAFT.value:
            raise InvalidState("Papers can only be removed while the exam is a draft.")
        paper = await self.paper(uow, exam, paper_id)
        await uow.session.delete(paper)
        await uow.flush()
        await record(
            uow, Actor.from_principal(principal), "exam.paper_removed", entity_type="exam", entity_id=exam.id
        )

    async def set_assignments(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID,
        paper_id: uuid.UUID,
        *,
        cohort_id: uuid.UUID,
        user_ids: Sequence[uuid.UUID],
    ) -> None:
        exam = await self.get(uow, exam_id, lock=True)
        paper = await self.paper(uow, exam, paper_id)
        sits = (
            await uow.session.scalars(
                select(ExamCohort.cohort_id).where(
                    ExamCohort.exam_id == exam.id, ExamCohort.cohort_id == cohort_id
                )
            )
        ).one_or_none()
        if sits is None:
            raise ValidationFailed("That cohort doesn't sit this exam.", field="cohort_id")
        wanted = set(user_ids)
        if wanted:
            faculty = set(
                (
                    await uow.session.scalars(
                        select(User.id)
                        .join(UserRole, UserRole.user_id == User.id)
                        .where(User.id.in_(wanted), UserRole.role == "faculty", User.status != "disabled")
                    )
                ).all()
            )
            if faculty != wanted:
                raise ValidationFailed(
                    "Assign faculty members with an active or invited account.", field="user_ids"
                )
        current = set(
            (
                await uow.session.scalars(
                    select(PaperAssignment.user_id).where(
                        PaperAssignment.exam_paper_id == paper.id, PaperAssignment.cohort_id == cohort_id
                    )
                )
            ).all()
        )
        if current - wanted:
            await uow.session.execute(
                delete(PaperAssignment).where(
                    PaperAssignment.exam_paper_id == paper.id,
                    PaperAssignment.cohort_id == cohort_id,
                    PaperAssignment.user_id.in_(current - wanted),
                )
            )
        uow.session.add_all(
            PaperAssignment(
                tenant_id=exam.tenant_id,
                exam_id=exam.id,
                exam_paper_id=paper.id,
                cohort_id=cohort_id,
                user_id=u,
            )
            for u in wanted - current
        )
        await uow.flush()
        if current != wanted:
            await record(
                uow,
                Actor.from_principal(principal),
                "exam.faculty_assigned",
                entity_type="exam",
                entity_id=exam.id,
                after={
                    "paper": str(paper.id),
                    "cohort": str(cohort_id),
                    "faculty": sorted(str(u) for u in wanted),
                },
            )

    async def _ensure_submissions(self, uow: UnitOfWork, exam: Examination) -> int:
        papers = (await uow.session.scalars(select(ExamPaper.id).where(ExamPaper.exam_id == exam.id))).all()
        cohorts = (
            await uow.session.scalars(select(ExamCohort.cohort_id).where(ExamCohort.exam_id == exam.id))
        ).all()
        existing = {
            (s.exam_paper_id, s.cohort_id)
            for s in (
                await uow.session.scalars(select(PaperSubmission).where(PaperSubmission.exam_id == exam.id))
            ).all()
        }
        new = [
            PaperSubmission(
                tenant_id=exam.tenant_id, exam_id=exam.id, exam_paper_id=p, cohort_id=c, status="open"
            )
            for p in papers
            for c in cohorts
            if (p, c) not in existing
        ]
        uow.session.add_all(new)
        await uow.flush()
        return len(new)

    async def transition(
        self,
        uow: UnitOfWork,
        principal: Principal | None,
        exam_id: uuid.UUID,
        action: str,
        *,
        reason: str | None,
    ) -> Examination:
        exam = await self.get(uow, exam_id, lock=True)
        t = transition_for(exam.status, action, reason)
        if t.target is ExamStatus.MARKS_ENTRY_OPEN and t.source is ExamStatus.DRAFT:
            view = await self.detail(uow, exam.id)
            missing = [c.message for c in view.checks if not c.ok]
            if missing:
                raise InvalidState("Not ready to open marks entry: " + " ".join(missing))
            await self._ensure_submissions(uow, exam)
        exam.status = t.target.value
        exam.version += 1
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal) if principal else Actor.system("exam-lifecycle"),
            f"exam.{t.action.value}",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"{t.label}: {exam.name}",
            before={"status": t.source.value},
            after={"status": t.target.value},
            reason=(reason or "").strip() or None,
        )
        return exam
