# Scenarios A and B — pre-authenticated and cold login — 2026-10-08

P10.6 baseline, docs/11 §4. **A laptop baseline, not a capacity claim.** Everything ran on one Apple M2
laptop: the stack, the database and the load generator shared the same eight cores. The load test found
two bugs that would have hurt on result day; both are fixed in the commit that adds this file. One
methodology trap (battery power) invalidated three later runs; they are reported as controls, not results.

## Environment
- **Code.** Runs 1–8 used an image built on 2026-10-07 at 20:09 UTC. Its request-path code matches
  `9eea1e5`; the one difference, the per-IP login default, was overridden by `compose.yml` anyway (below).
  B-cold-2 and the two controls ran `9eea1e5` plus this commit's client-address fix and route-level 503.
  The middleware-level 503 came after them.
- **k6 script:** `benchmarks/k6/student-journey.js` as committed with this file. k6 v2.3.0 (linux/arm64).
- **Hardware.** Apple M2 (4 performance + 4 efficiency cores), 16 GB RAM, macOS 15.3. Docker Desktop
  29.1.3 VM: 8 vCPUs, 7.65 GiB. All images are native arm64, with no container CPU or memory limits.
- **Topology.** The `compose.yml` stack:
  - Caddy 2.11.7, then one API container running 2 Uvicorn workers (Python 3.12);
  - PostgreSQL 16.15 (`max_connections=200`) and Redis 7.4 (256 MB, LRU); no PgBouncer;
  - the worker container was idle.
- **Config.**
  - DB pool: 10 + 5 overflow per process, 5 s timeout.
  - Argon2id: t=2, m=19 MiB, p=1, at most 4 concurrent hashes per process.
  - Sessions: Redis cache with a 10 s in-process tier.
  - Login limit per IP: 300/min, burst 100, from a `compose.yml` override left over from early E2E work.
    That override was stricter than the production default (3,000/1,000) and is removed in this commit.
- **Load generator.** k6 in a container on the same Docker network (`scorecode_default`), hitting
  `http://proxy:8080` with `Host: loadtest.localhost:8080`. Each virtual user sends its own
  `X-Forwarded-For` address from 198.18.0.0/15 (RFC 2544 benchmarking range); Caddy trusts the k6
  container (private range) to report it. **Co-located with the system under test, so the numbers are
  pessimistic and noisy** (docs/11 §4 validity rules).
- **Dataset** (`backend/scripts/loadtest_data.py`, seed 2026), one tenant:
  - 8,000 students who can sign in, in 40 cohorts;
  - one semester exam of 6 papers, processed, approved and published through the real services
    (8,000 published results);
  - 1,000 sessions made beforehand for the pre-authenticated variant.
- **Power** (`pmset -g log`):
  - A-preauth runs 1–3: on battery. This machine has Low Power Mode set for battery.
  - B-preauth runs 1–3, A-cold and B-cold-1: on AC.
  - B-cold-2 and the controls: on battery with Low Power Mode. See Finding 3.

**Raw data:** [2026-10-08-k6/](2026-10-08-k6/) holds, per run:
- `<run>.txt`: k6 summary;
- `<run>.json`: k6 end-of-test data;
- `<run>.csv`: docker stats, as epoch, container, CPU, memory.

Run start times (IST) are in `run-times-ist.log`.

## Scenario
- **A:** 100 VUs, ramp over 1 min, hold 5 min.
- **B:** 1,000 VUs, 0 → 1,000 in 60 s, hold 5 min.
- **Journey per iteration:** `GET /tenant/config` → `GET /me` → `GET /me/results/latest` →
  `GET /me/results/{id}/stats` → (30%) `GET /me/results`, then think 2–10 s (uniform).
  - **pre-authenticated:** the VU starts with a session cookie;
  - **cold:** the VU first fetches a CSRF token and signs in (the Argon2 path).
  - The plan's marksheet-URL step is left out: marksheet PDFs arrive in Phase 11.
- Each VU keeps its cookies across iterations, like a student who stays signed in.
- Pre-authenticated variants were run 3 times (median and range reported below); cold variants once
  each, so they have no spread.

## Results

Latency in milliseconds, measured by k6 (client side, through Caddy).

### A · pre-authenticated — median of 3 runs (range), on battery
23,787 requests per run (23,726–23,862) · 64.5 req/s (64.2–64.6) · **0 errors**

