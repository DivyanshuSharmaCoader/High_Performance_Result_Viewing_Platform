"""Measure the marks-import pipeline on a 10,000-row file (P8.7, docs/13 §6, PT-5).

Usage (needs `make up`): uv run python scripts/measure_import.py [--rows 10000] [--runs 3]

Creates a scratch database, a tenant with ``--rows`` students in 20 cohorts and one exam per run, then for
CSV and XLSX files times each stage as the product runs it, in-process (no network hop):

* upload  — POST /api/v1/admin/imports (validation, sha256, object storage, job enqueue)
* check   — the imports.analyse job: parse, map, validate every row, stage rows in import_rows
* commit  — the imports.commit job: one transaction writing mark_entries

The scratch database is dropped afterwards. Numbers depend on the machine; record them with its details.
"""

from __future__ import annotations

import argparse
import asyncio
import io
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
from openpyxl import Workbook
from sqlalchemy import insert

from app.core.config import Environment, Settings

PG = ("localhost", 55432)
DB = f"scorecode_bench_{uuid.uuid4().hex[:6]}"
MIGRATOR_PW = "migrator-dev-pw"  # the local docker-compose role, as in tests/conftest.py
PASSWORD = uuid.uuid4().hex  # the scratch tenant owner; never stored


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
        max_import_rows=100_000,
    )


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    os.environ["SCORECODE_MIGRATION_URL"] = url("scorecode_migrator", MIGRATOR_PW)
    here = Path(__file__).resolve().parent.parent
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "migrations"))
    command.upgrade(cfg, "head")


