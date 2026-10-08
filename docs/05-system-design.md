# 05 · Scalable System Design

> **Task 1 deliverable.** The end-to-end system design for ScoreCode: requirements, capacity estimation, high-level architecture, write path vs read path, scaling strategy, failure handling, and how the design evolves.
> Deep dives: [06 Multi-tenancy](06-multi-tenancy.md) · [07 Database](07-database-design.md) · [08 Backend](08-backend-architecture.md) · [09 Frontend](09-frontend-architecture.md) · [10 Security](10-security-architecture.md) · [11 Performance](11-performance-architecture.md) · [14 Deployment & ops](14-deployment-and-operations.md) · [17 Tech stack](17-tech-stack.md)
> Diagrams: [component](diagrams/component-diagram.md) · [deployment](diagrams/deployment-diagram.md) · [sequence](diagrams/sequence-diagrams.md) · [data flow](diagrams/data-flow-diagrams.md)

---

## 1. Requirements that drive the design

### Functional (summary — full list in the [SRS](SRS.md))
Tenant lifecycle · identity & RBAC · academic structure · students & staff · exams & grading · marks entry & import · result processing · approval · publication & correction · student portal · PDF marksheets · verification · notifications · analytics · entitlements · branding · audit · platform administration.

### Quality attributes, in priority order (from the brief §28)
| # | Attribute | Concrete design consequence |
|---|---|---|
| 1 | **Correctness** | Deterministic, tested computation; immutable publications; DB constraints, not just app checks. |
| 2 | **Security** | Defence in depth; sessions not long-lived JWTs; audit everything that writes. |
| 3 | **Tenant isolation** | `tenant_id` everywhere + composite FKs + PostgreSQL RLS + tenant-bound sessions + tenant-prefixed cache/storage keys. |
| 4 | **Maintainability** | Modular monolith with enforced module boundaries; typed contracts (OpenAPI → TS). |
| 5 | **Simplicity** | Few moving parts: one app image, one DB, one cache, one object store, one queue *(in Postgres)*. |
| 6 | **Performance** | Precomputed read model; CDN for static; cheap read path. |
| 7 | **Scalability** | Stateless app nodes; scale horizontally; read replicas later. |
| 8 | **Cost efficiency** | Runs on a single small VM for demo; small managed footprint for production. |

### Performance *targets* (to be measured — not claims)
These are hypotheses for the load-test plan in [15 Testing](15-testing-strategy.md). Each will be reported as **measured** or **not yet measured**.

| Target ID | Scenario | Target |
|---|---|---|
| PT-1 | Student "get my latest result" (warm session) | p95 < 150 ms server-side at the scenario's peak RPS |
| PT-2 | Login | p95 < 500 ms at the scenario's login rate (Argon2-bound) |
| PT-3 | Marksheet download URL issuance | p95 < 150 ms; file served by object storage/CDN |
| PT-4 | Error rate during publication spike | < 0.1% (excluding deliberate 429s) |
| PT-5 | Import of 10,000 mark rows | validated report available in < 60 s |
| PT-6 | Processing results for 8,000 students × 6 papers | < 2 min |

---

## 2. Capacity estimation (back-of-the-envelope — *assumptions, not measurements*)

### The reference spike: an 8,000-student institution publishes at 10:00
Assumptions (deliberately pessimistic, to be replaced by real analytics later):
- 70% of students check within the first 10 minutes → **5,600 users**.
- The arrival curve is front-loaded: 40% of those arrive in the first 60 s → **~2,240 users in minute one ≈ 37 new users/s**, with bursts maybe 3–5× higher in the first few seconds.
- Each user session generates ~8 API calls (tenant config, session check, dashboard, result detail, stats, notifications, marksheet URL, history) — static assets come from the CDN, not our servers.

**Derived load:** ~37 users/s × 8 calls ≈ **~300 API requests/s sustained in minute one**, bursts to perhaps **~1,000–1,500 RPS** for a few seconds. After minute one it decays to tens of RPS.

**What this tells us (the key system-design insight):**
1. This is *not* a big-data or "web scale" problem. A few hundred RPS of indexed single-row reads is comfortably within what one well-configured PostgreSQL instance can serve. **The design goal is to keep every result-day request cheap**, not to build a distributed system.
2. **Logins are the real hotspot.** Argon2id is *designed* to cost ~tens of milliseconds of CPU and tens of MB of RAM per hash. If 2,000 students log in during minute one, that is ~33 hashes/s — easily a full CPU core or more of pure hashing. Mitigations: long-lived sessions established *before* result day (activation flow), tuned Argon2 parameters, login rate limiting with fair queuing, and horizontal app scaling for the spike.
3. **PDF generation must not happen on result day.** Rendering an HTML→PDF marksheet can take hundreds of ms of CPU. 5,000 on-demand renders in a few minutes would saturate the app tier. → **pre-render on approval**, serve from object storage.
4. **Many tenants could publish simultaneously** (e.g., several schools publishing at month-end). Multi-tenant peak = sum of concurrent tenant spikes. This is where horizontal scaling of the stateless app tier and caching matter, and why per-tenant rate limits protect neighbours (noisy-neighbour control).

