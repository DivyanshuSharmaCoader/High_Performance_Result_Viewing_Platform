"""Synthetic result-day data for the k6 load tests (P10.6, docs/11 §4).

Usage (against the running stack's database, i.e. after `make stack` + `make seed-stack`):

    uv run python scripts/loadtest_data.py --students 8000 --sessions 1000 --out ../benchmarks/data

Creates (once; re-running only refreshes the sessions file) a tenant ``loadtest`` with ``--students`` active
students who can sign in (all with the synthetic password below), each in one of 40 cohorts, and one
semester exam of six papers that is processed, approved and **published** through the real services. Then
it opens ``--sessions`` sessions for the pre-authenticated variant and writes ``loadtest-users.json``:
``[{"login": ..., "token": ...}, ...]``. That file grants access to synthetic accounts only; it is
git-ignored and should be deleted after the run.

Deterministic: the same seed gives the same students and marks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import insert, select

from app.core.clock import utcnow
from app.core.config import Settings
from app.core.container import Infra
from app.core.http import Principal

SLUG = "loadtest"
PASSWORD = "loadtest-student-pass"  # noqa: S105 - synthetic accounts in a load-test tenant
OWNER = "owner@loadtest.example.com"


async def build(infra: Infra, n_students: int, n_papers: int, seed: int) -> uuid.UUID:
    from app.jobs_registry import load_job_handlers
    from app.modules.academics.models import AcademicSession, Cohort, Course, Program, Term
    from app.modules.audit.service import Actor
    from app.modules.directory.models import CohortMembership, Student
    from app.modules.entitlements.sync import sync_catalogue
    from app.modules.examinations.models import ExamCohort, Examination, ExamPaper, PaperSubmission
    from app.modules.grading.service import GradingService
    from app.modules.grading.templates import BY_KEY
    from app.modules.identity.models import User, UserRole
    from app.modules.identity.permissions import permissions_for
    from app.modules.marks.models import MarkEntry
    from app.modules.publishing.service import PublishingService
    from app.modules.results.service import ResultsService
    from app.modules.tenancy.models import Tenant
    from app.modules.tenancy.service import OwnerSpec, ProvisionRequest, provision_tenant

    load_job_handlers()
    await sync_catalogue(infra.db)
    async with infra.db.platform_uow() as uow:
        existing = (await uow.session.scalars(select(Tenant).where(Tenant.slug == SLUG))).one_or_none()
    if existing is not None:
        print(f"tenant {SLUG} exists; reusing it")
        return existing.id

    async with infra.db.uow() as uow:
        tenant = await provision_tenant(
            uow,
            ProvisionRequest(
                slug=SLUG,
                name="Load Test University",
                type="university",
                plan_code="enterprise",
                owner=OwnerSpec(
                    email=OWNER,
                    full_name="Load Test Owner",
                    password_hash=await infra.passwords.hash(PASSWORD),
                ),
            ),
            Actor.system("loadtest"),
        )
    tid = tenant.id
    rng = random.Random(seed)  # noqa: S311 - synthetic data
    password_hash = await infra.passwords.hash(PASSWORD)  # one hash for every synthetic student
    async with infra.db.uow(tid) as uow:
        s = uow.session
        owner = (await s.scalars(select(User).where(User.login_id == OWNER))).one()
        sess = AcademicSession(
            tenant_id=tid,
            code="2025-26",
            name="2025-26",
            starts_on=date(2025, 7, 1),
            ends_on=date(2026, 6, 30),
            is_current=True,
        )
        prog = Program(tenant_id=tid, code="BTECH", name="B.Tech.")
        courses = [
            Course(tenant_id=tid, code=f"LT{i + 1:03}", name=f"Course {i + 1}", credits=Decimal(4))
            for i in range(n_papers)
        ]
        s.add_all([sess, prog, *courses])
        await uow.flush()
        term = Term(tenant_id=tid, session_id=sess.id, code="ODD", name="Odd semester", sequence=1)
        cohorts = [
            Cohort(
                tenant_id=tid, code=f"C{i:02}", name=f"Section {i}", program_id=prog.id, session_id=sess.id
            )
            for i in range(40)
        ]
        s.add(term)
        s.add_all(cohorts)
        await uow.flush()
        scheme = await GradingService(infra).create(
            uow, None, name="10-point", description=None, config=BY_KEY["credit_10_point"].config
        )

        users, students, roles, members = [], [], [], []
        for i in range(n_students):
            uid, sid, login = uuid.uuid4(), uuid.uuid4(), f"LT{i:06}"
            users.append(
                {
                    "id": uid,
                    "tenant_id": tid,
                    "kind": "student",
                    "login_id": login,
                    "full_name": f"Student {i}",
                    "password_hash": password_hash,
                    "status": "active",
                }
            )
            roles.append({"tenant_id": tid, "user_id": uid, "role": "student"})
            students.append(
                {
                    "id": sid,
                    "tenant_id": tid,
                    "enrollment_no": login,
                    "full_name": f"Student {i}",
                    "status": "active",
                    "user_id": uid,
                }
            )
            members.append(
                {
                    "tenant_id": tid,
                    "cohort_id": cohorts[i % 40].id,
                    "student_id": sid,
                    "session_id": sess.id,
                    "program_id": prog.id,
                }
            )
        for table, rows in (
            (User, users),
            (UserRole, roles),
            (Student, students),
            (CohortMembership, members),
        ):
            for c in range(0, len(rows), 2000):
                await s.execute(insert(table), rows[c : c + 2000])

        exam = Examination(
            tenant_id=tid,
            term_id=term.id,
            name="End semester examination",
            kind="semester",
            status="marks_entry_closed",
            grading_scheme_id=scheme.id,
        )
        s.add(exam)
        await uow.flush()
        s.add_all(ExamCohort(tenant_id=tid, exam_id=exam.id, cohort_id=c.id) for c in cohorts)
        papers = [
            ExamPaper(
                tenant_id=tid,
                exam_id=exam.id,
                course_id=c.id,
                position=i,
                components=[
                    {"code": "INT", "label": "Internal", "max": "40", "min_pass": None},
                    {"code": "EXT", "label": "External", "max": "60", "min_pass": "21"},
                ],
                max_total=Decimal(100),
                credits=Decimal(4),
            )
            for i, c in enumerate(courses)
        ]
        s.add_all(papers)
        await uow.flush()
        s.add_all(
            PaperSubmission(
                tenant_id=tid, exam_id=exam.id, exam_paper_id=p.id, cohort_id=c.id, status="submitted"
            )
            for p in papers
            for c in cohorts
        )
        marks = []
        for p in papers:
            for m in members:
                a, b = rng.randint(12, 40), rng.randint(18, 60)
                marks.append(
                    {
                        "tenant_id": tid,
                        "exam_id": exam.id,
                        "exam_paper_id": p.id,
                        "cohort_id": m["cohort_id"],
                        "student_id": m["student_id"],
                        "components": {"INT": str(a), "EXT": str(b)},
                        "total": Decimal(a + b),
                        "attendance": "present",
                    }
                )
        for c in range(0, len(marks), 2000):
            await s.execute(insert(MarkEntry), marks[c : c + 2000])
        owner_id, exam_id = owner.id, exam.id

    principal = Principal(
        kind="user",
        user_id=owner_id,
        tenant_id=tid,
        roles=frozenset({"institution_owner"}),
        permissions=permissions_for(["institution_owner"]),
        session_hash=b"",
        user_kind="staff",
        display_name="Load Test Owner",
        reauthenticated_at=utcnow(),
    )
    results = ResultsService(infra)
    async with infra.db.uow(tid) as uow:
        run = await results.request(uow, principal, exam_id, override_reason=None)
        run_id = run.id
    print(await results.execute(tid, run_id, final_attempt=True))
    async with infra.db.uow(tid) as uow:
        await results.approve(uow, principal, exam_id, run_id, "load-test data")
    async with infra.db.uow(tid) as uow:
        pub = await PublishingService(infra).publish(uow, principal, exam_id, at=None)
        print(f"published {pub.students} results (publication {pub.id})")
    return tid


async def sessions(infra: Infra, tid: uuid.UUID, n: int, out: Path) -> None:
    from app.modules.identity.models import User
    from app.modules.identity.sessions import SessionService

    svc = SessionService(infra)
    rows = []
    async with infra.db.uow(tid) as uow:
        users = (
            await uow.session.scalars(
                select(User).where(User.kind == "student").order_by(User.login_id).limit(n)
            )
        ).all()
        for u in users:
            rows.append(
                {"login": u.login_id, "token": await svc.create(uow, u, ip=None, user_agent="k6 load test")}
            )
    path = out / "loadtest-users.json"

    def write() -> None:
        out.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows))

    await asyncio.to_thread(write)
    print(f"wrote {len(rows)} sessions to {path} (synthetic accounts; delete after the run)")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=8000)
    parser.add_argument("--papers", type=int, default=6)
    parser.add_argument("--sessions", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", type=Path, default=Path("../benchmarks/data"))
    args = parser.parse_args()
    infra = Infra.build(Settings(), app_name="scorecode-loadtest")
    try:
        tid = await build(infra, args.students, args.papers, args.seed)
        await sessions(infra, tid, args.sessions, args.out)
    finally:
        await infra.close()


if __name__ == "__main__":
    asyncio.run(main())
