# Failures under load (P14.5) — 2026-10-08

docs/15 §6 asks what happens when a dependency fails during scenario B. These are three runs of
`perf.yml` with the `chaos` input, raw data in [2026-10-08-chaos/](2026-10-08-chaos/).

## Environment
- **Commit:** c9f90f2. It includes the retryable 503 for database outages and the marksheet process pool
  (2 processes per worker).
- **Machine:** a GitHub-hosted runner (ubuntu-24.04, 4 vCPU AMD EPYC 7763, 16 GB). The whole stack and
  the k6 load generator share it, co-located like the laptop runs.
- **Stack:** 1 API container with 2 Uvicorn workers, 1 worker container, PostgreSQL 16, Redis 7, Caddy.
- **Data:** 8,000 students and one six-paper exam, published, from `backend/scripts/loadtest_data.py`.
- **Load:** scenario B pre-authenticated, 1,000 VUs (0 → 1,000 in 60 s, hold 5 min).
- **Injection:** 150 s into the run, i.e. 90 s into the hold.

**Read this first:** on this 4-vCPU runner, scenario B saturates the API *before* anything is broken.
About 300–350 req/s, p95 3.6–5 s, and 503 `overloaded` answers in every 10-second window. So the
question each run answers is **what changed when the failure hit**, by comparing windows of the API's own
request log (`timeline.txt`), not how fast scenario B is. Speed is P14.1's question.

## Results

### Redis stopped for 60 s (`redis-stop-60s/`)
| Window (UTC) | Requests | 200 | 503 |
|---|---|---|---|
| 06:56:50 (before) | 3,033 | 2,769 | 264 |
| **06:57:10 (stopped)** | 3,030 | 2,880 | 150 |
| 06:57:40 (stopped) | 3,042 | 2,843 | 199 |
| 06:58:10 (restarted) | 3,092 | 2,875 | 217 |
| 06:58:50 (after) | 3,544 | 3,447 | 97 |

- Throughput didn't change while Redis was down, and there were no 500s.
- Sessions, tenant config and entitlements fell back to the in-process cache and the database (circuit
  breaker). Rate limiting fell back to per-process buckets.
- Run total: 5.41% of requests failed. On this machine the share was as high *before* the injection, as
  the table shows: it's saturation, not Redis. This runner instance was busier than the other two (264
  503s per window before injection, against about 60–90 elsewhere), which shows how much runners vary.
- **Pass** (docs/15 §6: reads succeed; the rate limiter degrades to local).

### PostgreSQL restarted (`postgres-restart/`)
| Window (UTC) | Requests | 200 | 503 |
|---|---|---|---|
| 06:57:00 (before) | 3,682 | 3,633 | 49 |
| **06:57:10 (restart, about 1 s)** | 3,390 | 3,118 | **272** |
| 06:57:20 (after) | 3,686 | 3,594 | 92 |
| 06:57:30 (after) | 3,709 | 3,641 | 68 |

- During the restart about 200 more requests than usual got **503 `service-unavailable` with
  `Retry-After: 5`**. There were no 500s and no hangs. Service was back in the next window on its own:
  the pool's pre-ping replaces dead connections.
- Before c9f90f2 the same outage answered **500 `internal-error`**, found by stopping Postgres on the
  local stack. That's fixed and tested (`test_outages.py`).
- **Pass** (quick 503s, automatic recovery).

### Worker killed with SIGKILL while 8,000 marksheets rendered (`worker-kill/`)
- Killed 30 s after the data load; restarted 15 s later.
- Afterwards: **8,000 marksheet files for 8,000 rendered marksheets, 0 duplicate notifications**, and every
  `documents.render` job (160) and the notification fan-out succeeded. The lease reaper re-queued the
  killed worker's jobs, and documents already rendered were skipped.
- Background work took 1,322 s, against about 1,225 s in the runs without the kill.
- **Pass** (re-run by the next worker; final state identical; no duplicates).

## Also measured here: publication's background work on this runner
With 2 PDF processes per worker, 8,000 marksheets plus the notification fan-out finished in **1,224–1,225 s
(about 20.4 min)**, measured twice. The marksheet render span (first created to last rendered) was
1,226–1,233 s. That's the end-to-end number single-PDF timings can't give (storage, database and
contention included). Scaling it up is a P14.3 question (more processes per worker, or more workers).

## What this does not show
- Network latency or loss to the database (Toxiproxy), and object-store outages: not run, still open in
  docs/15 §6.
- A database *failover* (new primary) rather than a restart of the same one: needs a managed database
  (Phase 16).
