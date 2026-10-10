"""Result processing, preview and approval (docs/03 W8–W9, sequence diagram §4).

* ``request`` checks the exam can be processed, pins the grading scheme's latest version and queues a run.
* ``execute`` (the ``results.process`` job) loads every input set-based, computes in a thread, writes the
  rows in bulk and moves the exam to *processed*. It holds the exam row ``FOR UPDATE`` throughout and mark
  writers take ``FOR SHARE`` on it, so no mark can change half-way through a computation.
* ``approve`` re-computes the input hash: if anything that feeds the results changed since processing,
  approval is refused. On approval the content hash is recorded and every paper locked.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

import anyio
from sqlalchemy import Table, func, insert, or_, select, update

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import Conflict, InvalidState, NotFound, PermissionDenied
from app.core.http import Principal
from app.core.jobs import enqueue
from app.core.sql import in_values
from app.modules.academics.models import Cohort, Course
from app.modules.audit.service import Actor, record
from app.modules.directory.models import CohortMembership, Student
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EntitlementService
from app.modules.examinations.models import ExamCohort, Examination, ExamPaper, PaperSubmission
from app.modules.examinations.states import ExamAction, ExamStatus, transition_for
from app.modules.grading.engine import Component, PaperSpec
from app.modules.grading.models import GradingSchemeVersion
from app.modules.identity.models import User
from app.modules.identity.service import AuthService
from app.modules.marks.models import MarkEntry
from app.modules.results.compute import (
    Computed,
    Inputs,
    Mark,
    Paper,
    ProcessingError,
    anomalies,
    compute,
    input_hash,
    num,
    result_doc,
    statistics,
)
from app.modules.results.compute import (
    Student as StudentIn,
)
from app.modules.results.models import Approval, ResultRun, StudentExamResult, StudentPaperResult
from app.modules.tenancy.models import TenantSettings

ROSTER_STATUSES = ("active", "graduated")
# A correction draft (published results being corrected, P18.3) is processed like closed marks entry.
PROCESSABLE = (ExamStatus.MARKS_ENTRY_CLOSED, ExamStatus.PROCESSED, ExamStatus.CORRECTION_DRAFT)
PREVIOUS = ("completed", "stale", "approved", "published")
CHUNK = 1000  # rows per INSERT: ~17 columns each stays well under the 32,767-parameter limit
EXAM_RESULTS = cast(Table, StudentExamResult.__table__)
PAPER_RESULTS = cast(Table, StudentPaperResult.__table__)


@dataclass
class Overview:
    exam: Examination
    run: ResultRun | None
    runs: list[ResultRun]
    approvals: list[Approval]
    unsubmitted: list[dict[str, str]]
    names: dict[uuid.UUID, str]
    maker_checker: bool


@dataclass
class StudentRow:
    result: StudentExamResult
    enrollment_no: str
    full_name: str
    cohort_code: str
    papers: list[StudentPaperResult]


def _dec(v: str | None) -> Decimal | None:
    return Decimal(v) if v is not None else None


class ResultsService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    # ---- loading --------------------------------------------------------------------------------
    @staticmethod
    async def exam(uow: UnitOfWork, exam_id: uuid.UUID, *, lock: bool = False) -> Examination:
        stmt = select(Examination).where(Examination.id == exam_id)
        if lock:
            stmt = stmt.with_for_update()
        exam = (await uow.session.scalars(stmt)).one_or_none()
        if exam is None:
            raise NotFound("Exam not found")
        return exam

    @staticmethod
    async def runs(uow: UnitOfWork, exam_id: uuid.UUID) -> list[ResultRun]:
        return list(
            (
                await uow.session.scalars(
                    select(ResultRun).where(ResultRun.exam_id == exam_id).order_by(ResultRun.revision.desc())
                )
            ).all()
        )

    async def run(self, uow: UnitOfWork, exam_id: uuid.UUID, run_id: uuid.UUID | None) -> ResultRun:
        """A run of this exam; ``None`` means the latest."""
        stmt = select(ResultRun).where(ResultRun.exam_id == exam_id)
        stmt = (
            stmt.where(ResultRun.id == run_id)
            if run_id
            else stmt.order_by(ResultRun.revision.desc()).limit(1)
        )
        run = (await uow.session.scalars(stmt)).first()
        if run is None:
            raise NotFound("These results haven't been processed yet.")
        return run

    @staticmethod
    async def unsubmitted(uow: UnitOfWork, exam_id: uuid.UUID) -> list[dict[str, str]]:
        rows = await uow.session.execute(
            select(Course.code, Cohort.code, PaperSubmission.status)
            .join(ExamPaper, ExamPaper.id == PaperSubmission.exam_paper_id)
            .join(Course, Course.id == ExamPaper.course_id)
            .join(Cohort, Cohort.id == PaperSubmission.cohort_id)
            .where(PaperSubmission.exam_id == exam_id, PaperSubmission.status.in_(("open", "returned")))
            .order_by(Course.code, Cohort.code)
        )
        return [{"course_code": c, "cohort_code": k, "status": s} for c, k, s in rows.all()]

    @staticmethod
    async def load_inputs(uow: UnitOfWork, exam: Examination, version_id: uuid.UUID) -> Inputs:
        """Every input of a computation, in four set-based queries."""
        version = (
            await uow.session.scalars(
                select(GradingSchemeVersion).where(GradingSchemeVersion.id == version_id)
            )
        ).one()
        papers = [
            Paper(
                spec=PaperSpec(
                    paper_id=str(p.id),
                    components=tuple(
                        Component(
                            code=c["code"],
                            max=Decimal(str(c["max"])),
                            min_pass=Decimal(str(c["min_pass"])) if c.get("min_pass") is not None else None,
                            label=c.get("label") or c["code"],
                        )
                        for c in p.components
                    ),
                    credits=p.credits,
                    pass_total=p.pass_total,
                    title=code,
                ),
                course_code=code,
                course_name=name,
            )
            for p, code, name in (
                await uow.session.execute(
                    select(ExamPaper, Course.code, Course.name)
                    .join(Course, Course.id == ExamPaper.course_id)
                    .where(ExamPaper.exam_id == exam.id)
                    .order_by(ExamPaper.position, ExamPaper.id)
                )
            ).all()
        ]
        students: dict[str, StudentIn] = {}
        for sid, enrollment, name, cohort_id in (
            await uow.session.execute(
                select(Student.id, Student.enrollment_no, Student.full_name, CohortMembership.cohort_id)
                .join(CohortMembership, CohortMembership.student_id == Student.id)
                .join(
                    ExamCohort,
                    (ExamCohort.cohort_id == CohortMembership.cohort_id) & (ExamCohort.exam_id == exam.id),
                )
                .where(Student.status.in_(ROSTER_STATUSES))
                .order_by(Student.id, CohortMembership.cohort_id)
            )
        ).all():
            students.setdefault(str(sid), StudentIn(str(sid), enrollment, name, str(cohort_id)))
        marks = {
            (str(pid), str(sid)): Mark({k: str(v) for k, v in comps.items()}, attendance)
            for pid, sid, comps, attendance in (
                await uow.session.execute(
                    select(
                        MarkEntry.exam_paper_id,
                        MarkEntry.student_id,
                        MarkEntry.components,
                        MarkEntry.attendance,
                    ).where(MarkEntry.exam_id == exam.id)
                )
            ).all()
        }
        return Inputs(str(version.id), version.config, tuple(papers), tuple(students.values()), marks)

    @staticmethod
    async def latest_version_id(uow: UnitOfWork, scheme_id: uuid.UUID) -> uuid.UUID:
        return (
            await uow.session.scalars(
                select(GradingSchemeVersion.id)
                .where(GradingSchemeVersion.scheme_id == scheme_id)
                .order_by(GradingSchemeVersion.version.desc())
                .limit(1)
            )
        ).one()

    # ---- processing -----------------------------------------------------------------------------
    async def request(
        self, uow: UnitOfWork, principal: Principal, exam_id: uuid.UUID, *, override_reason: str | None
    ) -> ResultRun:
        exam = await self.exam(uow, exam_id, lock=True)
        if exam.status not in PROCESSABLE:
            raise InvalidState(
                "Close marks entry before processing results."
                if exam.status == ExamStatus.MARKS_ENTRY_OPEN
                else "Results can't be processed at this stage."
            )
        running = (
            await uow.session.scalars(
                select(ResultRun.id).where(ResultRun.exam_id == exam.id, ResultRun.status == "running")
            )
        ).first()
        if running is not None:
            raise Conflict("These results are already being processed.")
        # In a correction of published results the papers were accepted when first published; the
        # correction carries its own reason, so unsubmitted papers don't need another one.
        pending = [] if exam.correction_started_at is not None else await self.unsubmitted(uow, exam.id)
        reason = (override_reason or "").strip()
        if pending and not reason:
            listed = ", ".join(f"{p['course_code']} · {p['cohort_code']}" for p in pending[:5])
            more = f" and {len(pending) - 5} more" if len(pending) > 5 else ""
            raise InvalidState(
                f"{len(pending)} paper(s) aren't submitted yet: {listed}{more}. Wait for faculty, or give a "
                "reason to process anyway.",
                unsubmitted=pending,
            )
        revision = (
            await uow.session.scalar(select(func.max(ResultRun.revision)).where(ResultRun.exam_id == exam.id))
            or 0
        ) + 1
        run = ResultRun(
            tenant_id=uow.require_tenant(),
            exam_id=exam.id,
            revision=revision,
            status="running",
            grading_scheme_version_id=await self.latest_version_id(uow, exam.grading_scheme_id),
            started_by=principal.user_id,
            override={"reason": reason, "unsubmitted": pending} if pending else None,
        )
        uow.session.add(run)
        await uow.flush()
        await enqueue(
            uow,
            "results.process",
            {"run_id": str(run.id)},
            dedupe_key=f"results:{run.id}",
            created_by=principal.user_id,
        )
        await record(
            uow,
            Actor.from_principal(principal),
            "results.processing_started",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Processing results for {exam.name} (revision {revision})"
            + (f", with {len(pending)} paper(s) not submitted" if pending else ""),
            after={"revision": revision, "unsubmitted": len(pending)},
            reason=reason or None,
        )
        return run

    async def execute(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID, *, final_attempt: bool
    ) -> dict[str, Any]:
        """The ``results.process`` job. A business problem fails the run with a readable reason; an
        unexpected error is retried, and on the last attempt the run is failed so the exam isn't stuck."""
        try:
            async with self.infra.db.uow(tenant_id) as uow:
                return await self._execute(uow, run_id)
        except (ProcessingError, InvalidState) as exc:
            await self._fail(tenant_id, run_id, str(exc) if isinstance(exc, ProcessingError) else exc.detail)
            return {"failed": str(exc)}
        except Exception:
            if final_attempt:
                await self._fail(tenant_id, run_id, "Processing failed unexpectedly. Try again.")
            raise

    async def _fail(self, tenant_id: uuid.UUID, run_id: uuid.UUID, detail: str | None) -> None:
        async with self.infra.db.uow(tenant_id) as uow:
            run = (
                await uow.session.scalars(select(ResultRun).where(ResultRun.id == run_id).with_for_update())
            ).one()
            if run.status == "running":
                run.status, run.error_detail, run.finished_at = "failed", detail, utcnow()

    async def _execute(self, uow: UnitOfWork, run_id: uuid.UUID) -> dict[str, Any]:
        run = (
            await uow.session.scalars(select(ResultRun).where(ResultRun.id == run_id).with_for_update())
        ).one()
        if run.status != "running":
            return {"skipped": run.status}
        exam = await self.exam(uow, run.exam_id, lock=True)  # mark writers wait until this commits
        if exam.status not in PROCESSABLE:
            raise InvalidState("Marks entry was reopened before processing started. Process again.")
        inputs = await self.load_inputs(uow, exam, run.grading_scheme_version_id)
        computed = await anyio.to_thread.run_sync(compute, inputs)
        previous = await self._previous(uow, exam.id, run.revision)
        await self._write(uow, run, computed)
        run.status = "completed"
        run.input_hash = input_hash(inputs)
        run.content_hash = computed.content_hash
        run.students = len(computed.outcomes)
        cohorts = {
            str(cid): (code, name)
            for cid, code, name in (
                await uow.session.execute(
                    select(Cohort.id, Cohort.code, Cohort.name)
                    .join(ExamCohort, ExamCohort.cohort_id == Cohort.id)
                    .where(ExamCohort.exam_id == exam.id)
                )
            ).all()
        }
        run.stats = statistics(computed, inputs.papers, cohorts)
        run.anomalies = anomalies(
            computed,
            inputs.papers,
            previous=previous,
            unsubmitted=(run.override or {}).get("unsubmitted", []),
        )
        run.finished_at = utcnow()
        await uow.session.execute(
            update(ResultRun)
            .where(ResultRun.exam_id == exam.id, ResultRun.status == "completed", ResultRun.id != run.id)
            .values(status="stale")
        )
        exam.grading_scheme_version_id = run.grading_scheme_version_id
        before = exam.status
        if exam.status in (ExamStatus.MARKS_ENTRY_CLOSED, ExamStatus.CORRECTION_DRAFT):
            exam.status = transition_for(exam.status, ExamAction.PROCESS, None).target.value
        exam.version += 1
        await uow.flush()
        await record(
            uow,
            Actor("user", run.started_by, None) if run.started_by else Actor.system("results"),
            "results.processed",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Results processed for {exam.name} (revision {run.revision}, {run.students} students)",
            before={"status": before},
            after={
                "status": exam.status,
                "revision": run.revision,
                "outcomes": run.stats["outcomes"],
                "input_hash": run.input_hash,
                "content_hash": run.content_hash,
            },
        )
        return {"revision": run.revision, "students": run.students}

    @staticmethod
    async def _previous(
        uow: UnitOfWork, exam_id: uuid.UUID, revision: int
    ) -> dict[str, dict[str, Any]] | None:
        prior = (
            await uow.session.scalars(
                select(ResultRun.id)
                .where(
                    ResultRun.exam_id == exam_id,
                    ResultRun.revision < revision,
                    ResultRun.status.in_(PREVIOUS),
                )
                .order_by(ResultRun.revision.desc())
                .limit(1)
            )
        ).first()
        if prior is None:
            return None
        rows = await uow.session.execute(
            select(
                StudentExamResult.student_id,
                StudentExamResult.total,
                StudentExamResult.grade,
                StudentExamResult.outcome,
            ).where(StudentExamResult.result_run_id == prior)
        )
        return {
            str(sid): {"total": num(total), "grade": grade, "outcome": outcome}
            for sid, total, grade, outcome in rows.all()
        }

    @staticmethod
    async def _write(uow: UnitOfWork, run: ResultRun, computed: Computed) -> None:
        tenant_id = uow.require_tenant()
        exams: list[dict[str, Any]] = []
        papers: list[dict[str, Any]] = []
        for o in computed.outcomes:
            d = result_doc(o)
            exams.append(
                {
                    "tenant_id": tenant_id,
                    "result_run_id": run.id,
                    "student_id": uuid.UUID(d["student_id"]),
                    "cohort_id": uuid.UUID(d["cohort_id"]),
                    "outcome": d["outcome"],
                    "total": _dec(d["total"]),
                    "max_total": _dec(d["max_total"]),
                    "percentage": _dec(d["percentage"]),
                    "grade": d["grade"],
                    "grade_point": _dec(d["grade_point"]),
                    "sgpa": _dec(d["sgpa"]),
                    "credits_attempted": _dec(d["credits_attempted"]),
                    "credits_earned": _dec(d["credits_earned"]),
                    "rank": d["rank"],
                    "notes": d["notes"],
                }
            )
            for p in d["papers"]:
                papers.append(
                    {
                        "tenant_id": tenant_id,
                        "result_run_id": run.id,
                        "student_id": uuid.UUID(d["student_id"]),
                        "exam_paper_id": uuid.UUID(p["paper_id"]),
                        "outcome": p["outcome"],
                        "passed": p["outcome"] == "pass",
                        "attendance": p["attendance"],
                        "components": p["components"],
                        "total": _dec(p["total"]),
                        "max_total": Decimal(p["max_total"]),
                        "percentage": _dec(p["percentage"]),
                        "grade": p["grade"],
                        "grade_point": _dec(p["grade_point"]),
                        "credits": _dec(p["credits"]),
                        "failed_components": p["failed_components"],
                        "missing_components": p["missing_components"],
                    }
                )
        # Core inserts on the tables (not the ORM entities): no per-row ORM bookkeeping for rows that are
        # never loaded back into this session.
        for i in range(0, len(exams), CHUNK):
            await uow.session.execute(insert(EXAM_RESULTS), exams[i : i + CHUNK])
        for i in range(0, len(papers), CHUNK):
            await uow.session.execute(insert(PAPER_RESULTS), papers[i : i + CHUNK])

    async def discard(
        self, uow: UnitOfWork, principal: Principal, exam_id: uuid.UUID, reason: str
    ) -> Examination:
        """ "Back to marks entry": the processed results are set aside (stale) and marks can change again."""
        from app.modules.results.staleness import marks_changed

        exam = await self.exam(uow, exam_id, lock=True)
        if exam.status != ExamStatus.PROCESSED:
            raise InvalidState("Only processed results can be set aside.")
        await marks_changed(uow, Actor.from_principal(principal), exam)
        await record(
            uow,
            Actor.from_principal(principal),
            "results.discarded",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Results for {exam.name} set aside to change marks",
            reason=reason.strip(),
        )
        return exam

    # ---- approval -------------------------------------------------------------------------------
    async def maker_checker(self, uow: UnitOfWork) -> bool:
        settings = (await uow.session.scalars(select(TenantSettings))).one_or_none()
        if settings is None or settings.approval_mode != "maker_checker":
            return False
        return (await EntitlementService(self.infra).effective(uow)).has(F.MAKER_CHECKER_APPROVAL)

    async def _decidable(
        self, uow: UnitOfWork, principal: Principal, exam_id: uuid.UUID, run_id: uuid.UUID
    ) -> tuple[Examination, ResultRun]:
        exam = await self.exam(uow, exam_id, lock=True)
        AuthService(self.infra).require_recent_auth(principal)
        latest = await self.run(uow, exam.id, None)
        if latest.id != run_id:
            raise Conflict("These results were processed again. Review the latest results first.")
        if latest.status == "stale" or exam.status == ExamStatus.MARKS_ENTRY_CLOSED:
            raise InvalidState("Marks changed after processing. Process the results again first.")
        if exam.status != ExamStatus.PROCESSED or latest.status != "completed":
            raise InvalidState("Only processed results waiting for approval can be approved or rejected.")
        return exam, latest

    async def approve(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID,
        run_id: uuid.UUID,
        comment: str | None,
    ) -> ResultRun:
        exam, run = await self._decidable(uow, principal, exam_id, run_id)
        if await self.maker_checker(uow) and run.started_by == principal.user_id:
            raise PermissionDenied("Another administrator has to approve results you processed.")
        inputs = await self.load_inputs(uow, exam, run.grading_scheme_version_id)
        if input_hash(inputs) != run.input_hash:
            raise InvalidState(
                "Something these results depend on changed after processing (marks, papers or students). "
                "Process the results again first."
            )
        assert run.content_hash is not None
        uow.session.add(
            Approval(
                tenant_id=uow.require_tenant(),
                result_run_id=run.id,
                exam_id=exam.id,
                decision="approved",
                decided_by=principal.user_id,
                content_hash=run.content_hash,
                comment=(comment or "").strip() or None,
            )
        )
        run.status = "approved"
        t = transition_for(exam.status, ExamAction.APPROVE, None)
        exam.status, exam.version = t.target.value, exam.version + 1
        await uow.session.execute(
            update(PaperSubmission).where(PaperSubmission.exam_id == exam.id).values(status="locked")
        )
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "results.approved",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Results approved for {exam.name} (revision {run.revision})",
            before={"status": t.source.value},
            after={"status": t.target.value, "revision": run.revision, "content_hash": run.content_hash},
            reason=(comment or "").strip() or None,
        )
        return run

    async def reject(
        self, uow: UnitOfWork, principal: Principal, exam_id: uuid.UUID, run_id: uuid.UUID, reason: str
    ) -> ResultRun:
        """A reviewer sends processed results back. The exam stays processed; the processor fixes marks
        (which makes these results stale) and processes again."""
        exam, run = await self._decidable(uow, principal, exam_id, run_id)
        assert run.content_hash is not None
        uow.session.add(
            Approval(
                tenant_id=uow.require_tenant(),
                result_run_id=run.id,
                exam_id=exam.id,
                decision="rejected",
                decided_by=principal.user_id,
                content_hash=run.content_hash,
                comment=reason.strip(),
            )
        )
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "results.rejected",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Results rejected for {exam.name} (revision {run.revision})",
            after={"revision": run.revision},
            reason=reason.strip(),
        )
        return run

    async def revoke(
        self, uow: UnitOfWork, principal: Principal, exam_id: uuid.UUID, reason: str
    ) -> ResultRun:
        """Approved → processed (state diagram §1): the approval stops counting and papers unlock."""
        exam = await self.exam(uow, exam_id, lock=True)
        AuthService(self.infra).require_recent_auth(principal)
        t = transition_for(exam.status, ExamAction.REVOKE_APPROVAL, reason)
        run = await self.run(uow, exam.id, None)
        if run.status != "approved":
            raise InvalidState("These results aren't approved.")
        assert run.content_hash is not None
        uow.session.add(
            Approval(
                tenant_id=uow.require_tenant(),
                result_run_id=run.id,
                exam_id=exam.id,
                decision="revoked",
                decided_by=principal.user_id,
                content_hash=run.content_hash,
                comment=reason.strip(),
            )
        )
        run.status = "completed"
        exam.status, exam.version = t.target.value, exam.version + 1
        await uow.session.execute(
            update(PaperSubmission)
            .where(PaperSubmission.exam_id == exam.id, PaperSubmission.status == "locked")
            .values(status="submitted")
        )
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "results.approval_revoked",
            entity_type="exam",
            entity_id=exam.id,
            summary=f"Approval revoked for {exam.name} (revision {run.revision})",
            before={"status": t.source.value},
            after={"status": t.target.value},
            reason=reason.strip(),
        )
        return run

    # ---- reads ----------------------------------------------------------------------------------
    @staticmethod
    async def user_names(uow: UnitOfWork, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
        wanted = [i for i in ids if i]
        if not wanted:
            return {}
        rows = await uow.session.execute(select(User.id, User.full_name).where(in_values(User.id, wanted)))
        return {uid: name for uid, name in rows.all()}  # noqa: C416 (Row → tuple unpacking)

    async def overview(self, uow: UnitOfWork, exam_id: uuid.UUID) -> Overview:
        exam = await self.exam(uow, exam_id)
        runs = await self.runs(uow, exam.id)
        approvals = list(
            (
                await uow.session.scalars(
                    select(Approval).where(Approval.exam_id == exam.id).order_by(Approval.created_at.desc())
                )
            ).all()
        )
        names = await self.user_names(uow, {r.started_by for r in runs} | {a.decided_by for a in approvals})
        return Overview(
            exam=exam,
            run=runs[0] if runs else None,
            runs=runs,
            approvals=approvals,
            unsubmitted=await self.unsubmitted(uow, exam.id),
            names=names,
            maker_checker=await self.maker_checker(uow),
        )

    async def students(
        self,
        uow: UnitOfWork,
        exam_id: uuid.UUID,
        run_id: uuid.UUID | None,
        *,
        q: str | None,
        outcome: str | None,
        cohort_id: uuid.UUID | None,
        after: str | None,
        limit: int,
    ) -> tuple[ResultRun, list[StudentRow], str | None]:
        run = await self.run(uow, exam_id, run_id)
        stmt = (
            select(StudentExamResult, Student.enrollment_no, Student.full_name, Cohort.code)
            .join(Student, Student.id == StudentExamResult.student_id)
            .join(Cohort, Cohort.id == StudentExamResult.cohort_id)
            .where(StudentExamResult.result_run_id == run.id)
        )
        if outcome:
            stmt = stmt.where(StudentExamResult.outcome == outcome)
        if cohort_id:
            stmt = stmt.where(StudentExamResult.cohort_id == cohort_id)
        if q and q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(Student.enrollment_no.ilike(like), Student.full_name.ilike(like)))
        if after:
            stmt = stmt.where(Student.enrollment_no > after)
        rows = (await uow.session.execute(stmt.order_by(Student.enrollment_no).limit(limit + 1))).all()
        more = len(rows) > limit
        rows = rows[:limit]
        papers = await self._papers(uow, run.id, [r[0].student_id for r in rows])
        out = [
            StudentRow(r, enrollment, name, cohort, papers.get(r.student_id, []))
            for r, enrollment, name, cohort in rows
        ]
        return run, out, (out[-1].enrollment_no if more and out else None)

    @staticmethod
    async def _papers(
        uow: UnitOfWork, run_id: uuid.UUID, student_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[StudentPaperResult]]:
        if not student_ids:
            return {}
        out: dict[uuid.UUID, list[StudentPaperResult]] = {}
        for p in (
            await uow.session.scalars(
                select(StudentPaperResult)
                .join(ExamPaper, ExamPaper.id == StudentPaperResult.exam_paper_id)
                .where(
                    StudentPaperResult.result_run_id == run_id,
                    in_values(StudentPaperResult.student_id, student_ids),
                )
                .order_by(ExamPaper.position, ExamPaper.id)
            )
        ).all():
            out.setdefault(p.student_id, []).append(p)
        return out

    async def student(
        self, uow: UnitOfWork, exam_id: uuid.UUID, run_id: uuid.UUID | None, student_id: uuid.UUID
    ) -> tuple[ResultRun, StudentRow]:
        run = await self.run(uow, exam_id, run_id)
        row = (
            await uow.session.execute(
                select(StudentExamResult, Student.enrollment_no, Student.full_name, Cohort.code)
                .join(Student, Student.id == StudentExamResult.student_id)
                .join(Cohort, Cohort.id == StudentExamResult.cohort_id)
                .where(StudentExamResult.result_run_id == run.id, StudentExamResult.student_id == student_id)
            )
        ).first()
        if row is None:
            raise NotFound("This student has no result in this run.")
        r, enrollment, name, cohort = row
        papers = await self._papers(uow, run.id, [student_id])
        return run, StudentRow(r, enrollment, name, cohort, papers.get(student_id, []))
