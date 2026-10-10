"""Publishing approved results, and the student read path (docs/03 W10, W12; sequence diagram §5).

* ``publish`` checks the exam is approved, the plan allows it and (for a scheduled release) that scheduling
  is in the plan; then, in **one transaction**, writes the publication, a snapshot per student and the
  statistics snapshot. "Now" goes live in the same transaction; a scheduled one goes live from a job.
* ``go_live`` makes a publication visible: the previous live version (if any) becomes superseded.
* ``withdraw`` hides a live publication (with a reason); ``cancel`` drops a scheduled one.
* Corrections (P18.3): ``start_correction`` opens published results for changes while the live version
  stays visible; the corrected results are processed, approved and published as a new version that
  supersedes it. Only students whose result or marks changed are told. ``cancel_correction`` returns to
  the live version if no mark changed; ``correction_preview`` shows who changes before publishing.
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
from app.modules.examinations.models import Examination, ExamPaper, PaperSubmission
from app.modules.examinations.states import ExamAction, ExamStatus, transition_for
from app.modules.grading.models import GradingScheme, GradingSchemeVersion
from app.modules.identity.service import AuthService
from app.modules.notifications.service import Notifier
from app.modules.publishing.changes import changed_students
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
from app.modules.results.compute import input_hash
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


SUMMARY_FIELDS = ("outcome", "total", "max_total", "percentage", "grade", "sgpa")


def result_fingerprint(payload: dict[str, Any]) -> str:
    """What a student sees of their own result: the result and the papers' marks. Not the institution's
    name or the student's details, so a renamed school doesn't count as a changed result."""
    return payload_hash({"result": payload.get("result"), "papers": payload.get("papers")})


def _summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    r = payload.get("result") or {}
    return {k: r.get(k) for k in SUMMARY_FIELDS}


@dataclass
class CorrectionChange:
    enrollment_no: str
    full_name: str
    before: dict[str, Any] | None  # None: not in the live version
    after: dict[str, Any] | None  # None: not in the corrected results


@dataclass
class CorrectionPreview:
    live_version: int
    revision: int | None  # the corrected results compared (None: none processed yet)
    students: int
    changed: int
    changes: list[CorrectionChange]  # the first PREVIEW_LIMIT, by enrollment number


PREVIEW_LIMIT = 200


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
        live = await self._live(uow, exam.id)
        if live is not None and live.content_hash == run.content_hash:
            raise InvalidState(
                f"These are the results already live (version {live.version}): no mark changed. "
                "Cancel the correction instead."
            )
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
        changed = await changed_students(uow, pub.id, live.id) if live is not None else None
        # A marksheet and a verification code per student, rendered by the pdf worker from now on (ahead
        # of go-live for a scheduled release), so result day itself does no PDF work.
        await MarksheetService(self.infra).prepare(uow, pub.id, students, principal.user_id)
        uow.session.add(
            ExamStatistics(tenant_id=pub.tenant_id, publication_id=pub.id, stats=dict(run.stats or {}))
        )
        correction = exam.correction_reason
        if at is None:
            self._move(exam, ExamAction.PUBLISH)
            run.status = "published"
            self._end_correction(exam)
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
                else f"Results of {exam.name} published (version {version}, {pub.students} students"
                + (f", {len(changed)} changed by the correction" if changed is not None else "")
                + ")"
            ),
            after={
                "publication_id": str(pub.id),
                "version": version,
                "students": pub.students,
                "content_hash": pub.content_hash,
                "scheduled_at": at.isoformat() if at else None,
                "supersedes_version": live.version if live is not None else None,
                "students_changed": len(changed) if changed is not None else None,
            },
            reason=correction,
        )
        return pub

    @staticmethod
    def _end_correction(exam: Examination) -> None:
        exam.correction_started_at = exam.correction_started_by = exam.correction_reason = None

    @staticmethod
    async def _live(uow: UnitOfWork, exam_id: uuid.UUID) -> Publication | None:
        return (
            await uow.session.scalars(
                select(Publication).where(Publication.exam_id == exam_id, Publication.status == "published")
            )
        ).one_or_none()

    # ---- corrections after publication (P18.3) --------------------------------------------------
    async def start_correction(
        self, uow: UnitOfWork, principal: Principal, exam_id: uuid.UUID, reason: str
    ) -> Examination:
        exam = await self.exam(uow, exam_id)
        AuthService(self.infra).require_recent_auth(principal)
        t = transition_for(exam.status, ExamAction.START_CORRECTION, reason)
        live = await self._live(uow, exam.id)
        if live is None:
            raise InvalidState("There are no live results to correct.")
        exam.status, exam.version = t.target.value, exam.version + 1
        exam.correction_started_at, exam.correction_started_by = utcnow(), principal.user_id
        exam.correction_reason = reason.strip()
        # Administrators change marks now; papers stay submitted (faculty can't edit unless reopened).
        await uow.session.execute(
            update(PaperSubmission)
            .where(PaperSubmission.exam_id == exam.id, PaperSubmission.status == "locked")
            .values(status="submitted")
        )
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "exam.correction_started",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Correction of {exam.name} started; version {live.version} stays live until it is replaced",
            before={"status": t.source.value},
            after={"status": t.target.value, "live_version": live.version},
            reason=reason.strip(),
        )
        return exam

    async def cancel_correction(
        self, uow: UnitOfWork, principal: Principal, exam_id: uuid.UUID
    ) -> Examination:
        exam = await self.exam(uow, exam_id)
        if exam.correction_started_at is None:
            raise InvalidState("No correction is in progress.")
        live = await self._live(uow, exam.id)
        if live is None:
            raise InvalidState("The live results were withdrawn. Publish the corrected results instead.")
        t = transition_for(exam.status, ExamAction.CANCEL_CORRECTION, None)
        live_run = (
            await uow.session.scalars(select(ResultRun).where(ResultRun.id == live.result_run_id))
        ).one()
        from app.modules.results.service import ResultsService

        assert live_run.grading_scheme_version_id is not None
        inputs = await ResultsService.load_inputs(uow, exam, live_run.grading_scheme_version_id)
        if input_hash(inputs) != live_run.input_hash:
            raise InvalidState(
                "Marks (or the students or papers) changed during this correction. Publish the corrected "
                "results, or change them back first."
            )
        reason = exam.correction_reason
        exam.status, exam.version = t.target.value, exam.version + 1
        self._end_correction(exam)
        # Results processed during the correction no longer count, and papers lock again.
        await uow.session.execute(
            update(ResultRun)
            .where(
                ResultRun.exam_id == exam.id,
                ResultRun.revision > live_run.revision,
                ResultRun.status.in_(("completed", "approved")),
            )
            .values(status="stale")
        )
        await uow.session.execute(
            update(PaperSubmission).where(PaperSubmission.exam_id == exam.id).values(status="locked")
        )
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "exam.correction_cancelled",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Correction of {exam.name} cancelled; version {live.version} stays live",
            before={"status": t.source.value},
            after={"status": t.target.value},
            reason=reason,
        )
        return exam

    async def correction_preview(self, uow: UnitOfWork, exam_id: uuid.UUID) -> CorrectionPreview:
        exam = await self.exam(uow, exam_id)
        live = await self._live(uow, exam.id)
        if exam.correction_started_at is None or live is None:
            raise InvalidState("No correction of live results is in progress.")
        live_run = (
            await uow.session.scalars(select(ResultRun).where(ResultRun.id == live.result_run_id))
        ).one()
        run = (
            await uow.session.scalars(
                select(ResultRun)
                .where(
                    ResultRun.exam_id == exam.id,
                    ResultRun.revision > live_run.revision,
                    ResultRun.status.in_(("completed", "approved")),
                )
                .order_by(ResultRun.revision.desc())
                .limit(1)
            )
        ).one_or_none()
        if run is None:
            return CorrectionPreview(live.version, None, live.students, 0, [])
        rows = await self._payload_rows(uow, exam, run, live.tenant_id, live.id)
        live_rows = await uow.session.execute(
            select(PublishedResult.student_id, PublishedResult.payload).where(
                PublishedResult.publication_id == live.id
            )
        )
        before: dict[uuid.UUID, dict[str, Any]] = dict(live_rows.tuples().all())
        after = {r["student_id"]: r["payload"] for r in rows}
        changes = []
        for sid in sorted(
            set(before) | set(after),
            key=lambda i: str((after.get(i) or before[i])["student"]["enrollment_no"]),
        ):
            b, a = before.get(sid), after.get(sid)
            if b is not None and a is not None and result_fingerprint(b) == result_fingerprint(a):
                continue
            who = (a or b or {})["student"]
            changes.append(CorrectionChange(who["enrollment_no"], who["full_name"], _summary(b), _summary(a)))
        return CorrectionPreview(
            live.version, run.revision, len(after), len(changes), changes[:PREVIEW_LIMIT]
        )

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
        rows = await self._payload_rows(uow, exam, run, pub.tenant_id, pub.id)
        await self._insert(uow, rows)
        return [r["student_id"] for r in rows]

    async def _payload_rows(
        self,
        uow: UnitOfWork,
        exam: Examination,
        run: ResultRun,
        tenant_id: uuid.UUID,
        publication_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """The snapshot rows a publication of ``run`` would have (not written)."""
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
                    "tenant_id": tenant_id,
                    "publication_id": publication_id,
                    "student_id": r.student_id,
                    "exam_id": exam.id,
                    "payload": payload,
                    "payload_hash": payload_hash(payload),
                }
            )
        return rows

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
            self._end_correction(exam)
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
        correcting = exam.correction_started_at is not None and exam.status != ExamStatus.PUBLISHED
        # During a correction the exam stays where the correction is; only the live version goes.
        t = transition_for(
            ExamStatus.PUBLISHED.value if correcting else exam.status, ExamAction.WITHDRAW, reason
        )
        pub.status, pub.withdrawn_at, pub.withdraw_reason = "withdrawn", utcnow(), reason.strip()
        StudentReads(self.infra).forget_live(uow)
        if not correcting:
            exam.status = t.target.value
            # The approval still stands: the same results can be published again as a new version.
            await uow.session.execute(
                update(ResultRun).where(ResultRun.id == pub.result_run_id).values(status="approved")
            )
        exam.version += 1
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "publication.withdrawn",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Results of {exam.name} withdrawn (version {pub.version})"
            + (" during a correction" if correcting else ""),
            before={"status": t.source.value},
            after={"status": exam.status, "publication_id": str(pub.id)},
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
