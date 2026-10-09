"""Results history for the demo tenants (P17.1, P17.2): `scorecode seed --with-history`.

Each tenant gets exams in the states a presentation needs (docs/demo/):
- published ones, so students see a history (Thapar across two academic years, for an SGPA trail);
- one approved and not yet published, to publish (or schedule) live;
- at Thapar, one open for marks entry, to show the grid and an import with errors.

Exams, papers and marks are inserted as data (synthetic and deterministic, like scripts/loadtest_data.py).
Processing, approval and publication go through the real services and the job queue, so every check
and every snapshot is the product's own. Idempotent: an exam that already exists by term and name is
moved on from wherever it is. No real student data anywhere (decision D25).
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import insert, select

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.http import Principal
from app.core.jobs import Worker
from app.modules.academics.models import AcademicSession, Cohort, Course, Term
from app.modules.directory.models import CohortMembership
from app.modules.examinations.models import ExamCohort, Examination, ExamPaper, PaperSubmission
from app.modules.grading.models import GradingScheme
from app.modules.identity.models import User
from app.modules.identity.permissions import permissions_for
from app.modules.marks.models import MarkEntry
from app.modules.publishing.service import PublishingService
from app.modules.results.models import ResultRun
from app.modules.results.service import ResultsService

THEORY: list[dict[str, Any]] = [  # Thapar: internal 40, end-semester 60 (at least 21 of it to pass)
    {"code": "INT", "label": "Internal", "max": "40", "min_pass": None},
    {"code": "EXT", "label": "End semester", "max": "60", "min_pass": "21"},
]
SCHOOL: list[dict[str, Any]] = [  # board pattern: theory 80 (27 to pass), internal assessment 20
    {"code": "TH", "label": "Theory", "max": "80", "min_pass": "27"},
    {"code": "IA", "label": "Internal assessment", "max": "20", "min_pass": None},
]
TEST: list[dict[str, Any]] = [
    {"code": "MARKS", "label": "Marks", "max": "100", "min_pass": None}
]  # coaching test papers


@dataclass(frozen=True)
class ExamPlan:
    session: str
    term: str
    name: str
    kind: str
    cohorts: tuple[str, ...]  # cohort codes (in that session)
    courses: tuple[str, ...]
    components: list[dict[str, Any]]
    outcome: str  # "published" | "approved" | "open" (marks entry, partly entered)


THAPAR_COHORTS = ("COE-2A", "COE-2B", "ECE-2A", "MEC-2A")
THAPAR_COURSES = ("UCS301", "UCS310", "UCS405")
PLANS: dict[str, list[ExamPlan]] = {
    "thapar": [
        ExamPlan(
            "2024-25",
            "ODD",
            "End semester examination, odd 2024",
            "semester",
            THAPAR_COHORTS,
            THAPAR_COURSES,
            THEORY,
            "published",
        ),
        ExamPlan(
            "2024-25",
            "EVEN",
            "End semester examination, even 2025",
            "semester",
            THAPAR_COHORTS,
            THAPAR_COURSES,
            THEORY,
            "published",
        ),
        ExamPlan(
            "2025-26",
            "ODD",
            "End semester examination, odd 2025",
            "semester",
            THAPAR_COHORTS,
            THAPAR_COURSES,
            THEORY,
            "published",
        ),
        ExamPlan(
            "2025-26",
            "EVEN",
            "End semester examination, even 2026",
            "semester",
            THAPAR_COHORTS,
            THAPAR_COURSES,
            THEORY,
            "approved",
        ),
        ExamPlan(
            "2025-26",
            "EVEN",
            "Mid-semester test, even 2026",
            "unit_test",
            THAPAR_COHORTS,
            THAPAR_COURSES,
            THEORY,
            "open",
        ),
    ],
    "demoschool": [
        ExamPlan(
            "2025-26",
            "TERM1",
            "Term 1 examination",
            "term",
            ("8A", "8B", "9A", "10A"),
            ("ENG", "HIN", "MATH", "SCI", "SST"),
            SCHOOL,
            "published",
        ),
        ExamPlan(
            "2025-26",
            "TERM2",
            "Term 2 examination",
            "term",
            ("8A", "8B", "9A", "10A"),
            ("ENG", "HIN", "MATH", "SCI", "SST"),
            SCHOOL,
            "approved",
        ),
    ],
    "democoaching": [
        ExamPlan(
            "2025-26",
            "PHASE1",
            "JEE test series · Test 1",
            "unit_test",
            ("JEE-MA", "JEE-EB"),
            ("PHY", "CHE", "MAT"),
            TEST,
            "published",
        ),
        ExamPlan(
            "2025-26",
            "PHASE1",
            "NEET test series · Test 1",
            "unit_test",
            ("NEET-MA",),
            ("PHY", "CHE", "BIO"),
            TEST,
            "published",
        ),
        ExamPlan(
            "2025-26",
            "PHASE2",
            "JEE test series · Test 2",
            "unit_test",
            ("JEE-MA", "JEE-EB"),
            ("PHY", "CHE", "MAT"),
            TEST,
            "approved",
        ),
    ],
}


def _marks(rng: random.Random, ability: float, components: list[dict[str, Any]]) -> dict[str, str]:
    out = {}
    for c in components:
        top = int(c["max"])
        share = min(0.99, max(0.08, rng.gauss(ability, 0.09)))
        out[c["code"]] = str(round(top * share))
    return out


async def _owner(infra: Infra, tenant_id: uuid.UUID, owner_email: str) -> Principal:
    async with infra.db.uow(tenant_id) as uow:
        owner = (await uow.session.scalars(select(User).where(User.login_id == owner_email))).one()
    return Principal(
        kind="user",
        user_id=owner.id,
        tenant_id=tenant_id,
        roles=frozenset({"institution_owner"}),
        permissions=permissions_for(["institution_owner"]),
        session_hash=b"",
        user_kind="staff",
        display_name=owner.full_name,
        reauthenticated_at=utcnow(),
    )


async def _past_memberships(infra: Infra, tenant_id: uuid.UUID, session_code: str) -> None:
    """Students sat earlier sessions too: put each one in the same-coded cohort of that session."""
    async with infra.db.uow(tenant_id) as uow:
        s = uow.session
        past = (
            await s.scalars(select(AcademicSession).where(AcademicSession.code == session_code))
        ).one_or_none()
        current = (await s.scalars(select(AcademicSession).where(AcademicSession.is_current.is_(True)))).one()
        if past is None or past.id == current.id:
            return
        past_cohorts = {
            c.code: c for c in (await s.scalars(select(Cohort).where(Cohort.session_id == past.id))).all()
        }
        rows = (
            await s.execute(
                select(CohortMembership.student_id, Cohort.code)
                .join(Cohort, Cohort.id == CohortMembership.cohort_id)
                .where(CohortMembership.session_id == current.id)
            )
        ).all()
        already = set(
            (
                await s.scalars(
                    select(CohortMembership.student_id).where(CohortMembership.session_id == past.id)
                )
            ).all()
        )
        new = [
            {
                "tenant_id": tenant_id,
                "cohort_id": past_cohorts[code].id,
                "student_id": student_id,
                "session_id": past.id,
                "program_id": past_cohorts[code].program_id,
            }
            for student_id, code in rows
            if code in past_cohorts and student_id not in already
        ]
        if new:
            await s.execute(insert(CohortMembership), new)


async def _create(infra: Infra, tenant_id: uuid.UUID, plan: ExamPlan, rng: random.Random) -> uuid.UUID:
    async with infra.db.uow(tenant_id) as uow:
        s = uow.session
        sess = (await s.scalars(select(AcademicSession).where(AcademicSession.code == plan.session))).one()
        term = (await s.scalars(select(Term).where(Term.session_id == sess.id, Term.code == plan.term))).one()
        existing = (
            await s.scalars(
                select(Examination.id).where(Examination.term_id == term.id, Examination.name == plan.name)
            )
        ).one_or_none()
        if existing is not None:
            return existing
        cohorts = (
            await s.scalars(select(Cohort).where(Cohort.session_id == sess.id, Cohort.code.in_(plan.cohorts)))
        ).all()
        courses = {
            c.code: c for c in (await s.scalars(select(Course).where(Course.code.in_(plan.courses)))).all()
        }
        scheme = (await s.scalars(select(GradingScheme).order_by(GradingScheme.created_at))).first()
        assert scheme is not None, "seed_grading runs first"
        exam = Examination(
            tenant_id=tenant_id,
            term_id=term.id,
            name=plan.name,
            kind=plan.kind,
            status="marks_entry_open" if plan.outcome == "open" else "marks_entry_closed",
            grading_scheme_id=scheme.id,
        )
        s.add(exam)
        await uow.flush()
        s.add_all(ExamCohort(tenant_id=tenant_id, exam_id=exam.id, cohort_id=c.id) for c in cohorts)
        max_total = sum(Decimal(c["max"]) for c in plan.components)
        papers = [
            ExamPaper(
                tenant_id=tenant_id,
                exam_id=exam.id,
                course_id=courses[code].id,
                position=i,
                components=plan.components,
                max_total=max_total,
                credits=courses[code].credits,
            )
            for i, code in enumerate(plan.courses)
        ]
        s.add_all(papers)
        await uow.flush()
        s.add_all(
            PaperSubmission(
                tenant_id=tenant_id,
                exam_id=exam.id,
                exam_paper_id=p.id,
                cohort_id=c.id,
                status="open" if plan.outcome == "open" else "submitted",
            )
            for p in papers
            for c in cohorts
        )
        members = (
            await s.execute(
                select(CohortMembership.student_id, CohortMembership.cohort_id)
                .where(CohortMembership.cohort_id.in_([c.id for c in cohorts]))
                .order_by(CohortMembership.student_id)
            )
        ).all()
        marks = []
        for student_id, cohort_id in members:
            ability = min(0.95, max(0.3, rng.gauss(0.66, 0.13)))
            for p in papers:
                if plan.outcome == "open" and rng.random() < 0.4:
                    continue  # marks entry still in progress
                if rng.random() < 0.015:
                    marks.append(
                        {
                            "tenant_id": tenant_id,
                            "exam_id": exam.id,
                            "exam_paper_id": p.id,
                            "cohort_id": cohort_id,
                            "student_id": student_id,
                            "components": {},
                            "total": None,
                            "attendance": "absent",
                        }
                    )
                    continue
                values = _marks(rng, ability, plan.components)
                marks.append(
                    {
                        "tenant_id": tenant_id,
                        "exam_id": exam.id,
                        "exam_paper_id": p.id,
                        "cohort_id": cohort_id,
                        "student_id": student_id,
                        "components": values,
                        "total": sum(Decimal(v) for v in values.values()),
                        "attendance": "present",
                    }
                )
        for i in range(0, len(marks), 2000):
            await s.execute(insert(MarkEntry), marks[i : i + 2000])
        return exam.id


async def _advance(
    infra: Infra, tenant_id: uuid.UUID, exam_id: uuid.UUID, outcome: str, who: Principal
) -> str:
    """From wherever the exam is to the plan's outcome, through the services."""
    results, publishing = ResultsService(infra), PublishingService(infra)
    async with infra.db.uow(tenant_id) as uow:
        status = (
            await uow.session.scalars(select(Examination.status).where(Examination.id == exam_id))
        ).one()
    if outcome == "open":
        return status
    if status == "marks_entry_closed":
        async with infra.db.uow(tenant_id) as uow:
            await results.request(uow, who, exam_id, override_reason=None)
        # The queued job runs here or in a running worker, whichever claims it first (SKIP LOCKED).
        await Worker(infra, ["processing"]).drain()
    async with infra.db.uow(tenant_id) as uow:
        status = (
            await uow.session.scalars(select(Examination.status).where(Examination.id == exam_id))
        ).one()
        if status == "processed":
            run_id = (
                await uow.session.scalars(
                    select(ResultRun.id)
                    .where(ResultRun.exam_id == exam_id, ResultRun.status == "completed")
                    .order_by(ResultRun.created_at.desc())
                )
            ).first()
            if run_id is None:
                return status  # processing failed: the reason is on the run, in the admin UI
            await results.approve(uow, who, exam_id, run_id, "Demo data: checked")
            status = "approved"
    if outcome == "published" and status == "approved":
        async with infra.db.uow(tenant_id) as uow:
            await publishing.publish(uow, who, exam_id, at=None)
            status = "published"
    return status


async def seed_history(
    infra: Infra, tenant_id: uuid.UUID, slug: str, owner_email: str
) -> list[tuple[str, str]]:
    plans = PLANS.get(slug, [])
    if not plans:
        return []
    for session_code in sorted({p.session for p in plans}):
        await _past_memberships(infra, tenant_id, session_code)
    who = await _owner(infra, tenant_id, owner_email)
    rng = random.Random(f"{slug}-history")  # noqa: S311 - demo data, not security
    done = []
    for plan in plans:  # in order: earlier exams are published first, so "latest" is the newest
        exam_id = await _create(infra, tenant_id, plan, rng)
        done.append((plan.name, await _advance(infra, tenant_id, exam_id, plan.outcome, who)))
    return done
