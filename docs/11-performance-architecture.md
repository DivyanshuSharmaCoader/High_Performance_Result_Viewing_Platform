# 11 · Performance Architecture

> Covers brief section **M**, §9–11 (publication spike, performance architecture, scientific validity) and §32 (benchmarking).
> Capacity estimation: [05 §2](05-system-design.md#2-capacity-estimation-back-of-the-envelope--assumptions-not-measurements). Test plan: [15 Testing](15-testing-strategy.md#5-load--performance-testing).

## 0. Ground rules
1. **No performance number appears in any ScoreCode document, slide or marketing page unless it was measured**, with the hardware, dataset, tool, script version and date recorded next to it (see [benchmarks/README.md](../benchmarks/README.md)).
2. **Optimise the bottleneck you measured**, not the one that sounds impressive. Each optimisation below has an *activation trigger*.
3. Correctness, security and isolation are never traded for speed (e.g. we never cache across tenants, never skip authorization on "hot" endpoints).

---

## 1. Where the time actually goes on result day (hypothesis to verify)

| Request | Work | Expected cost class |
|---|---|---|
| Static assets | CDN | ~0 server cost |
| `GET /tenant/config` | cached JSON | very cheap |
| Session validation | cache hit, else 1 PK lookup | very cheap |
| `POST /auth/login` | **Argon2id hash** | **expensive (CPU + RAM by design)** |
| `GET /me/results/latest` | 1 index lookup of a JSONB snapshot | cheap |
| `GET .../stats` | 1 PK lookup of stats snapshot | cheap |
| marksheet URL | 1 lookup + sign URL (HMAC) | cheap; file bytes served by object store/CDN |
| notifications list | 1 index range scan | cheap |

→ Prediction: **login throughput and connection management are the limits**, not result reads. The load tests are designed to confirm or refute this.

---

## 2. Component-by-component justification

Format per component: **Need → Problem solved → Alternatives → Choice → Complexity introduced → Activation trigger**.

### 2.1 Async API (FastAPI on Uvicorn, asyncpg)
- **Need:** handle many concurrent I/O-bound requests per process.
- **Problem:** sync workers block a thread per in-flight DB/Redis call; thousands of concurrent connections need thousands of threads.
- **Alternatives:** sync Django/Flask + gunicorn threads; Node.js; Go.
- **Choice:** FastAPI async + SQLAlchemy 2.0 async + asyncpg; multiple Uvicorn worker processes per node (≈ CPU cores).
- **Complexity:** async discipline — any blocking call (Argon2, PDF, openpyxl) must run in a thread pool or worker. Argon2 runs via `run_in_threadpool` with a **bounded semaphore** so login bursts cannot starve other requests.
- **Trigger:** day one.

### 2.2 Horizontal scaling & load balancing
- **Need:** survive the spike and node failure.
- **Problem:** one process/VM has a ceiling and is a single point of failure.
- **Alternatives:** bigger single VM (vertical); autoscaling container platform.
- **Choice:** stateless API nodes behind Caddy (small prod) or cloud LB (growing); health-checked (`/readyz`); round-robin/least-conn.
- **Complexity:** shared state must live outside the process (sessions in DB/Redis, files in object store) — already the design.
- **Trigger:** small production (≥2 nodes for availability); add nodes when load tests show CPU saturation. **Scheduled pre-scaling**: because publication times are *known in advance* (scheduled publications), the platform can scale up 15 min before a large tenant's publication — cheaper and more reliable than reactive autoscaling.

### 2.3 Connection pooling (SQLAlchemy pool + PgBouncer)
- **Need:** PostgreSQL connections are expensive processes (memory per backend); N nodes × M workers × pool size can exceed `max_connections`.
- **Alternatives:** large `max_connections` (wastes memory, degrades performance); app pool only.
- **Choice:** small app pools (e.g. 5–10 per process) + **PgBouncer in transaction mode** once there are >2 API nodes; managed DB poolers where available.
- **Complexity:** transaction pooling forbids session-level state → we use `SET LOCAL`/`set_config(..., true)` for tenant context (already required) and avoid session-level prepared statements (asyncpg statement cache disabled or PgBouncer ≥1.21 prepared statement support).
- **Trigger:** connection count > ~50% of `max_connections` in load test, or >2 nodes.

### 2.4 Database indexing & efficient read paths
- **Need:** keep hot queries O(log n), index-only where possible.
- **Choice:** the published read model ([05 §4](05-system-design.md#4-write-path-vs-read-path-cqrs-lite)) + covering indexes ([07 §5](07-database-design.md#5-indexing-strategy)); `EXPLAIN ANALYZE` captured for every hot query in the benchmark report; `pg_stat_statements` enabled.
- **Complexity:** denormalised snapshot must be built correctly at publish time (tested).
- **Trigger:** day one (it's the architecture, not a tweak).

### 2.5 Caching (Redis) — where it is and isn't justified
| Data | Cache? | Key / TTL | Invalidation |
|---|---|---|---|
| Host → tenant, tenant config/branding | ✅ in-process LRU (30–60 s) + Redis | `tenant:host:{host}`, `t:{tid}:config:v{n}` | version bump on change; short TTL bounds staleness |
| Sessions | ✅ Redis (60 s) | `sess:{hash}` | delete on logout/revoke (+ TTL bound) |
| Effective entitlements | ✅ in-process + Redis | `t:{tid}:ent:v{n}` | version bump on plan/override change |
| Published result payload | ⚠️ **only if measurements show DB is the bottleneck** | `t:{tid}:pub:{pid}:stu:{sid}` (immutable) | **none needed** — immutable; withdrawal handled by checking publication status (cached separately, short TTL) |
| Exam stats snapshot | ✅ if measured | `t:{tid}:stats:{pid}` | immutable |
| Mutable admin data (marks grid, lists) | ❌ | — | Correctness > speed; low volume |
- **Alternatives:** no cache (DB only); CDN caching of API responses (unsafe for personalised data); in-process only (no sharing across nodes).
- **Complexity:** another dependency; stale-data risks; tenant-key discipline. Mitigated by: immutable keys, versioned keys, Redis never being source of truth, circuit breaker on Redis errors.
- **Withdrawal edge case:** a cached payload must not be served after a publication is withdrawn → the read handler always checks `publication.status` from a tiny cached map with ≤5 s TTL (withdrawal also actively deletes keys). Bounded staleness is documented.
- **Trigger:** config/session/entitlement caching from MVP (cheap, high hit rate). Result-payload caching only after a load test shows DB CPU or latency as the bottleneck.

**Redis vs no Redis:** the MVP *can* run without Redis (in-process caches + DB rate limiter), and the code must keep working if Redis disappears. Redis is added in small production because cross-node rate limiting and session caching need shared state. That's the justification — not "Redis makes things fast".

### 2.6 HTTP caching & CDN
- Static SPA assets: content-hashed filenames, `Cache-Control: public, max-age=31536000, immutable`, served by CDN; `index.html` `no-cache`.
- Tenant config: `ETag` + `Cache-Control: private, max-age=60`.
- Personal results: `Cache-Control: private, no-store` on shared devices? Trade-off: students on shared/cyber-café computers → **`no-store`** for result payloads; the SPA's in-memory cache handles repeat views.
- Marksheet PDFs: served directly from object storage via signed URLs (5 min), optionally through the CDN with signed-URL support. App servers never stream PDF bytes.
- Compression: Brotli/gzip at proxy/CDN.

### 2.7 Background jobs
- **Need:** move heavy/slow work out of requests: import parsing/validation, result processing, PDF rendering, notification fan-out, exports.
- **Choice & alternatives:** PostgreSQL-backed queue — comparison in [08 §6](08-backend-architecture.md#6-background-jobs).
- **Performance role:** pre-rendering PDFs at approval time removes the biggest potential CPU spike from result day.
- **Complexity:** idempotency, retries, monitoring queue depth.

### 2.8 Event-driven notifications
- Publication emits `PublicationPublished` → job fans out: bulk insert in-app notifications (`COPY`/multi-row), email in batches respecting provider rate limits.
- **Thundering-herd consideration:** emailing 8,000 students at 10:00:00 *creates* the spike. Option (tenant setting): **staggered notifications** over N minutes by cohort — smooths the curve at the cost of some students hearing a few minutes later. Default off; recommend for large tenants after measurement.

### 2.9 Real-time updates: WebSockets vs SSE vs polling
| | WebSockets | Server-Sent Events | **Polling** |
|---|---|---|---|
| Direction | Bi-directional | Server → client | Client → server |
| Infra | Sticky/long-lived connections, proxy config, memory per connection | Long-lived HTTP connections; simpler; auto-reconnect | Plain HTTP, cache-friendly |
| Spike behaviour | Thousands of idle sockets held during the spike | Same, lighter | Short requests; easy to rate-limit |
| Need in ScoreCode | None (no chat/collab) | Import/processing progress (admin only, a handful of users) | Same use case |
| **Verdict** | ❌ | Later, if polling cost is measured to matter | ✅ MVP |

**Students get no real-time channel.** "Your result is out" is delivered by email/in-app notification; a student who has the page open sees it on refresh. Admin progress uses 2 s polling of `GET /jobs/{id}` (a handful of admins → negligible load). SSE is the upgrade path; WebSockets are not planned.

### 2.10 Rate limiting
Protects fairness and the shared platform (noisy neighbours, credential stuffing, scraping). Buckets in [10 §7](10-security-architecture.md#7-rate-limiting--abuse-prevention). During publication spikes, **authenticated result reads get generous limits; anonymous/login endpoints get stricter limits** — logins are the expensive operation.

### 2.11 Graceful degradation
Priority order under overload: (1) serve authenticated students their results, (2) logins, (3) marksheet downloads, (4) stats, (5) history, (6) admin analytics/exports (deferred via queue). Implemented with: separate rate-limit budgets per endpoint class, `statement_timeout`, Redis circuit breaker, bounded login semaphore, friendly retry UX in the SPA with jitter. Detailed failure table: [05 §6](05-system-design.md#6-failure-modes-and-graceful-degradation).

### 2.12 Database scaling path
1. Vertical scaling of managed PG (cheap and effective up to large sizes).
2. Read model + caching (already).
3. **Read replica** for analytics, exports, platform reporting (not the student read path at first — replication lag could hide a just-published result; if used for the student path, read-your-publication consistency must be handled by checking replica LSN ≥ publication LSN).
4. Partitioning (audit first).
5. Silo deployments for very large tenants.
Sharding: not planned; the data volume doesn't warrant it.

### 2.13 Cache invalidation summary
Immutable-by-version keys for published data (no invalidation needed); version counters for tenant config & entitlements (bump on write in the same transaction, the post-commit hook deletes old keys); short TTLs as the safety net; never cache mutable admin data.

---

## 3. Login spike strategy (the real hotspot)
1. Activation before result day + 30-day student sessions → most students are **already logged in** at publication.
2. Argon2id parameters measured and chosen deliberately (document `time_cost`, `memory_cost`, `parallelism` and the ms/hash on the target CPU).
3. Bounded concurrency for hashing per process; login requests beyond capacity wait briefly then receive 429 + `Retry-After` with UI auto-retry, instead of timing everything out.
4. Pre-scale app nodes before scheduled large publications.

---

## 4. Benchmark plan (scientifically valid)

### Tooling
- **k6** for load generation (efficient, scriptable, good percentile output). Locust is an acceptable alternative if Python scripting is preferred.
- Prometheus + Grafana (or `docker stats` + `pg_stat_*` snapshots on a single VM) for server-side metrics.
- Synthetic data generator (deterministic seed) that creates N tenants, students, exams, published results.

### Scenarios (from brief §32)
| ID | Virtual users | Shape | Notes |
|---|---|---|---|
| A | 100 | ramp 1 min, hold 5 min | baseline / smoke |
| B | 1,000 | publication spike: 0→1,000 in 60 s, hold 5 min | realistic mid-size |
| C | 5,000 | spike | likely needs separate load-generator machine |
| D | 10,000 | spike | **only if infrastructure allows**; otherwise documented as not run with reason |
Each scenario runs in two variants: **pre-authenticated** (sessions created before the test) and **cold login** (Argon2 path), because their bottlenecks differ.

User journey per VU: `config → me → results/latest → stats → marksheet-url → (30%) history → think time 2–10 s`.

### Metrics recorded
p50/p95/p99 latency per endpoint, RPS achieved, error rate (split: 5xx vs 429), CPU & memory per container, DB CPU, active connections, `pg_stat_statements` top queries, Redis hit rate & ops/s, job queue depth.

### Validity rules
- Load generator on a **different machine** from the system under test (or documented as co-located, with the caveat that results are pessimistic and noisy).
- Warm-up period excluded; ≥3 runs per scenario, report median run and spread.
- Record: git commit SHA, hardware (vCPU, RAM, disk), OS, container limits, dataset size, config (pool sizes, workers, Argon2 params), k6 script version.
- Report negative results and bottlenecks honestly; every optimisation is validated by a before/after run of the same scenario.
- Local hardware limits (e.g. a laptop can't generate 10k VUs *and* host the stack) are written down, and the largest feasible scenario is reported instead of extrapolating.

Results live in `benchmarks/results/<date>-<scenario>.md` (template in [benchmarks/README.md](../benchmarks/README.md)).
