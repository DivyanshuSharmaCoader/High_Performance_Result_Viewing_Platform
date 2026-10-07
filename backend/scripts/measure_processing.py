"""Measure result processing for 8,000 students × 6 papers (P9.5, PT-6 / NFR-6: target < 2 min).

Usage (needs `make up`): uv run python scripts/measure_processing.py [--students 8000] [--papers 6] [--runs 3]

Creates a scratch database with one tenant, ``--students`` active students in cohorts of 200 and one closed
exam whose ``--papers`` papers (Internal /40 + External /60, 4 credits, the 10-point credit scheme) have a
mark for every student (about 5% absent). Then, in-process (no network hop):

* process — POST …/results/process, then the ``results.process`` job: load, compute, write rows, hashes,
  statistics, anomalies (each run is a new revision, so every run writes the full set of rows again);
* the job's phases on their own, read-only: load inputs, compute, input hash;
* approve — POST …/results/approve, which re-loads the inputs and re-computes the input hash in the request.

The scratch database is dropped afterwards. Numbers depend on the machine; record them with its details.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import random
import statistics
import time
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import asyncpg
import httpx
from sqlalchemy import insert, select, text

from app.core.config import Environment, Settings

PG = ("localhost", 55432)
DB = f"scorecode_bench_{uuid.uuid4().hex[:6]}"
MIGRATOR_PW = "migrator-dev-pw"  # the local docker-compose role, as in tests/conftest.py
PASSWORD = uuid.uuid4().hex  # the scratch tenant owner; never stored


class RollBack(Exception):
    """Leave a measuring transaction without keeping what it wrote."""


def url(role: str, password: str, db: str = DB) -> str:
    return f"postgresql+asyncpg://{role}:{password}@{PG[0]}:{PG[1]}/{db}"


async def admin(sql: str) -> None:
    c = await asyncpg.connect(
        host=PG[0], port=PG[1], user="scorecode_migrator", password=MIGRATOR_PW, database="scorecode"
    )
    try:
        await c.execute(sql)
    finally:
        await c.close()


def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        env=Environment.TEST,
        log_json=False,
        log_level="WARNING",
        database_url_app=url("scorecode_app", "app-dev-pw"),
        database_url_platform=url("scorecode_platform", "platform-dev-pw"),
        database_url_migrator=url("scorecode_migrator", MIGRATOR_PW),
        redis_url="redis://localhost:56379/14",
        s3_endpoint_url="http://localhost:59000",
        s3_bucket="scorecode-bench",
        argon2_time_cost=1,
        argon2_memory_kib=1024,
        rate_login_ip_per_minute=1000,
        api_session_burst=1000,
    )


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    os.environ["SCORECODE_MIGRATION_URL"] = url("scorecode_migrator", MIGRATOR_PW)
    here = Path(__file__).resolve().parent.parent
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "migrations"))
    command.upgrade(cfg, "head")


async def setup(infra, n_students: int, n_papers: int) -> tuple[str, uuid.UUID, uuid.UUID]:
    from app.modules.academics.models import AcademicSession, Cohort, Course, Program, Term
    from app.modules.audit.service import Actor
    from app.modules.directory.models import CohortMembership, Student
    from app.modules.entitlements.sync import sync_catalogue
    from app.modules.examinations.models import ExamCohort, Examination, ExamPaper, PaperSubmission
    from app.modules.grading.service import GradingService
    from app.modules.grading.templates import BY_KEY
    from app.modules.marks.models import MarkEntry
    from app.modules.tenancy.service import OwnerSpec, ProvisionRequest, provision_tenant

    await sync_catalogue(infra.db)
    await infra.storage.ensure_bucket()
    owner = "owner@bench.example.com"
    async with infra.db.uow() as uow:
        tenant = await provision_tenant(
            uow,
            ProvisionRequest(
                slug="bench",
                name="Benchmark Institute",
                type="university",
                plan_code="enterprise",
                owner=OwnerSpec(
                    email=owner, full_name="Owner", password_hash=await infra.passwords.hash(PASSWORD)
                ),
            ),
            Actor.system("benchmark"),
        )
    tid = tenant.id
    rng = random.Random(2026)  # noqa: S311 - synthetic data
    async with infra.db.uow(tid) as uow:
        s = uow.session
        sess = AcademicSession(
            tenant_id=tid,
            code="2025-26",
            name="2025-26",
            starts_on=date(2025, 7, 1),
            ends_on=date(2026, 6, 30),
            is_current=True,
        )
        prog = Program(tenant_id=tid, code="BE", name="B.E.")
        courses = [
            Course(tenant_id=tid, code=f"UCS3{i:02}", name=f"Course {i}", credits=Decimal(4))
            for i in range(n_papers)
        ]
        s.add_all([sess, prog, *courses])
        await uow.flush()
        term = Term(tenant_id=tid, session_id=sess.id, code="ODD", name="Odd", sequence=1)
        n_cohorts = max(1, n_students // 200)
        cohorts = [
            Cohort(tenant_id=tid, code=f"G{i:02}", name=f"Group {i}", program_id=prog.id, session_id=sess.id)
            for i in range(n_cohorts)
        ]
        s.add(term)
        s.add_all(cohorts)
        await uow.flush()
        scheme = await GradingService(infra).create(
            uow, None, name="Scale", description=None, config=BY_KEY["credit_10_point"].config
        )
        students = [
            {
                "id": uuid.uuid4(),
                "tenant_id": tid,
                "enrollment_no": f"1024{i:06}",
                "full_name": f"Student {i}",
                "status": "active",
            }
            for i in range(n_students)
        ]
        for chunk in range(0, len(students), 2000):
            await s.execute(insert(Student), students[chunk : chunk + 2000])
        sitting = {st["id"]: cohorts[i % n_cohorts].id for i, st in enumerate(students)}
        memberships = [
            {
                "tenant_id": tid,
                "cohort_id": cid,
                "student_id": sid,
                "session_id": sess.id,
                "program_id": prog.id,
            }
            for sid, cid in sitting.items()
        ]
        for chunk in range(0, len(memberships), 2000):
            await s.execute(insert(CohortMembership), memberships[chunk : chunk + 2000])
        exam = Examination(
            tenant_id=tid,
            term_id=term.id,
            name="Semester exam",
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
            for sid, cid in sitting.items():
                absent = rng.random() < 0.05
                a, b = rng.randint(10, 40), rng.randint(15, 60)
                marks.append(
                    {
                        "tenant_id": tid,
                        "exam_id": exam.id,
                        "exam_paper_id": p.id,
                        "cohort_id": cid,
                        "student_id": sid,
                        "components": {} if absent else {"INT": str(a), "EXT": str(b)},
                        "total": None if absent else Decimal(a + b),
                        "attendance": "absent" if absent else "present",
                    }
                )
        for chunk in range(0, len(marks), 2000):
            await s.execute(insert(MarkEntry), marks[chunk : chunk + 2000])
    return owner, tid, exam.id


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=8000)
    parser.add_argument("--papers", type=int, default=6)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    await admin(f'CREATE DATABASE "{DB}"')
    infra = None
    try:
        await asyncio.to_thread(migrate)  # alembic's env.py runs its own event loop
        from app.core.container import Infra
        from app.core.jobs import Worker
        from app.jobs_registry import load_job_handlers
        from app.main import create_app
        from app.modules.examinations.models import Examination
        from app.modules.results.compute import anomalies, compute, input_hash
        from app.modules.results.compute import statistics as statistics_
        from app.modules.results.models import ResultRun
        from app.modules.results.service import ResultsService

        load_job_handlers()
        cfg = settings()
        infra = Infra.build(cfg, app_name="scorecode-bench")
        app = create_app(cfg, infra)
        await infra.cache.redis.flushdb()  # db 14 is the benchmark's own; drop host lookups from earlier runs
        t_setup = time.perf_counter()
        owner, tid, exam_id = await setup(infra, args.students, args.papers)
        setup_s = time.perf_counter() - t_setup
        worker = Worker(infra, ["processing"])
        base = f"/api/v1/admin/exams/{exam_id}/results"
        transport = httpx.ASGITransport(app=app, client=("10.9.9.9", 1234))
        process: list[float] = []
        request: list[float] = []
        async with httpx.AsyncClient(
            transport=transport, base_url="http://bench.localhost", timeout=600
        ) as c:
            await c.get("/api/v1/auth/csrf")
            csrf = c.cookies.get("sc_csrf") or ""
            r = await c.post(
                "/api/v1/auth/login",
                json={"login_id": owner, "password": PASSWORD},
                headers={"X-CSRF-Token": csrf},
            )
            if r.status_code != 200:
                raise SystemExit(f"login failed: {r.status_code} {r.text}")
            hashes = set()
            for _ in range(args.runs):
                t0 = time.perf_counter()
                r = await c.post(
                    f"{base}/process",
                    json={},
                    headers={"X-CSRF-Token": csrf, "Idempotency-Key": uuid.uuid4().hex},
                )
                if r.status_code != 202:
                    raise SystemExit(f"process refused: {r.status_code} {r.text}")
                t1 = time.perf_counter()
                await worker.drain()
                t2 = time.perf_counter()
                run = (await c.get(base)).json()["run"]
                if run["status"] != "completed":
                    raise SystemExit(f"run {run['revision']} ended {run['status']}: {run['error_detail']}")
                hashes.add(run["content_hash"])
                request.append(t1 - t0)
                process.append(t2 - t0)

            # The job's phases on their own (read-only).
            phases: dict[str, list[float]] = {
                "load": [],
                "compute": [],
                "hash": [],
                "statistics + anomalies": [],
                "write rows (rolled back)": [],
            }
            for _ in range(args.runs):
                async with infra.db.uow(tid) as uow:
                    exam = (
                        await uow.session.scalars(select(Examination).where(Examination.id == exam_id))
                    ).one()
                    version = (
                        await uow.session.scalars(
                            select(ResultRun.grading_scheme_version_id)
                            .where(ResultRun.exam_id == exam_id)
                            .limit(1)
                        )
                    ).one()
                    a = time.perf_counter()
                    inputs = await ResultsService(infra).load_inputs(uow, exam, version)
                    b = time.perf_counter()
                    computed = compute(inputs)
                    d = time.perf_counter()
                    input_hash(inputs)
                    e = time.perf_counter()
                    statistics_(computed, inputs.papers)
                    anomalies(computed, inputs.papers, previous=None)
                    f = time.perf_counter()
                phases["load"].append(b - a)
                phases["compute"].append(d - b)
                phases["hash"].append(e - d)
                phases["statistics + anomalies"].append(f - e)
                try:
                    async with infra.db.uow(tid) as uow:
                        scratch = ResultRun(
                            tenant_id=tid,
                            exam_id=exam_id,
                            revision=999,
                            status="running",
                            grading_scheme_version_id=version,
                        )
                        uow.session.add(scratch)
                        await uow.flush()
                        g = time.perf_counter()
                        await ResultsService._write(uow, scratch, computed)
                        await uow.flush()
                        phases["write rows (rolled back)"].append(time.perf_counter() - g)
                        raise RollBack
                except RollBack:
                    pass

            t0 = time.perf_counter()
            r = await c.post(f"{base}/approve", json={"run_id": run["id"]}, headers={"X-CSRF-Token": csrf})
            approve_s = time.perf_counter() - t0
            if r.status_code != 200:
                raise SystemExit(f"approve failed: {r.status_code} {r.text}")
        async with infra.db.uow(tid) as uow:
            rows = (
                await uow.session.execute(text("SELECT count(*) FROM student_paper_results"))
            ).scalar_one()

        def row(name: str, vals: list[float]) -> str:
            return f"| {name} | {statistics.median(vals):.2f} | {min(vals):.2f} | {max(vals):.2f} |"

        print(
            f"machine: {platform.machine()} {platform.platform()} cpus={os.cpu_count()} python={platform.python_version()}"
        )
        print(
            f"students: {args.students:,}; papers: {args.papers}; marks: {args.students * args.papers:,}; "
            f"runs: {args.runs}; setup {setup_s:.1f} s; identical content hash across runs: {len(hashes) == 1}; "
            f"paper rows written in all: {rows:,}; students in last run: {len(computed.outcomes):,}"
        )
        print("| stage | median s | min s | max s |")
        print("|---|---|---|---|")
        print(row("process: request (POST)", request))
        print(row("**process: request + job**", process))
        for k, v in phases.items():
            print(row(f"phase: {k}", v))
        print(f"| approve (POST, single run) | {approve_s:.2f} | – | – |")
    finally:
        if infra is not None:
            await infra.close()  # app and platform connections must go before the scratch database can
        await admin(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')


if __name__ == "__main__":
    asyncio.run(main())