| Endpoint | p50 | p95 | p99 |
|---|---|---|---|
| config | 3.6 (3.4–3.7) | 10.7 (9.7–10.9) | 20.0 (16.7–21.2) |
| me | 3.8 (3.7–4.0) | 8.0 (7.7–8.1) | 13.1 (12.6–16.7) |
| results/latest | 4.9 (4.7–5.1) | 9.1 (8.3–9.3) | 16.0 (14.6–18.5) |
| stats | 5.6 (5.4–5.8) | 10.6 (9.3–10.8) | 19.7 (18.1–20.4) |
| history | 4.5 (4.3–4.7) | 8.4 (7.4–8.7) | 14.8 (13.0–16.9) |

### A · cold login — 1 run, on AC
24,016 requests · 65.1 req/s · **0 errors** · 100 of 100 sign-ins succeeded

| Endpoint | p50 | p95 | p99 |
|---|---|---|---|
| csrf | 1.6 | 3.7 | 4.0 |
| **login** | **34.0** | **49.2** | **53.0** |
| config | 3.2 | 9.7 | 21.3 |
| me | 3.3 | 7.5 | 12.7 |
| results/latest | 4.1 | 8.0 | 12.6 |
| stats | 4.5 | 7.9 | 12.7 |
| history | 3.5 | 5.8 | 9.5 |

At 100 VUs a sign-in costs about one Argon2 verification: 34 ms, against 33.1 ms measured in isolation
(2026-10-06 Argon2 file).

### B · pre-authenticated — median of 3 runs (range), on AC
- 220,741 requests per run (217,377–224,920) · 596.6 req/s (587.6–608.4).
- **103 server errors in 663,038 requests (0.016%)**: 0, 16 and 87 per run. Every one was a database
  pool timeout surfacing as a 500 (Finding 2).

| Endpoint | p50 | p95 | p99 |
|---|---|---|---|
| config | 12.6 (9.1–33.4) | 688 (506–757) | 1,781 (1,021–1,988) |
| me | 12.7 (9.4–34.5) | 676 (470–732) | 1,616 (945–1,838) |
| results/latest | 11.0 (8.4–29.5) | 643 (450–698) | 1,583 (944–1,829) |
| stats | 12.4 (9.8–32.5) | 586 (436–675) | 1,524 (892–1,788) |
| history | 11.3 (8.4–28.7) | 512 (418–643) | 1,438 (874–1,603) |

### B · cold login, before the fix — 1 run, on AC
- 601 of 1,000 sign-ins got `429` (Finding 1). The 601 VUs without a session then made cheap `401`
  calls for the rest of the run (32,469 failed `me` checks). The remaining errors were 2 pool-timeout
  500s.
- This run's latencies therefore describe a different workload and are not reported as a baseline.

### B · cold login, after the fix — 1 run, on battery with Low Power Mode (not comparable)
- 137,752 requests · 370.2 req/s.
- Sign-ins: **980 of 1,000 succeeded** (k6). The other 20 got `503`; the server returned no `429`.
- Server side: 3,297 × `503` (pool wait over 5 s, now a retryable answer), 7 × `500` and 1,371 × `401`.
  - The 500s came from the same pool timeout in the tenant lookup in the middleware, which is outside
    FastAPI's handlers. They are fixed and tested in this commit.
  - The 401s came from the 20 VUs without a session.
- Latency: config p50 687 / p95 4,414 / p99 5,207; login p50 44 / p95 2,946 / p99 5,095. Both workers
  were pinned for the whole hold (API CPU 215% on average). **The cause was the power state, not the
  sign-ins.** The controls below show the same saturation without any sign-ins.

### Controls: B · pre-authenticated, on battery with Low Power Mode
| Run | What differs from B-preauth runs 1–3 | req/s | failed | p50 (config) | API CPU avg |
|---|---|---|---|---|---|
| B-preauth-4 | this commit's build (per-VU client addresses) | 336.3 | 4.64% | 884 | 201% |
| B-preauth-5 | as 4, but Caddy not sending `X-Real-IP`, so all VUs share one address as in runs 1–3 | 404.1 | 1.45% | 537 | 195% |

The status split for the controls wasn't captured: the API container's logs were lost when it was
rebuilt. The failure percentages come from k6.

A 20-second smoke run (10 VUs) on the new build matched the old build within 1–2 ms at p50 on every
endpoint. Together with run 5, that rules out a per-request regression from the change.

## Resources (docker stats every 5 s; average / peak)
| Run | API CPU | API memory (peak) | Postgres CPU | Caddy CPU | Redis CPU |
|---|---|---|---|---|---|
| A-preauth (1–3) | 28–29% / 67–155% | 472 MiB | 7% / 12–24% | 3.5% | 1.5–1.9% |
| A-cold | 23% / 44% | 569 MiB | 6% / 23% | 3.3% | 1.4% |
| B-preauth (1–3) | 152–171% / 250–253% | 498–519 MiB | 40–46% / 63–77% | 19–23% | 3.9–4.4% |
| B-cold-1 | 109% / 228% | 757 MiB | 27% / 72% | 17% | 2.4% |
| B-cold-2 (battery) | 215% / 331% | 823 MiB | 46% / 63% | 25% | 5.7% |

