# Benchmarks

Methodology: [docs/11 §4](../docs/11-performance-architecture.md#4-benchmark-plan-scientifically-valid). **Nothing in this folder is a claim until a dated result file exists for it.**

## Running
`benchmarks/k6/run.sh <A|B|smoke> <preauth|cold> <n>` against `make stack` with data from
`backend/scripts/loadtest_data.py`. It samples `docker stats` every 5 s and refuses to run on battery power
(Low Power Mode cut this laptop's scenario-B throughput by 32–44%). Delete `data/loadtest-users.json` afterwards: it holds
sessions for the synthetic accounts.

## Layout (created during Phase 10/14)
```
benchmarks/
  k6/                  scenario scripts (A–D), shared journey module, run.sh
  data/                synthetic data generator config (deterministic seeds)
  results/             one Markdown file per run: YYYY-MM-DD-<scenario>-<variant>.md
```

## Result file template
Copy this into `results/YYYY-MM-DD-<scenario>-<variant>.md`:

```markdown
# <Scenario ID> — <pre-authenticated | cold-login> — <date>

## Environment
- Git commit: <sha>   · k6 script version: <sha/path>
- System under test: <provider/VM type, vCPU, RAM, disk>, region, OS, container limits
- Topology: <N api processes × M workers>, PgBouncer <yes/no>, Redis <yes/no>
- Load generator: <machine; same host or separate?>
- Config: DB pool size, Uvicorn workers, Argon2 params (t, m, p), cache settings
- Dataset: <tenants, students, publications> (generator seed)

## Scenario
- Virtual users, ramp profile, duration, think time, journey

## Results (median of N runs; spread in brackets)
| Endpoint | RPS | p50 | p95 | p99 | Errors (5xx) | 429s |
|---|---|---|---|---|---|---|

## Resources
CPU / memory per container · DB CPU · active connections · Redis hit rate · queue depth (attach graphs)

## Analysis
Bottleneck observed, evidence (EXPLAIN, profiles), what this does and does not show.

## Next action
```

## Results index
| Date | Scenario | Variant | Key result | File |
|---|---|---|---|---|
| 2026-10-06 | Dev-environment latency investigation | laptop + Docker Desktop | not a capacity benchmark; found & fixed a pool-deadlock bug; stalls traced to the VM | [results/2026-10-06-dev-environment-latency.md](results/2026-10-06-dev-environment-latency.md) |
| 2026-10-06 | Argon2id cost (P3.2) | laptop, Rosetta 2 | 33.1 ms p50 per verify; 98.5 verifications/s on 4 threads | [results/2026-10-06-argon2id-cost.md](results/2026-10-06-argon2id-cost.md) |
| 2026-10-07 | Marks import, 10,000 rows (PT-5, P8.7) | laptop, Rosetta 2, in-process API | validated report in 1.59 s (CSV) / 2.69 s (XLSX) vs < 60 s target; found & fixed an IN-list failure at 10k rows | [results/2026-10-07-marks-import-10k.md](results/2026-10-07-marks-import-10k.md) |
| 2026-10-07 | Result processing, 8,000 × 6 (PT-6, P9.5) | laptop, Rosetta 2, in-process API + worker | 9.59 s end to end vs < 2 min target (18.44 s before switching the row write to Core inserts); approval 1.16 s | [results/2026-10-07-result-processing-8000x6.md](results/2026-10-07-result-processing-8000x6.md) |
| 2026-10-08 | k6 scenarios A and B, pre-authenticated and cold (P10.6) | one M2 laptop, load generator co-located | A: p95 ≤ 11 ms, 0 errors; B pre-auth: about 600 req/s, p95 0.5–0.7 s, 0.016% errors, API CPU is the first limit; found and fixed a client-address bug (601/1,000 cold sign-ins got 429) and pool timeouts surfacing as 500; B-cold after the fix not yet re-run on AC | [results/2026-10-08-k6-scenarios-A-B.md](results/2026-10-08-k6-scenarios-A-B.md) |
| 2026-10-08 | Marksheet PDF render time (P11.2) | Docker image on M2 laptop (battery + Low Power Mode) and the GitHub CI runner | about 200 ms per six-paper PDF on one thread (laptop p50 172 ms; CI p50 202 ms, p95 292 ms); 8,000 students take about 25–28 min per worker process | [results/2026-10-08-marksheet-render.md](results/2026-10-08-marksheet-render.md) |
| 2026-10-08 | k6 scenarios A and B on a GitHub runner (P14.1) | 4 vCPU runner, co-located k6; 1 API container × 2 workers (and 2 containers, on a different CPU) | A p95 ≤ 13 ms, 0 errors; B about 353 req/s, p95 3.9 s, 1.6% failed (5 s pool timeouts); API CPU-bound at about 97% per worker; 2 containers split load evenly but the 4-vCPU machine becomes the limit | [results/2026-10-08-runner-scenarios.md](results/2026-10-08-runner-scenarios.md) |
| 2026-10-08 | Failures under load: Redis stopped, Postgres restarted, worker killed (P14.5) | GitHub runner, 4 vCPU, scenario B | no 500s; Redis down changed nothing visible; Postgres restart gave one 10 s window of retryable 503s and recovered on its own; worker kill gave exactly-once marksheets and notifications | [results/2026-10-08-failure-under-load.md](results/2026-10-08-failure-under-load.md) |
| 2026-10-09 | Student read path: profile and four fixes (P14.2, P14.3) | py-spy on the GitHub runner; before/after in-process on the M2 laptop (battery, back to back) | top costs: SQLAlchemy + asyncpg 38.7% of API CPU, transaction per request 5%, route matching 6.1%; read cache −20%, student routers first −5%, lazy transaction −14%, idle-only ping −3% CPU per request (about −35% together); SQL statements per request 1.24 → 0.49 | [results/2026-10-09-read-path.md](results/2026-10-09-read-path.md) |