### Storage estimate (per 1,000 students per year, rough)
| Data | Size estimate | Basis |
|---|---|---|
| Mark entries | ~1 MB | 1,000 × 6 papers × 4 exams × ~50 bytes |
| Published snapshots (JSONB) | ~8 MB | 1,000 × 4 publications × ~2 KB |
| Audit log | ~10–30 MB | very write-dependent; partition + archive |
| PDFs (object storage) | ~400 MB | 1,000 × 4 × ~100 KB (font subsetting can shrink this a lot) |
| Uploaded import files | ~10 MB | |

→ The relational database stays small (single-digit GB) for hundreds of tenants; **object storage dominates** and is the cheapest tier. This is why PDFs/uploads never go into Postgres.

---

## 3. High-level architecture

```
                         ┌────────────────────── Users ──────────────────────┐
                         │ Students (mobile)  Faculty/Admins (desktop)       │
                         │ Platform admins    Verifiers (QR scan)            │
                         └──────────────┬────────────────────────────────────┘
                                        │ HTTPS
                     ┌──────────────────▼───────────────────┐
                     │ DNS + CDN / edge (Cloudflare)        │  static SPA assets cached at edge,
                     │ *.scorecode.in, custom domains       │  DDoS shielding, TLS
                     └──────────────────┬───────────────────┘
                                        │
                     ┌──────────────────▼───────────────────┐
                     │ Reverse proxy / LB (Caddy)           │  TLS (incl. on-demand for custom
                     │ routes /api → app, / → static        │  domains), compression, request limits
                     └───────┬───────────────────┬──────────┘
                             │                   │
             ┌───────────────▼──────┐   ┌────────▼─────────────┐
             │ API app nodes (N)    │   │ Worker nodes (M)     │
             │ FastAPI + Uvicorn    │   │ same image, job mode │
             │ stateless            │   │ imports, processing, │
             │ modular monolith     │   │ PDFs, notifications  │
             └──┬───────┬───────┬───┘   └──┬───────┬───────┬───┘
                │       │       │          │       │       │
        ┌───────▼──┐ ┌──▼────┐ ┌▼──────────▼─┐ ┌───▼───────▼──────┐
        │PgBouncer │ │ Redis │ │ Object store│ │ Email provider   │
        │  ▼       │ │ cache,│ │ (S3/R2)     │ │ (SES/Postmark…)  │
        │PostgreSQL│ │ rate  │ │ PDFs, logos,│ └──────────────────┘
        │ primary  │ │ limit │ │ uploads,    │
        │(+replica │ │ (no   │ │ exports     │
        │ later)   │ │ truth)│ └─────────────┘
        │ incl. job│ └───────┘
        │ queue    │
        └──────────┘
   Observability: structured logs → log store · Prometheus metrics → Grafana · Sentry errors · uptime checks
```

### Components and their single responsibility
| Component | Responsibility | Source of truth? |
|---|---|---|
| CDN/edge | Serve SPA bundles, absorb static load, TLS, basic DDoS protection | No |
| Reverse proxy | TLS termination (incl. custom domains), routing, body-size limits, gzip/br | No |
| API nodes | All HTTP API logic; stateless | No |
| Workers | Asynchronous jobs: parse/validate imports, compute results, render PDFs, send notifications, exports, scheduled publications | No |
| PostgreSQL | All business data, sessions, job queue, audit log | **Yes** |
| Redis | Cache, rate-limit counters, short-lived coordination | **No — losing Redis loses no data** |
| Object storage | Binary files (uploads, PDFs, logos, exports) | Yes, for files |
| Email provider | Delivery of transactional email | — |

Why each exists and what was rejected: [17 Tech stack](17-tech-stack.md).

---

## 4. Write path vs read path (CQRS-lite)

The single most important design idea for "high-performance result viewing":

> **Do all expensive work on the write path, before publication. Make the read path a single indexed lookup of an immutable, precomputed document.**

```
 WRITE PATH (admin/faculty, low volume, correctness-critical)           READ PATH (students, spiky, latency-critical)
 ─────────────────────────────────────────────────────────────          ───────────────────────────────────────────────
 marks entry / import  ─►  mark_entries (normalized, validated)
          │
          ▼  process (worker, deterministic)
 student_exam_results (working, revisioned)
          │
          ▼  approve (hash frozen) ─► pre-render PDFs ─► object storage
          │
          ▼  publish (transactional)
 published_results  (immutable JSONB snapshot per student) ───────────►  GET /api/v1/me/results/latest
 exam_statistics    (immutable snapshot)              ───────────────►  GET /api/v1/me/results/{exam}/stats
 verification_records                                  ──────────────►  GET verify.scorecode.in/v/{code}
                                                                          (Redis cache in front, optional)
```

Properties:
- **Immutability makes caching trivially correct.** A `published_results` row for publication *v* never changes; the cache key includes the publication version, so invalidation is never needed — a correction creates *v+1* with new keys.
- The read path touches **one table by index** `(tenant_id, student_id, publication_id)` — no joins, no aggregation.
- Write-path complexity (validation, grading strategies, approvals) is isolated from read-path performance.

