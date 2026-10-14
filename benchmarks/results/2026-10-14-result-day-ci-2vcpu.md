# Result day on a 2-vCPU machine, with marksheet downloads and a slow database — 2026-10-14

P18.11 rehearsal. It ran on a **GitHub-hosted runner, not the deployed VPS**, so P18.11 stays open until the
same workflow runs against the server. The runner is the same size as the production VPS (2 vCPUs,
8 GB RAM). **The load generator ran on the same 2 vCPUs as the system it was testing**, so these numbers
are pessimistic: k6 driving 1,000 virtual users takes CPU away from the API.

Workflow `perf.yml`, run 38527908688, inputs `runs: "B:cold:1 B:preauth:1"`, `chaos: dbslow`,
`profile: false`. Raw artifacts were downloaded from the run and are not committed (they contain the
synthetic dataset's session tokens).

## Environment
- **Code:** commit `97e1c2f`. k6 script `benchmarks/k6/student-journey.js` at that commit.
- **Machine** (`machine.txt`): 2 vCPUs, AMD EPYC 9V74, 7,938 MB RAM; Docker 28.0.4.
- **Topology:** the `compose.yml` stack, as in the [2026-10-08 report](2026-10-08-k6-scenarios-A-B.md):
  Caddy, then one API container with 2 Uvicorn workers; PostgreSQL 16; Redis; one worker container.
- **Dataset** (`backend/scripts/loadtest_data.py`): one institution with 8,000 students. One exam was
  published through the real services, so 8,000 marksheets were rendered. 1,000 sessions were made
  beforehand for the pre-authenticated run.
- **Load:** scenario B. 1,000 virtual users ramp up over 60 s, then hold for 5 min. Each journey is:
  config, me, latest result, class statistics, history (30%), then (50%) the signed marksheet link and
  the PDF itself. Each user thinks for 2–10 s between journeys.

## Before the load: publication's background work
Measured by the workflow before any load started (`background.txt`). The marksheets were all ready
before the first virtual user signed in, so rendering did not compete with the load below.

| What | Measured |
|---|---|
| 8,000 marksheet PDFs rendered | 8,000 rendered, 8,000 stored files; span from first job created to last render **1,426 s (23.8 min)**, about 5.6 PDFs a second on 2 vCPUs |
| All background work finished | 1,421 s after the data load ended |
| Notifications | 8,000, **0 duplicates** |
| Jobs | `documents.render` 160 succeeded (50 students each), `results.process` 1, `notifications.publication_live` 1; none failed |

## B-cold: every user signs in first (Argon2 path), with the slow database injected
157,568 requests · **422.3 req/s** · **6.11% failed** · 951 of 1,000 sign-ins succeeded.

| Endpoint (client side, k6) | p50 | p95 | p99 | max |
|---|---|---|---|---|
| login | 886 ms | 5,356 ms | 5,713 ms | 6,061 ms |
| tenant config | 666 ms | 2,225 ms | 6,202 ms | 11,716 ms |
| me | 1,120 ms | 5,779 ms | 6,460 ms | 14,704 ms |
| latest result | 439 ms | 1,353 ms | 5,352 ms | 11,496 ms |
| class statistics | 406 ms | 994 ms | 2,609 ms | 11,429 ms |
| history | 401 ms | 994 ms | 4,352 ms | 10,674 ms |
| marksheet link | 949 ms | 5,494 ms | 5,908 ms | 11,871 ms |
| marksheet PDF (from storage) | 2.3 ms | 8.7 ms | 30.5 ms | 263 ms |

## B-preauth: sessions made beforehand
165,392 requests · **442.2 req/s** · **3.28% failed**.

| Endpoint (client side) | p50 | p95 | p99 | max |
|---|---|---|---|---|
| tenant config | 620 ms | 1,506 ms | 5,185 ms | 8,770 ms |
| me | 1,025 ms | 5,824 ms | 6,310 ms | 11,321 ms |
| latest result | 409 ms | 982 ms | 5,179 ms | 8,942 ms |
| class statistics | 383 ms | 852 ms | 1,650 ms | 9,193 ms |
| history | 380 ms | 855 ms | 2,257 ms | 6,784 ms |
| marksheet link | 870 ms | 5,517 ms | 5,881 ms | 9,451 ms |
| marksheet PDF | 2.3 ms | 9.9 ms | 36.1 ms | 224 ms |

Server-side times (the API's own access log, `server-B-*.txt`) are lower than the client's for every
route, e.g. B-preauth `latest` p50 339 ms / p95 839 ms against 409 / 982 on the client. The gap is
queueing in Caddy and k6 on the shared CPUs.

## The database's own work
`pg_stat_statements` over both runs. The slowest frequent query is the session lookup at a mean of
**0.119 ms**. Tenant resolution on a cache miss is 1.1 ms, but it ran only 860 times. In `explain.txt`,
every hot path is an index scan with shared-buffer hits only. **PostgreSQL is not the bottleneck**: the
time is spent in the API processes, on two CPUs also running k6, Caddy and PostgreSQL.

## Failures
- **503 Service Unavailable** is the API shedding load. It happens when a request can't get a database
  connection in time (`ServiceUnavailable`, retryable). B-preauth ran at a steady 100–340 per 10 s
  (about 2–8% of requests); B-cold peaked at 565.
- **401 in B-cold only:** 49 sign-ins failed (with 503s during the ramp). The k6 script signs in only on a
  user's first iteration, so those 49 users made unauthenticated requests for the rest of the run, at
  about 140 per 10 s. **This is the load generator's behaviour, not the product's**: a real student would
  sign in again. These requests count towards B-cold's 6.11%. B-preauth had no 401s.
- **PDF downloads never failed** (12,863 and 14,203 of them), because they are served from object
  storage and not by the API.

## The slow database (chaos `dbslow`)
At 07:51:08, 50 ms of delay was added to every packet leaving the PostgreSQL container, for 60 s
(`tc netem`). This was during B-cold, at full load.

| 10 s window | requests | slower than 1 s | 503 |
|---|---|---|---|
| 07:50:50 (before) | 4,361 | 839 | 131 |
| 07:51:10 | **1,887** | 1,386 | 167 |
| 07:51:20 | 3,580 | 1,455 | **565** |
| 07:51:30 – 07:52:10 | 4,005–4,329 | 862–1,455 | 39–337 |
| 07:52:20 – 07:52:50 (after) | 4,048–4,344 | 768–1,138 | 51–301 |

Throughput halved in the first ten seconds, then recovered to the normal level within 20 s **while the
delay was still in place**. Requests slower than 1 s rose by about 60% for the minute. The API shed the
overload with 503s rather than letting connections pile up. Nothing crashed, no container restarted, and
the system was back to its pre-failure numbers within about 20 s of the delay ending. The workflow's
"recovered" line is missing from `chaos.txt`, so the exact moment the delay was removed was not logged;
the 07:52:20 window is the first to look like the windows before the failure.

## What this means for result day
- **On 2 vCPUs, 1,000 students at once is beyond comfortable.** Throughput tops out at about 440 req/s.
  p95 stays under 1 s for the result pages (latest, statistics, history), but `me` and the marksheet
  link reach 5–6 s at p95, and 3% of requests are refused with a retryable 503. With k6 on a separate
  machine, the API would get the CPU k6 used here; how much that helps can only be measured on the VPS
  (P18.11).
- **`/me` and the marksheet link are the slow routes** (server p50 858 ms and 726 ms, against about
  330 ms for the others). They are the next thing to profile with `profile: true`, on the VPS.
- **Marksheets take about 24 minutes to render for 8,000 students on 2 vCPUs.** The publish screen shows
  their progress, and a scheduled release renders them ahead of time. For a large school, the admin guide
  should recommend scheduling the release at least half an hour ahead.
- **The earlier laptop runs are not comparable** (8 vCPUs; B-preauth ran at a median 597 req/s with
  0.016% server errors, [2026-10-08](2026-10-08-k6-scenarios-A-B.md)). They differ in CPU count and in the added
  marksheet steps.

## Still to do for P18.11 (on the VPS)
Run `perf.yml`'s journey from a separate machine against the deployed stack:
- cold and pre-authenticated;
- with Redis down, the database slow, and the worker killed;
- recording CPU, RAM and database connections from node-exporter and Prometheus.
