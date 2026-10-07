# PT-6 — result processing, 8,000 students × 6 papers — developer laptop — 2026-10-07

Measured for P9.5. Target ([docs/05](../../docs/05-system-design.md) PT-6, SRS NFR-6): **processing 8,000 students × 6 papers in under 2 minutes**. This is a laptop baseline, not production.

## Environment
- Git commit: `65d0caa` (script `backend/scripts/measure_processing.py`)
- Machine: Apple M2, 8 cores, 16 GB, macOS 15.3. **Python 3.12.13 is an x86_64 build running under Rosetta 2**, so the application-side numbers (compute especially) are pessimistic compared with native arm64 or a server x86 CPU.
- Services: Postgres 16 (`scorecode/postgres:16`), Redis 7, SeaweedFS S3, in Docker Desktop 29.1.3 (Linux VM with 8 CPUs, 7.65 GiB), reached through Docker's port forwarding.
- Application: the API and the job worker run **in one process** with the benchmark (httpx ASGI transport, no Uvicorn). Postgres is real, with forced RLS as in production.
- Dataset: a scratch database with one tenant and 8,000 active students in 40 cohorts of 200. One closed exam has six papers, each Internal /40 + External /60 (minimum 21), 4 credits, graded with the 10-point credit scheme. Every student has a mark row for every paper: 48,000 marks, about 5% absent, all papers submitted. Data is synthetic with a fixed seed.

## What was measured
- **process: request + job**: `POST …/results/process` plus the `results.process` job. The job loads the inputs, computes every result, writes 8,000 exam rows and 48,000 paper rows, computes both hashes, statistics and anomalies, and moves the exam to *processed*. Each run is a new revision, so each run writes the full set of rows.
- **Phases**, measured separately and read-only: load the inputs (4 queries), compute (pure engine), input hash, statistics and anomalies. The row write is timed inside a transaction that is rolled back.
- **approve**: `POST …/results/approve`. It reloads every input and recomputes the input hash inside the request, before recording the approval.

## Results (3 runs; median, with min–max)
| Stage | Median | Range |
|---|---|---|
| process: request (POST) | 0.04 s | 0.04–0.24 |
| **process: request + job** | **9.59 s** | 9.52–9.61 |
| phase: load inputs | 0.78 s | 0.70–0.93 |
| phase: compute | 2.62 s | 2.35–2.62 |
| phase: input hash | 0.24 s | 0.24–0.40 |
| phase: statistics + anomalies | 0.14 s | 0.13–0.14 |
| phase: write 56,000 rows | 5.50 s | 5.46–5.58 |
| approve (one request) | 1.16 s | – |

All three runs produced the same content hash, so the output was identical at this scale too (determinism, P9.2).

### Before the write change (same machine, same script, commit `86b5332` code)
| Stage | Median |
|---|---|
| process: request + job | 18.44 s |
| phase: write 56,000 rows | 14.16 s |

## Analysis
- **PT-6 is met** with about 12× headroom on this machine: 9.6 s against a 120 s target.
- **The row write was the bottleneck**: 77% of the job, at about 4,000 rows/s, with ORM-entity bulk inserts. Switching to Core inserts on the tables (`65d0caa`) halved the job time; these rows are never loaded back into the session. `COPY` would be faster again, but Postgres refuses `COPY FROM` on tables with row-level security, and these tables have forced RLS.
- Compute (2.6 s) runs in a worker thread under Rosetta. A native or server CPU should be faster; that hasn't been measured.
- Approval takes 1.2 s because it reloads and re-hashes every input as a deliberate safety check (docs/08 §7.1). That is acceptable for a once-per-exam action, but it is the slowest *request* measured so far.
- What this does **not** show:
  - concurrent processing of several exams;
  - a worker in a separate process or container;
  - larger tenants;
  - production hardware;
  - the anomaly comparison against a previous run with many changes (in these runs nothing changed between revisions).

## Next action
Re-run on the demo/production VM (Phase 16). If approval latency matters at larger sizes, compare stored per-row mark versions instead of recomputing the hash. Stale runs' rows accumulate (56,000 per revision); a retention job should purge rows of superseded runs (tracked for Phase 16).