async def setup(
    infra, n_students: int, n_exams: int
) -> tuple[str, uuid.UUID, list[tuple[uuid.UUID, uuid.UUID]]]:
    from app.modules.academics.models import AcademicSession, Cohort, Course, Program, Term
    from app.modules.audit.service import Actor
    from app.modules.directory.models import CohortMembership, Student
    from app.modules.entitlements.sync import sync_catalogue
    from app.modules.examinations.models import ExamCohort, Examination, ExamPaper, PaperSubmission
    from app.modules.grading.service import GradingService
    from app.modules.grading.templates import BY_KEY
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
    exams: list[tuple[uuid.UUID, uuid.UUID]] = []
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
        course = Course(tenant_id=tid, code="UCS301", name="Data Structures", credits=Decimal(4))
        s.add_all([sess, prog, course])
        await uow.flush()
        term = Term(tenant_id=tid, session_id=sess.id, code="ODD", name="Odd", sequence=1)
        cohorts = [
            Cohort(tenant_id=tid, code=f"G{i:02}", name=f"Group {i}", program_id=prog.id, session_id=sess.id)
            for i in range(20)
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
        memberships = [
            {
                "tenant_id": tid,
                "cohort_id": cohorts[i % 20].id,
                "student_id": st["id"],
                "session_id": sess.id,
                "program_id": prog.id,
            }
            for i, st in enumerate(students)
        ]
        for chunk in range(0, len(memberships), 2000):
            await s.execute(insert(CohortMembership), memberships[chunk : chunk + 2000])
        for e in range(n_exams):
            exam = Examination(
                tenant_id=tid,
                term_id=term.id,
                name=f"Exam {e}",
                status="marks_entry_open",
                grading_scheme_id=scheme.id,
            )
            s.add(exam)
            await uow.flush()
            s.add_all(ExamCohort(tenant_id=tid, exam_id=exam.id, cohort_id=c.id) for c in cohorts)
            paper = ExamPaper(
                tenant_id=tid,
                exam_id=exam.id,
                course_id=course.id,
                components=[
                    {"code": "INT", "label": "Internal", "max": "40", "min_pass": None},
                    {"code": "EXT", "label": "External", "max": "60", "min_pass": "21"},
                ],
                max_total=Decimal(100),
            )
            s.add(paper)
            await uow.flush()
            s.add_all(
                PaperSubmission(tenant_id=tid, exam_id=exam.id, exam_paper_id=paper.id, cohort_id=c.id)
                for c in cohorts
            )
            exams.append((exam.id, paper.id))
    return owner, tid, exams


def files(n: int, seed: int) -> dict[str, bytes]:
    rng = random.Random(seed)  # noqa: S311 - synthetic data
    rows = [(f"1024{i:06}", f"Student {i}", rng.randint(0, 40), rng.randint(0, 60)) for i in range(n)]
    csv = (
        "Enrollment No,Name,Internal,External\n" + "".join(f"{e},{nm},{a},{b}\n" for e, nm, a, b in rows)
    ).encode()
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Marks")
    ws.append(["Enrollment No", "Name", "Internal", "External"])
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return {"csv": csv, "xlsx": buf.getvalue()}


async def run_once(
    app, infra, owner: str, exam: tuple[uuid.UUID, uuid.UUID], fmt: str, data: bytes
) -> dict[str, float]:
    from app.core.jobs import Worker

    worker = Worker(infra, ["imports"])
    transport = httpx.ASGITransport(app=app, client=("10.9.9.9", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://bench.localhost") as c:
        await c.get("/api/v1/auth/csrf")
        csrf = c.cookies.get("sc_csrf") or ""
        r = await c.post(
            "/api/v1/auth/login",
            json={"login_id": owner, "password": PASSWORD},
            headers={"X-CSRF-Token": csrf},
        )
        if r.status_code != 200:
            raise SystemExit(f"login failed: {r.status_code} {r.text}")
        mime = "text/csv" if fmt == "csv" else "application/octet-stream"
        t0 = time.perf_counter()
        r = await c.post(
            "/api/v1/admin/imports",
            files={"file": (f"marks.{fmt}", data, mime)},
            data={"kind": "marks", "exam_id": str(exam[0]), "paper_id": str(exam[1])},
            headers={"X-CSRF-Token": csrf},
        )
        r.raise_for_status()
        job_id = r.json()["id"]
        t1 = time.perf_counter()
        await worker.drain()
        t2 = time.perf_counter()
        job = (await c.get(f"/api/v1/admin/imports/{job_id}")).json()
        if job["status"] != "validated" or job["rows_error"]:
            raise SystemExit(f"check did not pass: {job['status']} {job['rows_error']} errors")
        r = await c.post(f"/api/v1/admin/imports/{job_id}/commit", json={}, headers={"X-CSRF-Token": csrf})
        r.raise_for_status()
        t3 = time.perf_counter()
        await worker.drain()
        t4 = time.perf_counter()
        done = (await c.get(f"/api/v1/admin/imports/{job_id}")).json()
        if done["status"] != "committed":
            raise SystemExit(f"commit failed: {done.get('error_detail')}")
        return {
            "upload": t1 - t0,
            "check": t2 - t1,
            "commit": (t4 - t3) + (t3 - t2),
            "rows": job["rows_total"],
        }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    await admin(f'CREATE DATABASE "{DB}"')
    infra = None
    try:
        await asyncio.to_thread(migrate)  # alembic's env.py runs its own event loop
        from app.core.container import Infra
        from app.jobs_registry import load_job_handlers
        from app.main import create_app

        load_job_handlers()
        cfg = settings()
        infra = Infra.build(cfg, app_name="scorecode-bench")
        app = create_app(cfg, infra)
        await infra.cache.redis.flushdb()  # db 14 is the benchmark's own; drop host lookups from earlier runs
        owner, _tid, exams = await setup(infra, args.rows, args.runs * 2)
        results: dict[str, list[dict[str, float]]] = {"csv": [], "xlsx": []}
        i = 0
        for run in range(args.runs):
            data = files(args.rows, seed=run)
            for fmt in ("csv", "xlsx"):
                results[fmt].append(await run_once(app, infra, owner, exams[i], fmt, data[fmt]))
                i += 1
        print(
            f"machine: {platform.machine()} {platform.platform()} cpus={os.cpu_count()} python={platform.python_version()}"
        )
        print(
            f"rows per file: {args.rows:,}; runs per format: {args.runs}; file sizes: csv {len(files(args.rows, 0)['csv']):,} B"
        )
        print("| format | stage | median s | min s | max s |")
        print("|---|---|---|---|---|")
        for fmt, runs in results.items():
            for stage in ("upload", "check", "commit"):
                vals = [r[stage] for r in runs]
                print(
                    f"| {fmt} | {stage} | {statistics.median(vals):.2f} | {min(vals):.2f} | {max(vals):.2f} |"
                )
            totals = [r["upload"] + r["check"] + r["commit"] for r in runs]
            print(
                f"| {fmt} | **total** | **{statistics.median(totals):.2f}** | {min(totals):.2f} | {max(totals):.2f} |"
            )
    finally:
        if infra is not None:
            await infra.close()  # app and platform connections must go before the scratch database can
        await admin(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')


if __name__ == "__main__":
    asyncio.run(main())
