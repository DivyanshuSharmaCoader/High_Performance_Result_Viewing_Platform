"""Time marksheet PDF rendering (P11.2: "timing measured per PDF").

Runs where WeasyPrint has its libraries, i.e. the Docker image:

    docker build --target test -t scorecode-test backend
    docker run --rm scorecode-test python scripts/measure_marksheets.py --count 200 --papers 6

Renders ``--count`` marksheets from synthetic snapshots (deterministic seed), one after another on one
thread, the way one ``pdf`` worker job does. It reports the time per PDF (after one warm-up render, which
loads fonts) and the file sizes. Storage and database time aren't included: this measures layout cost only.
"""

from __future__ import annotations

import argparse
import platform
import random
import statistics
import time
from datetime import UTC, datetime
from typing import Any

from app.modules.documents.render import Branding, render_marksheet
from app.modules.verification.codes import grouped, new_code

FIRST = ["Aarav", "Priya", "Ishaan", "Ananya", "Kabir", "Meera", "Rohan", "Saanvi", "Vihaan", "Diya"]
LAST = ["Sharma", "Gupta", "Singh", "Iyer", "Reddy", "Khan", "Das", "Mehta", "Nair", "Banerjee"]


def payload(rng: random.Random, i: int, papers: int) -> dict[str, Any]:
    rows = []
    for p in range(papers):
        internal, external = rng.randint(10, 40), rng.randint(15, 60)
        total = internal + external
        rows.append(
            {
                "course_code": f"UCS{301 + p}",
                "course_name": f"Course number {p + 1} with a realistic name",
                "credits": "4",
                "attendance": "present",
                "outcome": "pass" if external >= 21 else "fail",
                "total": str(total),
                "max_total": "100",
                "percentage": str(total),
                "grade": "A" if total >= 80 else "B" if total >= 60 else "C",
                "grade_point": "8",
                "failed_components": [],
                "missing_components": [],
                "components": [
                    {"code": "INT", "label": "Internal", "max": "40", "marks": str(internal)},
                    {"code": "EXT", "label": "External", "max": "60", "marks": str(external)},
                ],
            }
        )
    return {
        "schema": 1,
        "institution": {"name": "Load Test University Trust", "display_name": "Load Test University"},
        "exam": {"name": "End semester examination", "kind": "semester", "term": "Odd", "session": "2025-26"},
        "scheme": {"name": "10-point", "strategy": "credit_points"},
        "student": {
            "enrollment_no": f"LT{i:06}",
            "full_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            "cohort": {"code": f"C{i % 40:02}", "name": f"Section {i % 40}"},
            "program": "B.Tech.",
        },
        "result": {
            "outcome": "pass",
            "total": "450",
            "max_total": str(papers * 100),
            "percentage": "75",
            "grade": None,
            "grade_point": None,
            "sgpa": "8.12",
            "credits_attempted": str(papers * 4),
            "credits_earned": str(papers * 4),
            "rank": None,
            "notes": [],
        },
        "papers": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--papers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument(
        "--processes", type=int, default=0, help="also time the same PDFs through a pool of N processes"
    )
    args = parser.parse_args()
    rng = random.Random(args.seed)  # noqa: S311 - synthetic data
    branding = Branding(color="#8b1a1a", address="Patiala, Punjab", footer_text="Controller of Examinations")
    issued = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)

    def one(i: int) -> tuple[float, int]:
        code = new_code()
        started = time.perf_counter()
        result = render_marksheet(
            payload(rng, i, args.papers),
            branding=branding,
            verify_url=f"https://verify.scorecode.in/v/{code}",
            code_display=grouped(code),
            version=1,
            issued_at=issued,
            timezone="Asia/Kolkata",
        )
        return time.perf_counter() - started, len(result.pdf)

    warm_s, _ = one(0)
    times, sizes = [], []
    wall = time.perf_counter()
    for i in range(1, args.count + 1):
        t, size = one(i)
        times.append(t * 1000)
        sizes.append(size)
    wall = time.perf_counter() - wall
    q = statistics.quantiles(times, n=100)
    print(
        f"python {platform.python_version()} on {platform.machine()} · {args.count} PDFs × {args.papers} papers"
    )
    print(f"first render (fonts load): {warm_s * 1000:.0f} ms")
    print(
        f"per PDF: mean {statistics.mean(times):.0f} ms · p50 {q[49]:.0f} ms · p95 {q[94]:.0f} ms · "
        f"max {max(times):.0f} ms"
    )
    print(f"throughput: {args.count / wall:.1f} PDFs/s on one thread")
    print(f"size: mean {statistics.mean(sizes) / 1024:.1f} KiB · max {max(sizes) / 1024:.1f} KiB")
    if args.processes:
        from functools import partial

        from app.modules.documents.pool import pool, shutdown

        executor = pool(args.processes)
        jobs = []
        for i in range(args.count):
            code = new_code()
            jobs.append(
                partial(
                    render_marksheet,
                    payload(rng, i, args.papers),
                    branding=branding,
                    verify_url=f"https://verify.scorecode.in/v/{code}",
                    code_display=grouped(code),
                    version=1,
                    issued_at=issued,
                    timezone="Asia/Kolkata",
                )
            )
        for f in [executor.submit(j) for j in jobs[: args.processes]]:  # warm every process (fonts)
            f.result()
        started = time.perf_counter()
        for f in [executor.submit(j) for j in jobs]:
            f.result()
        pooled = time.perf_counter() - started
        shutdown()
        print(
            f"pool of {args.processes} processes: {args.count / pooled:.1f} PDFs/s "
            f"({args.count / pooled / (args.count / wall):.2f}× one thread)"
        )


if __name__ == "__main__":
    main()
