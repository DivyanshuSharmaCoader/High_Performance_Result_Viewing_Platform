# Benchmark report (P17.4) — 2026-10-09

Every number here was measured; each links to its dated result file with method, environment and raw
data ([benchmarks/](../../benchmarks/README.md)). Targets are the SRS's (NFR-3 to NFR-7, NFR-16).

**Read this first:** the load tests ran on one 4-vCPU GitHub runner hosting the whole stack *and* the
load generator. That is pessimistic (they compete for CPU) but repeatable. Runner CPU models vary between
runs, so before/after comparisons run both variants on one runner, in ABBA order (`perf.yml compare=`).

## 1. Result day (scenario B: 1,000 students arriving in 60 s, then 5 minutes of reading)
Same runner (AMD EPYC 7763), `perf.yml` run 37838765271:

| Code | req/s | Failed | `latest` p95 (k6, end to end) | DB statements per request | DB time per request |
|---|---|---|---|---|---|
| Before the P14.3 changes (1e3b76b) | 322–327 | 3.3–3.6% | 4.4–4.5 s | 6.86 | 0.33 ms |
| After (22d2b73) | **573–593** | **0.00%** | **0.24–0.28 s** | **1.65** | **0.03 ms** |

- **After the changes, the system serves the whole offered load.** At 1,000 users with 2–10 s of think
  time, about 600 req/s is all the load there is, and nothing fails.
- **Before, the API was saturated.** The failures were 503 `overloaded`: a 5 s wait for a database
  connection held up by a saturated event loop
  ([2026-10-08-runner-scenarios.md](../../benchmarks/results/2026-10-08-runner-scenarios.md)).
- **Server-side p95 (NFR-3)** is recorded from run 37867983470 onwards: see §5.

## 2. What changed, and what each change bought (P14.2, P14.3)
- **Profile of the saturated API** (py-spy, scenario B):
  - SQLAlchemy and asyncpg: **38.7%** of CPU.
  - A transaction per request: 5%.
  - Route matching: 6.1%.
  - The pool's pre-ping: 2.6% (half of all `BEGIN`s).
- **Four fixes**, each measured before and after on one machine
  ([2026-10-09-read-path.md](../../benchmarks/results/2026-10-09-read-path.md)):

| Change | API CPU per request |
|---|---|
| Student read cache (immutable rows, per-tenant keys) | −20% |
| Student routers matched first | −5% |
| The transaction starts at the first statement (a cached request takes no connection) | −14% |
| Ping pooled connections only after they idle | −3% |
| **Together** | **about −35%** |

## 3. Other targets
| Target | Result | File |
|---|---|---|
| NFR-5: validate a 10,000-row marks file < 60 s | **1.59 s** (CSV), **2.69 s** (XLSX) | [2026-10-07-marks-import-10k](../../benchmarks/results/2026-10-07-marks-import-10k.md) |
| NFR-6: process 8,000 students × 6 papers < 2 min | **9.59 s** end to end; approval 1.16 s | [2026-10-07-result-processing-8000x6](../../benchmarks/results/2026-10-07-result-processing-8000x6.md) |
| NFR-4: login p95 < 500 ms | scenario A cold: **42 ms**; scenario B cold: 2.97 s (logins queue behind the saturated workers on the 4-vCPU runner, before P14.3) | [runner scenarios](../../benchmarks/results/2026-10-08-runner-scenarios.md) |
| Marksheet PDFs | about 200 ms each on one thread; 8,000 marksheets plus notices in 18–20 min with 2 processes per worker on the runner; 4 processes give 3.4× locally | [marksheet render](../../benchmarks/results/2026-10-08-marksheet-render.md), [failure under load](../../benchmarks/results/2026-10-08-failure-under-load.md) |
| Argon2id cost | 33 ms per verification; about 98 verifications/s on 4 threads | [argon2id](../../benchmarks/results/2026-10-06-argon2id-cost.md) |

## 4. Scaling out (NFR-16)
**The API and workers are stateless:** sessions, caches and limits live in PostgreSQL and Redis, and
background work is claimed with `FOR UPDATE SKIP LOCKED`. Caddy finds every API container by DNS and
balances with `least_conn`. The 2-container runs split CPU within 10%.

| Comparison (same runner) | Result |
|---|---|
| 1 vs 2 containers × 2 workers, 1,000 users (run 37838754876) | Both served the offered load: about 644 req/s, 0 errors. p95 9.1–9.8 ms vs 6.7 ms. There's nothing to compare at that load |
| 1 vs 2 containers × 2 workers, 3,000 users (run 37845417571) | 531–534 vs 551–581 req/s. Failures **rose**, from 6–7.5% to 28–39% (all retryable 503s) |
| 1 vs 2 containers × **1 worker**, 2,000 users (run 37866472727) | *pending* |

**What the 3,000-user run shows:**
- With two containers, four API processes, PostgreSQL, Caddy and a 3,000-user load generator compete for
  the same 4 vCPUs.
- A second container on the **same** machine adds processes, not CPU. Each event loop gets less of it,
  so more requests wait past the 5 s pool timeout.
- Scaling out works by adding machines (docs/14 N3). On one machine, the knob is the number of workers,
  about one per spare vCPU.
- The one-worker comparison isolates the effect of a second API process that has a core of its own.

## 5. Server-side latency (NFR-3: latest result p95 < 150 ms server-side)
*Pending run 37867983470:* `timeline.py --latency` over the API's own request log. That is the time from
the request reaching the API to its response, without the proxy, the network or the load generator's
queueing.

## 6. Failures under load (docs/15 §6)
| Injection | Result | File |
|---|---|---|
| Redis stopped for 60 s | throughput and errors unchanged; caches and limits degrade to per-process | [failure under load](../../benchmarks/results/2026-10-08-failure-under-load.md) |
| PostgreSQL restarted | before P14.3: about 200 extra retryable 503s in one 10-s window. After (idle-only pings, run 37841311985): **57**, no 500s, recovered in the next window, 0.02% failed overall | same, and §3 of the read-path file |
| Worker SIGKILL during 8,000 marksheets | every marksheet exactly once, no duplicate notices | same |
| Database lost entirely | restored from an encrypted backup with identical fingerprints; **RTO 57 s** | [drill log](../runbooks/drills/README.md) |

## 7. Not measured
- Production hardware.
- A load generator on a separate machine.
- Multi-machine scale-out.
- Network latency or loss to the database.
- Object-storage outages.
