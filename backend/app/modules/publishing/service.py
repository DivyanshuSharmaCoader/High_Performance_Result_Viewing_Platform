"""Publishing approved results, and the student read path (docs/03 W10, W12; sequence diagram §5).

* ``publish`` checks the exam is approved, the plan allows it and (for a scheduled release) that scheduling
  is in the plan; then, in **one transaction**, writes the publication, a snapshot per student and the
  statistics snapshot. "Now" goes live in the same transaction; a scheduled one goes live from a job.
* ``go_live`` makes a publication visible: the previous live version (if any) becomes superseded.
* ``withdraw`` hides a live publication (with a reason); ``cancel`` drops a scheduled one.
* Students read only snapshots of *published* publications, located by the student linked to their own
  session — there is no student id anywhere in the student API.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import Table, func, insert, select, update

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import InvalidState, LimitExceeded, NotFound, ValidationFailed
from app.core.http import Principal
from app.core.jobs import enqueue
from app.modules.academics.models import AcademicSession, Cohort, Course, Program, Term
from app.modules.audit.service import Actor, record
from app.modules.branding.models import TenantBranding
from app.modules.directory.models import Student
from app.modules.documents.service import MarksheetService
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EntitlementService
from app.modules.examinations.models import Examination, ExamPaper
from app.modules.examinations.states import ExamAction, ExamStatus, transition_for
from app.modules.grading.models import GradingScheme, GradingSchemeVersion
from app.modules.identity.service import AuthService
from app.modules.notifications.service import Notifier
from app.modules.publishing.models import ExamStatistics, Publication, PublishedResult
from app.modules.publishing.read_cache import LivePublication, StudentReads
from app.modules.publishing.snapshot import (
    ExamInfo,
    Institution,
    PaperInfo,
    SchemeInfo,
    StudentInfo,
    build_payload,
    payload_hash,
)
from app.modules.results.models import ResultRun, StudentExamResult, StudentPaperResult
from app.modules.tenancy.models import TenantSettings

CHUNK = 1000
SNAPSHOTS = cast(Table, PublishedResult.__table__)
COUNTED = ("scheduled", "published", "superseded", "withdrawn")  # a publication that used a plan slot
MIN_LEAD = timedelta(minutes=2)  # a scheduled time must be at least this far ahead


@dataclass
class MyResult:
    publication: LivePublication
    payload: dict[str, Any]
    revised: bool  # an earlier version of this exam was published before


def _row(obj: Any, *cols: str) -> dict[str, Any]:
    return {c: getattr(obj, c) for c in cols}


class PublishingService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    # ---- admin ----------------------------------------------------------------------------------
    @staticmethod
    async def exam(uow: UnitOfWork, exam_id: uuid.UUID) -> Examination:
        exam = (
            await uow.session.scalars(select(Examination).where(Examination.id == exam_id).with_for_update())
        ).one_or_none()
        if exam is None:
            raise NotFound("Exam not found")
        return exam

    @staticmethod
    async def publications(uow: UnitOfWork, exam_id: uuid.UUID) -> list[Publication]:
        return list(
            (
                await uow.session.scalars(
                    select(Publication)
                    .where(Publication.exam_id == exam_id)
                    .order_by(Publication.version.desc())
                )
            ).all()
        )

    @staticmethod
    async def _publication(uow: UnitOfWork, exam_id: uuid.UUID, publication_id: uuid.UUID) -> Publication:
        pub = (
            await uow.session.scalars(
                select(Publication)
                .where(Publication.id == publication_id, Publication.exam_id == exam_id)
                .with_for_update()
            )
        ).one_or_none()
        if pub is None:
            raise NotFound("Publication not found")
        return pub

    async def _check_plan(self, uow: UnitOfWork, exam: Examination, scheduled: bool) -> None:
        ent = await EntitlementService(self.infra).effective(uow, fresh=True)
        if scheduled:
            ent.require(F.SCHEDULED_PUBLICATION)
        limit = ent.limit(F.MAX_PUBLISHED_EXAMS_PER_YEAR)
        if limit is None:
            return
        # Serialise publications per tenant while counting (the settings row is the tenant's mutex).
        await uow.session.execute(select(TenantSettings.tenant_id).with_for_update())
        already = (
            await uow.session.scalar(
                select(func.count())
                .select_from(Publication)
                .where(Publication.exam_id == exam.id, Publication.status.in_(COUNTED))
            )
            or 0
        )
        if already:
            return  # re-publishing an exam (after a withdrawal, a correction) uses no new slot
        session_id = (await uow.session.scalars(select(Term.session_id).where(Term.id == exam.term_id))).one()
        used = (
            await uow.session.scalar(
                select(func.count(func.distinct(Publication.exam_id)))
                .join(Examination, Examination.id == Publication.exam_id)
                .join(Term, Term.id == Examination.term_id)
                .where(Term.session_id == session_id, Publication.status.in_(COUNTED))
            )
            or 0
        )
        if used >= limit:
            raise LimitExceeded(
                f"Your plan includes {limit:,} exam publications per academic year and {used:,} exams of this "
                "year are already published. Upgrade your plan to publish more.",
                limit=F.MAX_PUBLISHED_EXAMS_PER_YEAR,
                current=used,
                requested=1,
                max=limit,
            )

    async def publish(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID,
        *,
        at: datetime | None,
    ) -> Publication:
        exam = await self.exam(uow, exam_id)
        AuthService(self.infra).require_recent_auth(principal)
        actor = Actor.from_principal(principal)
        if exam.status == ExamStatus.WITHDRAWN:
            t = transition_for(exam.status, ExamAction.REAPPROVE, None)
            exam.status = t.target.value
        if exam.status != ExamStatus.APPROVED:
            raise InvalidState(
                "Results must be approved before they can be published."
                if exam.status in (ExamStatus.PROCESSED, ExamStatus.MARKS_ENTRY_CLOSED)
                else "This exam can't be published at this stage."
            )
        run = (
            await uow.session.scalars(
                select(ResultRun)
                .where(ResultRun.exam_id == exam.id, ResultRun.status == "approved")
                .order_by(ResultRun.revision.desc())
                .limit(1)
            )
        ).one_or_none()
        if run is None or run.content_hash is None:
            raise InvalidState("There are no approved results to publish.")
        now = utcnow()
        if at is not None and at < now + MIN_LEAD:
            raise ValidationFailed("Choose a time at least a few minutes from now.", field="at")
        await self._check_plan(uow, exam, scheduled=at is not None)

        version = (
            await uow.session.scalar(
                select(func.max(Publication.version)).where(Publication.exam_id == exam.id)
            )
            or 0
        ) + 1
        pub = Publication(
            tenant_id=uow.require_tenant(),
            exam_id=exam.id,
            result_run_id=run.id,
            version=version,
            status="scheduled" if at is not None else "published",
            scheduled_at=at,
            published_at=None if at is not None else now,
            created_by=principal.user_id,
            content_hash=run.content_hash,
        )
        if at is None:
            # The live version this one replaces must step aside before the one-live-per-exam index sees it.
            pub.supersedes_id = await self._supersede(uow, exam.id)
        uow.session.add(pub)
        await uow.flush()
        students = await self._snapshots(uow, exam, run, pub)
        pub.students = len(students)
        # A marksheet and a verification code per student, rendered by the pdf worker from now on (ahead
        # of go-live for a scheduled release), so result day itself does no PDF work.
        await MarksheetService(self.infra).prepare(uow, pub.id, students, principal.user_id)
        uow.session.add(
            ExamStatistics(tenant_id=pub.tenant_id, publication_id=pub.id, stats=dict(run.stats or {}))
        )
        if at is None:
            self._move(exam, ExamAction.PUBLISH)
            run.status = "published"
            await Notifier.schedule_publication(uow, pub.id)
            StudentReads(self.infra).forget_live(uow)
        else:
            self._move(exam, ExamAction.SCHEDULE)
            await enqueue(
                uow,
                "publishing.go_live",
                {"publication_id": str(pub.id)},
                run_at=at,
                dedupe_key=f"publication:{pub.id}",
                created_by=principal.user_id,
            )
        await uow.flush()
        await record(
            uow,
            actor,
            "publication.scheduled" if at else "publication.published",
            entity_type="exam",
            entity_id=exam.id,
            summary=(
                f"Results of {exam.name} scheduled for {at.isoformat()}"
                if at
                else f"Results of {exam.name} published (version {version}, {pub.students} students)"
            ),
            after={
                "publication_id": str(pub.id),
                "version": version,
                "students": pub.students,
                "content_hash": pub.content_hash,
                "scheduled_at": at.isoformat() if at else None,
            },
        )
        return pub

    @staticmethod
    def _move(exam: Examination, action: ExamAction) -> None:
        t = transition_for(exam.status, action, None)
        exam.status, exam.version = t.target.value, exam.version + 1

    @staticmethod
    async def _supersede(uow: UnitOfWork, exam_id: uuid.UUID) -> uuid.UUID | None:
        live = (
            await uow.session.scalars(
                select(Publication)
                .where(Publication.exam_id == exam_id, Publication.status == "published")
                .with_for_update()
            )
        ).one_or_none()
        if live is None:
            return None
        live.status = "superseded"
        await uow.flush()
        return live.id

    async def _snapshots(
        self, uow: UnitOfWork, exam: Examination, run: ResultRun, pub: Publication
    ) -> list[uuid.UUID]:
        """One payload per student, written in chunks; returns the students."""
        settings = (await uow.session.scalars(select(TenantSettings))).one()
        branding = (await uow.session.scalars(select(TenantBranding))).one_or_none()
        institution = Institution(
            name=settings.official_name,
            display_name=branding.display_name if branding else settings.official_name,
        )
        term, session = (
            await uow.session.execute(
                select(Term.name, AcademicSession.name)
                .join(AcademicSession, AcademicSession.id == Term.session_id)
                .where(Term.id == exam.term_id)
            )
        ).one()
        exam_info = ExamInfo(name=exam.name, kind=exam.kind, term=term, session=session)
        scheme_name, version_config = (
            await uow.session.execute(
                select(GradingScheme.name, GradingSchemeVersion.config)
                .join(GradingScheme, GradingScheme.id == GradingSchemeVersion.scheme_id)
                .where(GradingSchemeVersion.id == run.grading_scheme_version_id)
            )
        ).one()
        scheme = SchemeInfo(name=scheme_name, strategy=str(version_config.get("strategy")))
        paper_info = {
            str(p.id): PaperInfo(str(p.id), code, name, p.credits, list(p.components))
            for p, code, name in (
                await uow.session.execute(
                    select(ExamPaper, Course.code, Course.name)
                    .join(Course, Course.id == ExamPaper.course_id)
                    .where(ExamPaper.exam_id == exam.id)
                    .order_by(ExamPaper.position, ExamPaper.id)
                )
            ).all()
        }
        papers: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for p in (
            await uow.session.scalars(
                select(StudentPaperResult).where(StudentPaperResult.result_run_id == run.id)
            )
        ).all():
            papers.setdefault(p.student_id, []).append(
                _row(
                    p,
                    "exam_paper_id",
                    "outcome",
                    "attendance",
                    "components",
                    "total",
                    "max_total",
                    "percentage",
                    "grade",
                    "grade_point",
                    "failed_components",
                    "missing_components",
                )
            )
        rows: list[dict[str, Any]] = []
        for r, enrollment, full_name, cohort_code, cohort_name, program in (
            await uow.session.execute(
                select(
                    StudentExamResult,
                    Student.enrollment_no,
                    Student.full_name,
                    Cohort.code,
                    Cohort.name,
                    Program.name,
                )
                .join(Student, Student.id == StudentExamResult.student_id)
                .join(Cohort, Cohort.id == StudentExamResult.cohort_id)
                .join(Program, Program.id == Cohort.program_id)
                .where(StudentExamResult.result_run_id == run.id)
                .order_by(Student.enrollment_no)
            )
        ).all():
            payload = build_payload(
                institution=institution,
                exam=exam_info,
                scheme=scheme,
                student=StudentInfo(enrollment, full_name, cohort_code, cohort_name, program),
                result=_row(
                    r,
                    "outcome",
                    "total",
                    "max_total",
                    "percentage",
                    "grade",
                    "grade_point",
                    "sgpa",
                    "credits_attempted",
                    "credits_earned",
                    "rank",
                    "notes",
                ),
                papers=papers.get(r.student_id, []),
                paper_info=paper_info,
            )
            rows.append(
                {
                    "tenant_id": pub.tenant_id,
                    "publication_id": pub.id,
                    "student_id": r.student_id,
                    "exam_id": exam.id,
                    "payload": payload,
                    "payload_hash": payload_hash(payload),
                }
            )
        await self._insert(uow, rows)
        return [r["student_id"] for r in rows]

    @staticmethod
    async def _insert(uow: UnitOfWork, rows: list[dict[str, Any]]) -> None:
        for i in range(0, len(rows), CHUNK):
            await uow.session.execute(insert(SNAPSHOTS), rows[i : i + CHUNK])

    async def go_live(self, tenant_id: uuid.UUID, publication_id: uuid.UUID) -> dict[str, Any]:
        """The scheduled-publication job. A cancelled (or already live) publication is left alone."""
        async with self.infra.db.uow(tenant_id) as uow:
            pub = (
                await uow.session.scalars(
                    select(Publication).where(Publication.id == publication_id).with_for_update()
                )
            ).one()
            if pub.status != "scheduled":
                return {"skipped": pub.status}
            exam = await self.exam(uow, pub.exam_id)
            pub.supersedes_id = await self._supersede(uow, exam.id)
            pub.status, pub.published_at = "published", utcnow()
            self._move(exam, ExamAction.PUBLISH)
            await uow.session.execute(
                update(ResultRun).where(ResultRun.id == pub.result_run_id).values(status="published")
            )
            await Notifier.schedule_publication(uow, pub.id)
            StudentReads(self.infra).forget_live(uow)
            await uow.flush()
            await record(
                uow,
                Actor.system("publishing"),
                "publication.published",
                entity_type="exam",
                entity_id=exam.id,
                summary=f"Scheduled results of {exam.name} went live (version {pub.version})",
                after={"publication_id": str(pub.id), "version": pub.version, "students": pub.students},
            )
            return {"published": str(pub.id)}

    async def cancel(
        self, uow: UnitOfWork, principal: Principal, exam_id: uuid.UUID, publication_id: uuid.UUID
    ) -> Publication:
        pub = await self._publication(uow, exam_id, publication_id)
        exam = await self.exam(uow, exam_id)
        if pub.status != "scheduled":
            raise InvalidState("Only a scheduled publication can be cancelled.")
        pub.status = "cancelled"
        self._move(exam, ExamAction.CANCEL_SCHEDULE)
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "publication.cancelled",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Scheduled publication of {exam.name} cancelled",
            after={"publication_id": str(pub.id)},
        )
        return pub

    async def withdraw(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID,
        publication_id: uuid.UUID,
        reason: str,
    ) -> Publication:
        pub = await self._publication(uow, exam_id, publication_id)
        exam = await self.exam(uow, exam_id)
        AuthService(self.infra).require_recent_auth(principal)
        if pub.status != "published":
            raise InvalidState("Only live results can be withdrawn.")
        t = transition_for(exam.status, ExamAction.WITHDRAW, reason)
        pub.status, pub.withdrawn_at, pub.withdraw_reason = "withdrawn", utcnow(), reason.strip()
        StudentReads(self.infra).forget_live(uow)
        exam.status, exam.version = t.target.value, exam.version + 1
        # The approval still stands: the same results can be published again as a new version.
        await uow.session.execute(
            update(ResultRun).where(ResultRun.id == pub.result_run_id).values(status="approved")
        )
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "publication.withdrawn",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Results of {exam.name} withdrawn (version {pub.version})",
            before={"status": t.source.value},
            after={"status": t.target.value, "publication_id": str(pub.id)},
            reason=reason.strip(),
        )
        return pub

    # ---- students -------------------------------------------------------------------------------
    # Every read goes through StudentReads: immutable rows are cached per tenant and student, the list of
    # live publications for 5 s at most (read_cache.py). Identity comes only from the session.
    async def student_id(self, uow: UnitOfWork, principal: Principal) -> uuid.UUID:
        sid = await StudentReads(self.infra).student_id(uow, principal.user_id)
        if sid is None:
            raise NotFound("No student record is linked to this account.")
        return sid

    async def my_results(self, uow: UnitOfWork, principal: Principal) -> list[MyResult]:
        """The live version of every published exam of this student, newest first."""
        reads = StudentReads(self.infra)
        sid = await self.student_id(uow, principal)
        out = []
        for pub in await reads.live(uow):
            payload = await reads.payload(uow, pub.id, sid)
            if payload is not None:
                out.append(MyResult(pub, payload, pub.version > 1))
        return out

    async def my_result(self, uow: UnitOfWork, principal: Principal, publication_id: uuid.UUID) -> MyResult:
        reads = StudentReads(self.infra)
        sid = await self.student_id(uow, principal)
        pub = next((p for p in await reads.live(uow) if p.id == publication_id), None)
        payload = await reads.payload(uow, publication_id, sid) if pub is not None else None
        if pub is None or payload is None:
            raise NotFound("Result not found")
        return MyResult(pub, payload, pub.version > 1)

    async def my_stats(
        self, uow: UnitOfWork, principal: Principal, publication_id: uuid.UUID
    ) -> dict[str, Any] | None:
        from app.modules.publishing.snapshot import student_stats

        mine = await self.my_result(uow, principal, publication_id)  # 404 unless it's this student's
        reads = StudentReads(self.infra)
        level = await reads.stats_level(uow)
        stats = await reads.stats(uow, mine.publication.id)
        return student_stats(stats or {}, level)
