# Scenarios A and B on a GitHub runner — pre-authenticated and cold (P14.1) — 2026-10-08

The full scenario runs, on hardware that is the same every time and has no battery (the laptop's
results depended on its power state: 2026-10-08-k6-scenarios-A-B.md). Raw data: the artifacts of
`perf.yml` runs **37737458557** and **37737494369**, kept 30 days. The numbers below were computed from
the artifacts' k6 summaries and `docker stats` samples.

## Environment
- **Code:** commit 1e3b76b, before the P14.3 optimisations (2026-10-09-read-path.md).
- **Machine:**
  - Run 37737458557: GitHub-hosted `ubuntu-24.04`, 4 vCPU Intel Xeon Platinum 8370C, 16 GB.
  - Run 37737494369 (two API containers) landed on an AMD EPYC 7763, also 4 vCPU and 16 GB. That
    is a different CPU, so it can't be compared like for like (below).
- **Topology:** `compose.yml` stack with Caddy, API containers with 2 Uvicorn workers each, the worker,
  PostgreSQL 16, Redis 7 and SeaweedFS.
  - **k6 runs on the same machine**, so the results are pessimistic: the load generator takes CPU from
    the system under test. Its own CPU isn't in the samples below.
- **Config:**
  - DB pool: 10 + 5 overflow per process, 5 s timeout.
  - Argon2id: t=2, m=19 MiB, at most 4 concurrent hashes per process.
  - Sessions: Redis with a 10 s in-process tier.
- **Data:** `loadtest_data.py`: 8,000 students and one published six-paper exam, plus 1,000 pre-created
  sessions.
  - Publication's background work (8,000 marksheets and 8,000 notifications) finished before any load:
    1,090 s.
  - `pg_stat_statements` was reset after it.
- **Scenarios (`benchmarks/k6/student-journey.js`):**
  - **A:** 100 virtual users. Ramp for 1 min, hold for 5 min.
  - **B:** 1,000 virtual users. 0 to 1,000 in 60 s, hold for 5 min.
  - **Journey:** config → me → latest → stats, plus history 30% of the time, then 2–10 s of think time.
  - **Pre-authenticated:** a session cookie per user.
  - **Cold:** a real sign-in (CSRF, then login with Argon2id) before the first journey.

## Results — 1 API container × 2 workers (run 37737458557)
| Run | Requests | req/s | Failed | config p50 / p95 / p99 | latest p50 / p95 / p99 | login p50 / p95 / p99 |
|---|---|---|---|---|---|---|
| A preauth 1 | 23,890 | 64.7 | 0.00% | 3.9 / 9.2 / 13.4 ms | 6.0 / 10.0 / 13.5 ms | — |
| A preauth 2 | 23,845 | 64.6 | 0.00% | 3.9 / 9.1 / 12.4 ms | 6.1 / 10.1 / 14.0 ms | — |
| A preauth 3 | 23,987 | 64.9 | 0.00% | 3.9 / 9.3 / 13.9 ms | 6.2 / 10.5 / 14.0 ms | — |
| A cold 1 | 23,938 | 64.9 | 0.00% | 3.9 / 8.6 / 12.2 ms | 6.1 / 9.8 / 12.6 ms | 34.7 / 42.3 / 55.5 ms |
| B preauth 1 | 124,639 | 333.9 | 2.55% | 1,184 / 4,770 / 5,156 ms | 1,143 / 4,467 / 5,033 ms | — |
| B preauth 2 | 131,721 | 353.0 | 1.64% | 1,104 / 3,946 / 5,046 ms | 1,048 / 3,767 / 5,027 ms | — |
| B preauth 3 | 133,657 | 358.5 | 1.31% | 1,050 / 3,902 / 5,035 ms | 1,009 / 3,552 / 5,023 ms | — |
| B cold 1 | 133,707 | 358.7 | 2.10% | 1,078 / 3,867 / 5,039 ms | 1,023 / 3,653 / 5,025 ms | 210 / 2,974 / 5,071 ms |

- **Medians:**
  - A pre-authenticated: **64.7 req/s**, every endpoint p95 ≤ 13.2 ms, p99 ≤ 16.6 ms, 0 errors. That is
    the offered load: think time limits it, not the system.
  - B pre-authenticated: **353 req/s**, p95 3.9 s, 1.64% failed.
- `me`, `stats` and `history` track `config` and `latest` within about 10%. Every run's per-endpoint
  numbers are in its `.txt` summary.

## Resources (median of 5-second `docker stats` samples during each run)
| Run | API | PostgreSQL | Caddy | Redis | API memory |
|---|---|---|---|---|---|
| A preauth (3 runs) | 29–30% | 8–9% | 4–5% | 1–3% | 308 MiB |
| A cold | 33% | 9% | 4% | 3% | 424 MiB |
| B preauth (3 runs) | **192–196%** (max 227%) | 51–55% | 19–20% | 4% | 348 MiB |
| B cold | **195%** (max 248%) | 53% | 20% | 4% | 790 MiB |

100% is one vCPU, so the API's 2 workers can use at most 200%.

## Analysis
- **Scenario B is limited by API CPU:** the 2 worker processes run at about 97% each.
  - PostgreSQL has room (about 50% of one vCPU), Redis is idle, and the proxy is at 20%.
  - The profile of that CPU and what was done about it are in 2026-10-09-read-path.md (P14.2/P14.3).
- **The failures are pool timeouts:** a 503 `overloaded` after waiting 5 s for a database connection.
  - Every endpoint's p99 sits at 5.02–5.16 s, exactly the pool timeout.
  - The chaos runs on the same setup logged those 503s in the API's request log
    (2026-10-08-failure-under-load.md).
  - The connections weren't busy in the database (index lookups under 1 ms, `explain.txt`). Requests
    held them while waiting for a saturated event loop.
- **Cold sign-in adds little:** 1,000 Argon2id logins spread over the ramp. Login p50 is 210 ms; p95 is
  2.97 s, because logins queue behind the same saturated workers.
- **Scenario A** (100 users) is far below capacity everywhere.

## Two API containers (run 37737494369, AMD EPYC 7763)
| Run | Requests | req/s | Failed | API containers | PostgreSQL |
|---|---|---|---|---|---|
| B preauth 1–3 | 142,724–143,293 | 382.7–384.8 | 0.42–0.43% | 125% + 124–129% | 71–74% |
| B cold 1 | 143,486 | 385.2 | 0.81% | 127% + 125% | 69% |

- **Caddy splits load evenly** (`least_conn`): the two containers' CPU is within 10%.
- **Not comparable with the single-container run.** It's a different CPU model, and the machine itself
  is now the limit:
  - 4 API processes at about 62% each, plus PostgreSQL at 70%, Caddy at 23% and k6, on 4 vCPUs.
  - Throughput rose 9% (353 to 384 req/s) and failures fell from 1.6% to 0.4%, but how much of that
    is the second container and how much the faster CPU can't be told apart.
- **The same-machine comparison is P14.4:** `perf.yml` `compare=replicas`, both variants on one runner.

## What this does not show
- **Capacity on production hardware.** One 4-vCPU machine hosts everything, load generator included.
- **The effect of the P14.3 changes.** These runs predate them. `perf.yml` `compare=ref:1e3b76b` measures
  1e3b76b against the optimised code on one runner.
