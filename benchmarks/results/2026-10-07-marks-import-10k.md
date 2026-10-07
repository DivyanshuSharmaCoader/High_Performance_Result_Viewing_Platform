# PT-5 — marks import, 10,000 rows — developer laptop — 2026-10-07

Measured for P8.7. Target ([docs/05](../../docs/05-system-design.md) PT-5): **a validated report for a 10,000-row marks file in < 60 s**. This is a laptop baseline, not production.

## Environment
- Git commit: `fd6f172` (script `backend/scripts/measure_import.py`)
- Machine: Apple M2, 8 cores, 16 GB, macOS 15.3. **Python 3.12.13 is an x86_64 build running under Rosetta 2**, so the application-side numbers are pessimistic compared with native arm64 or a server x86 CPU.
- Services: Postgres 16 (`scorecode/postgres:16`), Redis 7, SeaweedFS S3, in Docker Desktop 29.1.3 (Linux VM with 8 CPUs, 7.65 GiB), reached through Docker's port forwarding.
- Application: the FastAPI app and the job worker run **in one process** with the benchmark (httpx ASGI transport, no Uvicorn and no network hop to the API). Postgres, Redis and object storage are real, as in production.
- Libraries: openpyxl 3.1.5, SQLAlchemy 2.1.3, asyncpg 0.31.0.
- Dataset: a scratch database with one tenant, 10,000 active students in 20 cohorts. Each run gets a fresh exam with one paper (two components: Internal /40, External /60 with a minimum of 21), so every commit creates 10,000 new mark entries.
- Files: synthetic (seeded), single-paper layout (`Enrollment No, Name, Internal, External`), every row valid. CSV 294,831 B; XLSX 229,817 B.

## Stages (as the product runs them)
- **upload**: `POST /api/v1/admin/imports`, which covers the size and type checks, sha256, the object-storage write and the job enqueue.
- **check**: the `imports.analyse` job, which parses and maps the file, validates every row against the exam context and stages the rows in `import_rows`. When it finishes, the validated report is available. **This is the PT-5 measurement.**
- **commit**: `POST …/commit` plus the `imports.commit` job, which writes `mark_entries` in one transaction (with version checks and an audit entry).

## Results (3 runs per format; median, with min–max)
| Format | Upload | Check (PT-5) | Commit | Total |
|---|---|---|---|---|
| CSV | 0.08 s (0.07–0.21) | **1.59 s** (1.58–1.61) | 2.75 s (2.61–2.83) | 4.41 s (4.30–4.62) |
| XLSX | 0.05 s (0.05–0.06) | **2.69 s** (2.53–2.69) | 2.69 s (2.65–2.74) | 5.39 s (5.32–5.44) |

## Analysis
- **PT-5 is met with wide headroom on this machine**: the validated report is ready in 1.6 s (CSV) and 2.7 s (XLSX), against a 60 s target. XLSX checking costs about 1.1 s more than CSV, which is openpyxl's read-only parse.
- **The first attempt failed, and that led to a fix.** Committing 10,000 rows raised `stack depth limit exceeded`. Postgres expanded the commit's `(paper, student) IN ((…), …)` lock query into nested ORs. A similar plain `IN (…)` list in the students import would also have hit asyncpg's limit of 32,767 bind parameters on a 50,000-row file. The fix is in `fd6f172`: `app/core/sql.py` binds one array per column, and `tests/integration/test_sql_scale.py` covers 40,000 values and 20,000 pairs.
- What this measurement does **not** show:
  - the update path (a file overwriting existing marks);
  - long and wide multi-paper files;
  - concurrent imports;
  - a worker in a separate process;
  - production hardware.
- The check loads every student in the tenant once (docs/13 §6, set-based validation). That is cheap at 10,000 students, but the cost grows with the size of the tenant, not the size of the file.

## Next action
Re-run on the demo/production VM (Phase 16) and with a 50,000-student tenant (Phase 14). If tenant size dominates there, limit the student load to the enrolment numbers in the file, which `in_values` makes a single query.
