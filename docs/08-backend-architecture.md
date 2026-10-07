# 08 · Backend Architecture

> Covers brief section **J** (modules/services and API boundaries) and the SE evidence asked for in §30 (modular design, SOLID, API design, error handling).
> Diagrams: [component diagram](diagrams/component-diagram.md) · [class diagrams](diagrams/class-diagrams.md) · [sequence diagrams](diagrams/sequence-diagrams.md)

---

## 1. Style: modular monolith

One deployable (one Docker image) that runs in two modes — `api` (Uvicorn/FastAPI) and `worker` (job consumer) — containing **independent modules with enforced boundaries**.

### Why not microservices (comparison)
| | Modular monolith | Microservices |
|---|---|---|
| Transactions across modules (e.g. publish = snapshot + verification + notifications) | One ACID transaction | Sagas/outbox across services |
| Ops burden for a 1–3 person team | One image, one DB | N deployables, service discovery, distributed tracing mandatory |
| Tenant isolation | One enforcement point | Must be re-implemented per service |
| Independent scaling | Via `api`/`worker` modes and job queues — sufficient | Fine-grained |
| Later extraction | Possible if boundaries are clean | — |
| **Verdict** | ✅ **Chosen** | ❌ No requirement justifies it now |

The boundaries below are designed so that **PDF rendering**, **verification** and **notifications** could be extracted later without changing their callers.

---

## 2. Modules (bounded contexts)

| Module | Owns (tables) | Public service interface (examples) | Depends on |
|---|---|---|---|
| `platform` | plans, features, plan_features, platform_users, platform_audit_logs | `TenantAdminService.suspend()`, `PlanService` | tenancy, entitlements, audit |
| `tenancy` | tenants, tenant_domains, tenant_settings | `TenantResolver.resolve(host)`, `TenantProvisioner.create()` | — |
| `identity` | users, user_roles, sessions, auth_tokens, api_keys | `AuthService.login()`, `SessionService.validate()`, `Authorizer.require(perm)` | tenancy, audit |
| `entitlements` | tenant_subscriptions, tenant_feature_overrides, tenant_usage_* | `Entitlements.has(feature)`, `Entitlements.check_limit(limit, delta)` | tenancy |
| `branding` | tenant_branding, marksheet_templates (tenant rows) | `BrandingService.get_public_config()` | entitlements, files |
| `academics` | academic_sessions, terms, departments, programs, cohorts, courses | `AcademicStructureService` | entitlements, audit |
| `directory` | students, cohort_memberships, staff_profiles | `StudentService`, `StaffService` | identity, academics, entitlements |
| `examinations` | examinations, exam_cohorts, exam_papers, paper_assignments, paper_submissions | `ExamService`, `PaperWorkflow` | academics, directory, grading |
| `grading` | grading_schemes, grading_scheme_versions | `GradingEngine.compute(inputs, scheme_version)` (pure) | — |
| `marks` | mark_entries | `MarksService.upsert_many()`, `MarksQuery` | examinations, directory |
| `ingestion` | import_jobs, import_rows | `ImportService.start()`, `.validate()`, `.commit()` + pluggable `ImportProfile`s (students, courses, marks) | files, marks, directory |
| `results` | result_runs, student_exam_results, student_paper_results, approvals | `ResultProcessor.run()`, `ApprovalService` | marks, grading, examinations |
| `publishing` | publications, published_results, exam_statistics | `PublicationService.publish()/schedule()/withdraw()/correct()`, `StudentResultsQuery` | results, verification, documents, notifications |
| `documents` | marksheet_documents | `MarksheetRenderer.render(published_result)` | branding, files |
| `verification` | verification_records | `VerificationService.issue()/lookup()/revoke()` | — |
| `notifications` | notifications, notification_deliveries, notification_templates | `Notifier.notify(event, recipients)` | identity, branding |
| `analytics` | (reads results/publishing) | `ExamStatsBuilder`, `AnalyticsQuery` | results |
| `audit` | audit_logs | `AuditLog.record(event)` | — |
| `files` | files | `FileStore.put()/signed_url()` | — |
| `core` (shared kernel) | — | DB session/UoW, tenant context, config, errors, logging, cache, rate limit, jobs, ids, clock | — |

### Boundary rules (enforced in CI with `import-linter`)
1. A module may import only another module's **`api` package** (`module/api.py`: service interfaces + DTOs), never its models/repositories.
2. A module's tables are written only by that module. Other modules read via its query interface.
3. `core` imports no module. `grading` is pure (no I/O) → trivially unit-testable.
4. Dependency direction is acyclic (checked by the linter contract).

---

## 3. Layering inside each module