---

## 5. Scaling strategy, tier by tier

| Tier | Scaling approach | When to act (signal, not guess) |
|---|---|---|
| Static frontend | CDN — effectively unlimited | From day one (cheap) |
| API nodes | Horizontal: add containers/VMs behind the proxy. Stateless by design (sessions in DB/Redis, files in object store). | CPU > 70% sustained during load tests or p95 regression |
| Workers | Horizontal; separate queues per job class (`imports`, `processing`, `pdf`, `notifications`) so a PDF backlog never blocks an import | Queue depth / job latency metrics |
| PostgreSQL connections | PgBouncer (transaction pooling) in front; app pools sized small | Connection count approaching `max_connections` |
| PostgreSQL reads | 1) indexes & read model, 2) Redis cache for hot published reads, 3) read replica for analytics/exports | DB CPU/IO during load tests |
| PostgreSQL writes | Vertical scaling; batch inserts (COPY) for imports/notifications; partition `audit_logs` by month | Write latency; table size |
| Redis | Single small instance; it holds no truth, so HA is optional until SLA demands it | Memory/CPU |
| Object storage | Managed — no action | — |
| Multi-region | **Not planned.** Users are in India; one Indian region suffices. | Never, until a customer outside India requires it |

### Evolution path (only when a measured requirement appears)
1. Single VM, docker compose (demo).
2. 2+ app VMs + managed Postgres + managed Redis + CDN (small production).
3. Container platform with autoscaling (e.g. ECS/Fargate, Cloud Run-style, or Nomad/K8s *only if team already knows it*), read replica, PgBouncer cluster.
4. Extract a module into a service **only** if it has a different scaling or isolation profile — the likely first candidates are **PDF rendering** (CPU-heavy) and **verification** (public, anonymous traffic). Because modules already communicate via interfaces and jobs, extraction is a deployment change, not a rewrite.
5. Enterprise silo: same images deployed into a dedicated stack for a single tenant.

---

## 6. Failure modes and graceful degradation

| Failure | Effect | Designed behaviour |
|---|---|---|
| Redis down | Cache misses, rate limiter unavailable | App falls back to DB for reads (with circuit breaker so we don't wait on Redis timeouts); rate limiting falls back to a per-process in-memory limiter (coarser, still protective). Alert. |
| One API node dies | Lost in-flight requests | LB health checks remove it; clients retry idempotent GETs. |
| Worker dies mid-job | Job left "running" | Jobs are idempotent with heartbeat/lease; stalled jobs re-queued. Import commit and publication run in single DB transactions so partial application is impossible. |
| DB primary down | Read & write outage | Managed DB failover (small production+). Demo tier: restore from backup — documented RTO/RPO. Student pages show a friendly maintenance message, not stack traces. |
| Object storage slow/down | Marksheet download fails | Result *view* still works (it's in Postgres); download button shows retry message. |
| Email provider down | Notifications delayed | Retries with backoff; in-app notifications still visible. |
| Every pooled DB connection busy (process saturated) | Requests wait up to `SCORECODE_DB_POOL_TIMEOUT_S` | `503` problem `overloaded` + `Retry-After: 2` (never a bare 500); the SPAs retry with jittered backoff; counted in `scorecode_db_pool_exhausted_total`. Found by the P10.6 load test. |
| Traffic beyond capacity | Latency rises | Per-tenant & per-IP rate limits (429 with Retry-After), static "results are being published, please retry in a moment" page for the student app, priority for already-authenticated users over new logins. |
| Bad import file | — | Never touches live marks until explicit commit; staging is isolated. |
| Bug in grading | Wrong results | Preview + anomaly checks + approval gate + correction workflow (versioned) + audit trail. |

---

## 7. Key cross-cutting design decisions (summary)

| Decision | Choice | Detail |
|---|---|---|
| Architecture style | Modular monolith | [08](08-backend-architecture.md), [17](17-tech-stack.md) |
| Tenancy model | Shared DB, shared schema, `tenant_id` + composite FKs + RLS | [06](06-multi-tenancy.md) |
| Tenant routing | Host-based (subdomain; custom domain on Pro) in **all** environments | [06](06-multi-tenancy.md#4-tenant-aware-routing) |
| Auth | Opaque server-side sessions in HttpOnly cookies; API keys for integrations | [10](10-security-architecture.md) |
| Read model | Immutable published snapshots | §4 above |
| Async jobs | PostgreSQL-backed job queue | [08](08-backend-architecture.md#6-background-jobs) |
| Real-time | Polling in MVP; SSE later if measured need; no WebSockets | [11](11-performance-architecture.md) |
| Files | Object storage, tenant-prefixed keys, signed URLs | [10](10-security-architecture.md) |
| Observability | Structured logs + Prometheus + Sentry + uptime | [14](14-deployment-and-operations.md) |

The full decision register (what needs your confirmation before coding) is in [18 Risks & decisions](18-risks-and-decisions.md).