Not captured in these runs, though the plan asks for them: `pg_stat_statements` top queries, active
connection counts, Redis hit rate (process counters only, below) and job queue depth (the worker was
idle). One process's counters after the controls showed a 90% hit rate in the local cache tier and 84%
in Redis.

## Analysis

**What the docs predicted** (docs/11 §1): "login throughput and connection management are the limits,
not result reads."

**What we saw on this machine.**
- **Pre-authenticated reads.** The first limit is the API processes' CPU, not the database. At about 600
  req/s, the two Uvicorn workers averaged 150–170% CPU and peaked at 250%, while Postgres averaged
  about 45%. That works out to about 2.6 ms of API CPU per request.
  - Tail latency grows when requests queue for the event loop while holding pooled connections. The
    p95 of 0.5–0.7 s and the pool timeouts are a symptom of CPU saturation, not of too few
    connections: more connections would not add CPU.
  - So result reads are not free in Python. The prediction holds only in part: connection management
    shows up, but as a consequence of CPU saturation.
- **Cold login.** Each sign-in cost about 34 ms of Argon2 work at 100 VUs. At 1,000 VUs the run did not
  measure Argon2 at all: it measured the per-IP limiter (Finding 1).
- **API memory** grows by about 300 MB once sign-ins happen and stays there. Argon2 needs 19 MiB per
  hash, with up to 8 hashes running at once across the two processes, and the allocator keeps the
  freed memory. Observed, not yet investigated (Phase 14).

### Finding 1 — every student behind one proxy shared one sign-in bucket (fixed)
- **What happened.** The API took the right-most `X-Forwarded-For` entry as the client address. That
  entry is the nearest proxy: here the k6 container; in production, a CDN edge serving a whole city.
  So all 1,000 students drew from one per-IP bucket. 300/min with a burst of 100 over the 60 s ramp is
  about 400 sign-ins, and 399 succeeded.
- **The fix.**
  - Caddy now works out the client address itself: `trusted_proxies` plus `trusted_proxies_strict`, so
    `X-Forwarded-For` is read from the right and the first untrusted hop wins.
  - Caddy *overwrites* `X-Real-IP` with that address, and the API reads only that header.
  - Tested: a forged left-most entry is ignored, a client-sent `X-Real-IP` is ignored, and one student
    exhausting the failure bucket does not lock out another student behind the same edge. Each test was
    mutation-checked, and the behaviour was checked end to end through Caddy on the stack.
  - After the fix, 980 of 1,000 cold sign-ins succeeded even on a throttled CPU.

### Finding 2 — pool timeouts surfaced as 500s (fixed)
- **What happened.** Under saturation a request can wait more than `SCORECODE_DB_POOL_TIMEOUT_S` for a
  connection. SQLAlchemy's `TimeoutError` hit the generic handler and became a `500`.
- **The fix.** It is now a `503 overloaded` problem with `Retry-After: 2`, which the SPAs already retry
  with jittered backoff. This covers both route dependencies and the tenant lookup in the middleware,
  and each is counted in `scorecode_db_pool_exhausted_total`. Tested and mutation-checked.

### Finding 3 — battery power cut this laptop's capacity by a third to almost a half (methodology)
- With the same code and data, B-preauth on battery with Low Power Mode served about 340–400 req/s with
  both workers pinned, against about 600 req/s on AC.
- `benchmarks/k6/run.sh` now refuses to run on battery unless `FORCE=1` is set for a labelled control.

## What this does and does not show
- **It shows:**
  - the student read path works under 1,000 concurrent students on one laptop, with 0.016% errors
    before the fix and retryable 503s after;
  - where the first bottleneck is (API CPU);
  - two real defects, found and fixed.
- **It does not show:**
  - capacity on server hardware, or with a separate load generator;
  - scenarios C and D, which need a separate load-generator machine (docs/11 §4);
  - **B-cold after the fix on AC power.** This is open: re-run `benchmarks/k6/run.sh B cold 3` on AC.

## Next action
- Phase 14 (performance), each step validated by a before/after run of the same scenario:
  - re-run B-cold on AC;
  - profile the API's CPU per request (py-spy) on the read path; candidates are per-request JSON
    logging, response serialisation and ORM work;
  - set Uvicorn workers to the vCPU count;
  - look at allocator settings for the Argon2 memory growth.
- Pre-scale before large scheduled publications (docs/11 §3) stays the operational answer until then.