```
module/
  api.py            ← public interface: service protocols + Pydantic DTOs (what other modules may use)
  router.py         ← HTTP layer: FastAPI routes, request/response schemas, auth dependencies
  service.py        ← application services: use cases, transactions, authorization, audit, entitlements
  domain.py         ← domain logic & invariants (state machines, value objects) — no FastAPI, no SQL
  repository.py     ← persistence: SQLAlchemy queries, tenant-scoped base class
  models.py         ← SQLAlchemy table mappings
  jobs.py           ← background job handlers for this module
  tests/            ← unit (domain/service with fakes) + integration (repository/router with real PG)
```

Request flow: `router → (deps: tenant ctx, session, permission) → service (UoW transaction) → domain → repository → DB`; the service records audit events in the **same transaction** as the change.

### SOLID, concretely (good material for the SE report)
| Principle | Where it shows |
|---|---|
| **S**ingle responsibility | Router (HTTP) vs service (use case) vs repository (SQL) vs domain (rules). |
| **O**pen/closed | `GradingStrategy` registry: add `RelativeGradingStrategy` without touching existing strategies. `ImportProfile` for new import kinds. `NotificationChannel` for SMS/WhatsApp. |
| **L**iskov | All `GradingStrategy` implementations satisfy the same property-based test suite (e.g. monotonicity: more marks never yields a worse grade). |
| **I**nterface segregation | Small protocols: `FileStore`, `Clock`, `Mailer`, `Cache` — services depend only on what they use. |
| **D**ependency inversion | Services depend on protocols; infrastructure adapters (S3, SES, Redis) injected via FastAPI dependencies / a small container; tests inject fakes. |

Patterns used deliberately: Strategy (grading, import profiles, channels), State machine (exam/publication lifecycle), Unit of Work (transactions), Repository, Template Method (import pipeline stages), Outbox-style jobs (side effects after commit), CQRS-lite (published read model).

---

## 4. Request pipeline (middleware / dependencies, in order)

1. **Request ID** (`X-Request-ID` accepted from proxy or generated) → bound to structured logger.
2. **Tenant resolution** from `Host` → `TenantContext` (or platform/verify realm).
3. **Security headers**, CORS (no wildcard; only same-origin + configured hosts).
4. **Rate limiting** (per IP, per session, per tenant buckets; see [11](11-performance-architecture.md)).
5. **Session authentication** (cookie → hashed lookup → cache) → `Principal(user_id, tenant_id, roles)`; check `principal.tenant_id == ctx.tenant_id`.
6. **CSRF check** for state-changing methods (double-submit token header).
7. **Route dependency** `require(permission)` + entitlement gate `require_feature("custom_domain")`.
8. **Unit of Work**: open transaction, `set_config('app.tenant_id', ...)`, run service, commit; on error rollback.
9. **Error mapping** to RFC 9457 `application/problem+json`.

---

## 5. API design

- REST over HTTPS, JSON, versioned prefix **`/api/v1`**, OpenAPI 3.1 generated by FastAPI and committed to the repo (`openapi.json`) — diffed in CI to catch breaking changes. Frontend client generated from it (`openapi-typescript`).
- Resource naming: plural nouns; actions on state machines as sub-resources: `POST /exams/{id}/process`, `/approve`, `/publish`.
- **IDs never imply authorization** — every handler authorizes on `(tenant, principal, resource)`.
- Pagination: cursor-based (`?cursor=…&limit=50`, max 200).
- Filtering: explicit query params, no generic query language.
- Errors: `{"type": ".../errors/limit-exceeded", "title": "...", "status": 402, "detail": "...", "limit": "max_students", "current": 598, "requested": 10, "max": 600}`.
- Concurrency: `version` field / `If-Match` → `409 Conflict` on mismatch.
- Idempotency: `Idempotency-Key` header required on `POST /imports/{id}/commit`, `/publish`, `/process` — retried requests return the original response.
- Long operations return `202 Accepted` + job resource (`GET /jobs/{id}` for progress).

### Endpoint map (V1 shape; MVP subset marked ★)

**Public / auth** (tenant host)
```
GET  /api/v1/tenant/config ★              branding + public settings (cacheable, ETag)
POST /api/v1/auth/login ★                 → sets session cookie
POST /api/v1/auth/logout ★
POST /api/v1/auth/password/forgot ★ | /reset ★
POST /api/v1/auth/activate ★              enrollment no + activation code → set password
POST /api/v1/auth/invitations/{token}/accept ★
GET  /api/v1/me ★                         principal, roles, permissions, feature flags
```
**Student** (identity from session only)
```
GET /api/v1/me/results ★                  history (latest version of each publication)
GET /api/v1/me/results/latest ★
GET /api/v1/me/results/{publication_id} ★ 404 unless it's this student's
GET /api/v1/me/results/{publication_id}/stats ★
POST /api/v1/me/results/{publication_id}/marksheet-url ★ → short-lived signed URL
GET /api/v1/me/notifications ★ · POST /api/v1/me/notifications/{id}/read ★
```
**Institution admin / faculty**
```
/api/v1/admin/settings · /branding ★ · /staff ★ · /students ★ · /academic-sessions ★ · /terms ★
/api/v1/admin/departments · /programs ★ · /cohorts ★ · /courses ★ · /grading-schemes ★
/api/v1/admin/exams ★  /exams/{id}/papers ★  /exams/{id}/assignments ★
GET/PUT /api/v1/exams/{id}/papers/{pid}/marks ★     (faculty: assigned only)
POST /api/v1/exams/{id}/papers/{pid}/submit ★ | /return
POST /api/v1/imports ★ (multipart) · GET /imports/{id} ★ · GET /imports/{id}/rows?status=error ★
PATCH /api/v1/imports/{id}/mapping ★ · POST /imports/{id}/commit ★ · GET /imports/{id}/error-report.xlsx ★
POST /api/v1/admin/exams/{id}/results/process ★ (Idempotency-Key) · GET …/results ★ (run, stats, anomalies, approvals)
GET …/results/students ★ · GET …/results/students/{sid} ★ · POST …/results/discard
POST /api/v1/admin/exams/{id}/results/approve ★ | /reject | /revoke (re-auth)
POST /api/v1/exams/{id}/publications ★ (now | scheduled_at) · POST /publications/{id}/withdraw ★
POST /api/v1/exams/{id}/corrections · GET /publications/{id}/diff
GET  /api/v1/admin/analytics/exams/{id} ★ · GET /admin/audit-logs ★
GET  /api/v1/admin/subscription ★ · GET /admin/usage ★
GET  /api/v1/jobs/{id} ★
```
**Verification** (`verify.` host, anonymous, rate-limited)
```
GET /v/{code} ★ (server-rendered HTML)  ·  GET /api/v1/verify/{code} ★ (JSON)
```
**Platform** (`admin.` host)
```
/api/v1/platform/tenants ★ · /tenants/{id} ★ · /tenants/{id}/suspend ★ · /tenants/{id}/plan ★
/api/v1/platform/plans · /features · /tenants/{id}/overrides · /metrics/overview ★ · /health/deep ★
```
**Integration API (Pro, V1)** — API-key auth, scoped: `GET /api/v1/ext/students`, `/ext/publications`, webhooks `publication.published`.

Full reference: generated OpenAPI + [API docs page](api/README.md).

---

## 6. Background jobs

### Options compared
| | Celery + Redis/RabbitMQ | RQ / arq (Redis) | **PostgreSQL-backed queue** (e.g. Procrastinate, or a small `SELECT … FOR UPDATE SKIP LOCKED` table) |
|---|---|---|---|
| Extra infrastructure | Broker | Redis becomes critical | **None** |
| Transactional enqueue (job created iff the business transaction commits) | ❌ (needs outbox) | ❌ (needs outbox) | ✅ **same transaction** |
| Throughput | Very high | High | Hundreds–thousands of jobs/s — far above our needs |
| Async (asyncio) native | Partial | arq yes | Procrastinate yes |
| Scheduling (cron, delayed) | Beat | arq yes | Yes (periodic tasks, `schedule_at`) |
| **Verdict** | Overkill | Makes Redis a source of truth | ✅ **Chosen** |

**Decision:** PostgreSQL-backed queue. It removes the classic dual-write bug ("DB committed but job never enqueued" / "job ran but DB rolled back") and keeps Redis optional. Revisit only if job throughput becomes a measured bottleneck.

### Job catalogue
| Queue | Job | Trigger | Idempotency key |
|---|---|---|---|
| `imports` | `parse_and_validate_import(job_id)` | upload | job_id |
| `imports` | `commit_import(job_id)` | admin commit | job_id |
| `processing` | `process_results(exam_id, revision)` | admin | (exam_id, revision) |
| `pdf` | `render_marksheets(result_run_id, chunk)` | approval | (published_result, template_version) |
| `publishing` | `publish_scheduled(publication_id)` | `schedule_at` | publication_id |
| `notifications` | `fanout_publication(publication_id)`, `send_email_batch(ids)` | publish | delivery id |
| `maintenance` | purge sessions/tokens/import rows, reconcile usage counters, usage daily snapshot, audit partition rotation, backup verification | cron | date |
| `exports` | `export_tenant_data(tenant_id)` | admin | request id |

Rules: every job payload contains `tenant_id`; handlers set tenant context first; handlers are idempotent; retries with exponential backoff; per-tenant concurrency caps; dead-letter after N attempts with alert.

### Domain events (in-process)
Services emit events (`ResultsApproved`, `PublicationPublished`, `StudentCreated`, …) inside the transaction; subscribers either act synchronously in the same transaction (audit, verification record creation) or **enqueue jobs** (PDF, notifications) — never perform external I/O inside the transaction.

---

## 7. Grading engine (heart of correctness)

```python
class GradingStrategy(Protocol):
    code: str
    def validate_config(self, config: dict) -> GradingConfig: ...
    def grade_paper(self, paper: PaperSpec, marks: MarkInput, cfg: GradingConfig) -> PaperResult: ...
    def aggregate(self, papers: list[PaperResult], cfg: GradingConfig) -> ExamResult: ...

REGISTRY = {s.code: s for s in (PercentageBandsStrategy(), CreditGpaStrategy(), MarksOnlyStrategy())}
```
- Pure functions on `Decimal` with explicit rounding mode (`ROUND_HALF_UP`, configurable per scheme), no floats.
- Tested by example tables (golden files with hand-worked expectations in `backend/tests/fixtures/grading/`), and property-based tests (Hypothesis): monotonicity, bounds (0 ≤ percentage ≤ 100), absent handling, determinism and paper-order independence. The credit golden table is a generic CBCS-style scale used by the Thapar demo tenant — not Thapar's official policy (D25).
- Rules every strategy shares (implemented in `app/modules/grading/engine/strategies.py`): exempt papers are left out of every total; absent papers score nothing, never pass and show the scheme's `absent_grade`; withheld/malpractice on any paper withholds the exam; a missing component mark makes the paper and the exam `incomplete` (never computed from partial marks); grades come from the **rounded** percentage the student sees; division runs in a local `Decimal` context so results never depend on global state.
- The engine lives in `app/modules/grading/engine/` and an import-linter contract forbids it from importing the database, the web framework or any other module.

### 7.1 Result processing (implemented in Phase 9, `app/modules/results/`)
- **Request** (`POST …/results/process`, `results.process`): the exam must be *marks entry closed* or *processed*. Unsubmitted papers block it unless the request gives a reason, which is audited and listed as an anomaly. The request pins the latest version of the exam's grading scheme, inserts run *n* (`running`; a partial unique index allows one running run per exam) and queues `results.process` on the `processing` queue.
- **Job** (`results/service.py` `execute`): locks the exam row `FOR UPDATE` for the whole computation. Grid saves and import commits lock the same row, so marks can't change mid-run. It loads every input in four set-based queries (scheme version, papers, roster, marks) and computes in a worker thread with the pure engine (`results/compute.py`). It bulk-inserts `student_exam_results` and `student_paper_results`, then stores `input_hash` and `content_hash`, statistics and anomalies. Older completed runs become `stale`, and the exam moves to *processed*. Ungradable data, such as a mark above a lowered maximum, fails the run with the student named and writes nothing.
- **Determinism**: inputs are sorted before computing, so the same inputs in any order give identical rows and identical hashes. This is unit-tested (including a Hypothesis property) and checked end to end: processing twice gives the same hashes.
- **Staleness** (FR-10.3): administrators may still correct marks after processing. Any change runs `results/staleness.py` in the same transaction: completed runs become stale and the exam returns to *marks entry closed*. Approval recomputes the input hash, so a change that bypassed this, or a roster or paper change, still blocks approval.
- **Approval** (`results.approve`, re-auth required): it must name the latest run, which must be completed and not stale. In maker-checker mode (`tenant_settings.approval_mode` plus the plan's `maker_checker_approval`), the person who processed the run can't approve it. Approval appends an `approvals` row carrying the run's content hash, marks the run approved, moves the exam to *approved* and locks every paper. *Reject* records the decision and leaves the exam processed. *Revoke* (with a reason) returns the exam to processed and unlocks papers. *Discard* sets processed results aside and returns to marks entry.
- **Immutability**: the app role may only `SELECT, INSERT` on `student_exam_results`, `student_paper_results` and `approvals` (tested). Result columns use 3 decimal places, the engine's widest rounding, so stored values equal the hashed ones.
- **Not built yet**: marksheet pre-rendering on approval (FR-11.3) comes with PDFs in Phase 11; purging old runs' rows is a later retention job.

---

## 8. Configuration & secrets
- 12-factor: configuration via environment variables, parsed by `pydantic-settings` into a typed `Settings` object; app refuses to start if required secrets are missing or defaults are used in production.
- Secrets in the host's secret store (cloud secret manager or encrypted env files via SOPS for VM deployments); never in Git (gitleaks in CI).

## 9. Error handling & logging
- Domain errors are typed (`NotFound`, `PermissionDenied`, `LimitExceeded`, `InvalidState`, `ValidationFailed`, `Conflict`) and mapped centrally to HTTP problems; unexpected exceptions → 500 with request id, reported to Sentry, no internals leaked.
- Structured JSON logs (`structlog`) with `request_id`, `tenant_id`, `user_id` (opaque id), route, status, latency; **no marks, names, passwords or tokens in logs** (log scrubbing processor + tests).
