# ScoreCode — Step-by-Step Implementation Plan

> **Task 3 deliverable.** How to build ScoreCode from an empty repository to a deployed MVP with the Thapar demo tenant.
> Progress is tracked in **[CHECKLIST.md](CHECKLIST.md)** — every step below has a matching checkbox with the same ID (e.g. `P3.4`).
> Why this order: [19 Roadmap](19-roadmap.md). Architecture: [SAS](SAS.md).

## How to use this plan
1. Work phase by phase; inside a phase, steps are ordered by dependency.
2. A step is **done** only when its *Done when* criteria hold **and** its tests pass in CI. Then tick it in `CHECKLIST.md`.
3. Every step lands as one or more small PRs into `main` (trunk-based). Branch names: `p3.4-session-auth`.
4. Each phase ends with a **phase gate**: all steps ticked, CI green, demo works, docs updated.
5. If you change a design decision while implementing, update the relevant doc and the decision register ([18 §3](18-risks-and-decisions.md#3-decision-register--confirm-before-writing-production-code)) in the same PR.

**Definition of Done (applies to every step):** code + tests (unit and/or integration as relevant) + lint/type checks pass + audit events for writes + authorization & tenant-isolation tests for new endpoints + docs/OpenAPI updated + no secrets committed.

---

## Phase 0 — Product & architecture ✅
| ID | Step | Done when |
|---|---|---|
| P0.1 | Write product, business, architecture, security, performance, testing docs | Docs 01–20 merged |
| P0.2 | Write SRS, SAS and diagrams | Merged, diagrams render on GitHub |
| P0.3 | Write implementation plan & checklist | IMPLEMENTATION_PLAN.md + CHECKLIST.md merged |
| P0.4 | **Confirm decisions D1–D25** and answer open questions in [18](18-risks-and-decisions.md) | Decision statuses updated to Accepted/Changed |

---

## Phase 1 — Repository, tooling, CI, walking skeleton
**Goal:** `docker compose up` gives a running (empty) system; CI enforces quality from the first commit.

| ID | Step | Details | Done when |
|---|---|---|---|
| P1.1 | Monorepo skeleton | `backend/`, `frontend/`, `infra/`, `benchmarks/`, `docs/`; root `README`, `.editorconfig`, `.gitignore`, `Makefile`, `LICENSE` decision (D24) | Structure matches [SAS §7](SAS.md#7-development-view-41-development) |
| P1.2 | Backend project | `uv` project, FastAPI app factory, `pydantic-settings` config, `/livez` and `/readyz`, structlog JSON logging with request id | `curl /livez` → 200; unit test for config validation |
| P1.3 | Backend quality tooling | ruff (lint+format), mypy, pytest + pytest-asyncio, import-linter skeleton contract, pre-commit hooks | `make lint test` passes locally |
| P1.4 | Frontend workspace | pnpm workspace, `apps/tenant`, `apps/platform`, `packages/ui`, `packages/api-client`; Vite + React + TS strict, Tailwind, ESLint, Prettier, Vitest | `pnpm -r build` and `pnpm -r test` pass |
| P1.5 | Docker & compose | Multi-stage backend Dockerfile (non-root user), compose with proxy (Caddy), api, worker, postgres, redis (profile), minio, mailpit; `*.localhost` routing | `docker compose up` → `http://demo.localhost:8080/api/livez` 200 and SPA placeholder loads |
| P1.6 | CI pipeline v1 | GitHub Actions: backend lint/type/unit, frontend lint/type/test/build, gitleaks, pip-audit, pnpm audit, docker build | CI green on PR; branch protection on `main` |
| P1.7 | Job queue spike (D8) | Prototype Procrastinate vs minimal `SKIP LOCKED` queue: enqueue in transaction, worker, retry, schedule_at | ADR written with chosen option; spike code removed or promoted |
| P1.8 | ADRs | `docs/adr/0001`… for accepted decisions D1–D8 | ADR files merged |
| **Gate M1** | Walking skeleton | | Compose up works on a fresh clone in < 10 min following README |

---

## Phase 2 — Platform kernel: database, tenancy, RLS, audit, errors
**Goal:** the multi-tenant foundation every module will rely on.

| ID | Step | Details | Done when |
|---|---|---|---|
| P2.1 | DB roles & connection | Init SQL creating `scorecode_migrator`, `scorecode_app` (NOBYPASSRLS), `scorecode_platform`; async SQLAlchemy engine/pools per role; Alembic configured to use migrator | Integration test connects with each role; app role cannot `CREATE TABLE` |
| P2.2 | Conventions & base classes | UUIDv7 ids, timestamp mixins, naming convention for constraints, `version` column mixin, Decimal types | Unit tests for id generation ordering |
| P2.3 | Tenancy tables | `tenants`, `tenant_domains`, `tenant_settings` migrations; `TenantContext` | Migration up/down test |
| P2.4 | Tenant resolution middleware | Host → tenant (slug, custom domain), platform & verify realms, unknown host 404, suspended 403; in-process cache | Tests for each host type and suspended/unknown |
| P2.5 | Unit of Work + RLS context | Per-request transaction; `set_config('app.tenant_id', …, true)`; `TenantScopedRepository` base requiring context | Test: query without context errors; with context only own rows |
| P2.6 | RLS policy helper + coverage test | Migration helper `enable_tenant_rls(table)`; CI test asserts every table with `tenant_id` has RLS enabled + forced + policy | Test fails if a tenant table lacks RLS |
| P2.7 | Composite FK pattern | `UNIQUE(tenant_id,id)` + composite FK helper; sample tables proving cross-tenant FK insert fails | Integration test |
| P2.8 | Audit module | `audit_logs` (monthly partitions), `AuditLog.record()` in same transaction, app role INSERT/SELECT only | Test: rolled-back change leaves no audit row; app role cannot UPDATE/DELETE |
| P2.9 | Errors & API conventions | Typed domain errors → RFC 9457 problem+json; request id in responses; pagination helper; idempotency-key table & dependency | Unit + integration tests |
| P2.10 | Cache abstraction | `Cache` protocol with in-process + Redis implementations, tenant-key helper, circuit breaker | Test: Redis down → fallback works |
| P2.11 | Observability basics | Prometheus `/metrics` (internal port), request metrics middleware, Sentry init (env-gated), log scrubbing processor | Test: scrubber removes password/token fields |

---

## Phase 3 — Identity: authentication, sessions, RBAC
| ID | Step | Details | Done when |
|---|---|---|---|
| P3.1 | Users & roles schema | `users`, `user_roles`, `sessions`, `auth_tokens` with RLS | Migrations + RLS test pass |
| P3.2 | Password hashing | Argon2id service in threadpool with bounded semaphore; parameters configurable; measure ms/hash on dev machine and record in docs | Unit tests; measured value documented |
| P3.3 | Login/logout | `POST /auth/login`, `/logout`; session token (256-bit), hashed storage, `__Host-` cookie; session rotation; constant-time failure path with dummy hash | Integration tests incl. wrong tenant host → 401 |
| P3.4 | Session validation dependency | Cookie → session (cache → DB) → `Principal`; sliding expiry per user kind; tenant binding check | Tests: expired, revoked, cross-host replay |
| P3.5 | CSRF protection | Double-submit token for unsafe methods | Test: POST without token → 403 |
| P3.6 | RBAC | Permission map in code, `require(permission)` dependency, default-deny route test (every route declares permission or is explicitly public) | Authz matrix test scaffold green |
| P3.7 | Rate limiting | Token buckets (Redis Lua + local fallback); login per IP/account; 429 + Retry-After | Tests incl. Redis-down fallback |
| P3.8 | Password reset & invites | One-time tokens, emails via Mailer (Mailpit in dev), no account enumeration | Integration tests with Mailpit API |
| P3.9 | Platform realm auth | `platform_users`, TOTP (pyotp) mandatory, platform host only | Tests: platform login on tenant host fails |
| P3.10 | Tenant isolation suite v1 | Generated tests over all routes (ID swap, host swap, cookie replay) | Suite runs in CI as required check |
| P3.11 | Frontend auth | Tenant app login page (branding placeholder), session handling, role-based route trees, logout; platform console login with TOTP | Playwright: login/logout for each role |
| **Gate M2** | Secure multi-tenant core | | Two seeded tenants on two hosts; isolation suite green; live demo of blocked cross-tenant access |

---

## Phase 4 — Onboarding, plans & entitlements, basic branding, platform console v0
| ID | Step | Details | Done when |
|---|---|---|---|
| P4.1 | Plans & features schema + seed | `plans`, `features`, `plan_features`, `tenant_subscriptions`, `tenant_feature_overrides`, `tenant_usage_counters`; seed Free/Starter/Growth/Pro/Enterprise | Migration + seed idempotent |
| P4.2 | Entitlement service | Resolution (override → plan → default), status effects, caching with version bump, `require_feature` dependency, `check_limit` with row lock | Table-driven tests + race test |
| P4.3 | Tenant provisioning service | Single transaction: tenant, subscription, owner, settings, branding, default grading templates; used by sign-up **and** seed scripts | Integration test |
| P4.4 | Self-serve sign-up | Marketing/sign-up page, slug validation & reserved list, email verification, redirect to tenant host | E2E-1 passes |
| P4.5 | Basic branding | `tenant_branding` (name, logo upload to object storage, primary colour with contrast check); `GET /tenant/config`; frontend applies CSS variables before paint | E2E: two tenants render different branding |
| P4.6 | Onboarding checklist | Admin dashboard checklist driven by data (profile, structure, students, exam) | Component + API tests |
| P4.7 | Platform console v0 | Tenants list/detail, change plan, overrides, suspend/reactivate (platform role, audited in platform audit log) | E2E: suspend → tenant portal shows unavailable page |
| P4.8 | Seed tenants | `make seed`: Thapar (Enterprise-like), Demo School (Free), Demo Coaching (Growth) via provisioning service | Fresh clone + `make seed` shows 3 branded portals |
| **Gate M3** | Self-serve SaaS | | Sign-up to branded portal works end-to-end; platform console shows all tenants |
| P4.9 *(added 2026-10-08 at the owner's request; after Gate M3)* | Free caps and Pro trial | Free caps checked against the market; a 30-day Pro trial once per institution, using hashed identity signals; plan page, trial banner and plan comparison; console grant/revoke | Abuse tests (email variants, domain, device, soft-signal review, network), expiry and conversion tests, Playwright trial flow |

---

## Phase 5 — Academic structure
| ID | Step | Details | Done when |
|---|---|---|---|
| P5.1 | Schema | `academic_sessions`, `terms`, `departments`, `programs`, `cohorts`, `courses` with RLS, composite FKs, per-tenant unique codes | Migrations + constraint tests |
| P5.2 | Services & APIs | CRUD + archive, entitlement check for multiple departments, audit events | API tests + authz matrix entries |
| P5.3 | Admin UI | Sessions/terms, departments, programs, cohorts, courses screens with shared table/form components | Playwright create/edit/archive |
| P5.4 | Thapar & demo seed data | Realistic (synthetic) structure: departments, programs, cohorts, courses with credits | Seed script idempotent |

---

## Phase 6 — Directory & generic import framework
| ID | Step | Details | Done when |
|---|---|---|---|
| P6.1 | Students & staff schema | `students`, `cohort_memberships`, `staff_profiles`; `pg_trgm` search index | Migrations + tests |
| P6.2 | Student service | Create/edit/archive with `max_students` limit check & usage counter; search; cohort assignment | Tests incl. limit and race |
| P6.3 | Staff management | Invite staff, assign roles, `max_staff`/`max_admins` limits, owner transfer | Tests |
| P6.4 | Files module | Upload to object storage (tenant-prefixed keys), size/type/magic-byte checks, signed URLs | Security tests (wrong type, oversize) |
| P6.5 | Import framework core | `import_jobs`, `import_rows`, parsers (CSV encodings, XLSX read-only), mapping, rule engine, staging, annotated error XLSX (formula-injection safe), commit with idempotency | Golden-file tests on messy corpus |
| P6.6 | Student import profile | Rules: required fields, duplicates (file & DB), cohort exists, formats; commit respects limits | Tests + E2E import with errors → fix → commit |
| P6.7 | Student activation | Activation codes (hashed), printable code sheet (PDF/CSV) per cohort, activation flow UI | E2E: student activates and logs in |
| P6.8 | Admin UI | Students list/search/detail, staff list, import wizard (upload → map → review → commit) reused later for marks | Playwright |

---

## Phase 7 — Examinations & grading engine
| ID | Step | Details | Done when |
|---|---|---|---|
| P7.1 | Grading engine (pure) | `GradingStrategy` protocol; `PercentageBandsStrategy`, `MarksOnlyStrategy`, `CreditGpaStrategy` (SGPA); Decimal + rounding config | ≥ 90% branch coverage; Hypothesis properties (monotonic, bounded, deterministic) |
| P7.2 | Golden grading tables | Example tables: CBSE-style bands, a credit/SGPA policy modelled on Thapar's public grading rules, coaching marks-only with ranks | Golden tests pass |
| P7.3 | Grading schemes schema & UI | `grading_schemes`, immutable `grading_scheme_versions`, editor with preview calculator | Immutability trigger test |
| P7.4 | Exams schema | `examinations`, `exam_cohorts`, `exam_papers` (components JSON validated), `paper_assignments`, `paper_submissions` | Migrations + tests |
| P7.5 | Exam state machine | Transition table, guards, audit on each transition | Exhaustive transition tests |
| P7.6 | Exam setup UI | Exam workspace shell with Setup tab (papers, components, cohorts, grading, faculty assignment) | Playwright |

---

## Phase 8 — Marks entry & marks import
| ID | Step | Details | Done when |
|---|---|---|---|
| P8.1 | Mark entries schema & service | `mark_entries`, upsert-changed-only, optimistic locking, attendance codes, cell-level audit diffs | Tests incl. conflict 409 |
| P8.2 | Faculty scope enforcement | Assigned paper × cohort only; open state only | Authz matrix tests |
| P8.3 | Marks grid UI | Virtualised editable grid, keyboard navigation, paste from Excel, inline validation, autosave, conflict UI | Playwright: enter, paste, conflict |
| P8.4 | Paper submission workflow | Submit / return with comment / lock; completeness matrix for admins | Tests + UI |
| P8.5 | Marks import profile | All rules in [13 §4](13-result-ingestion.md#4-validation-rules) incl. name mismatch, total mismatch, fuzzy enrollment suggestions; long & wide formats | Rule tests + golden files |
| P8.6 | Pre-filled templates | Per exam/paper XLSX with roster and Excel data validation | Test opens generated file and checks validations |
| P8.7 | Import performance check | 10k-row file validation time measured (PT-5) and recorded | Result in `benchmarks/results/` |

---

## Phase 9 — Result processing, preview, approval
| ID | Step | Details | Done when |
|---|---|---|---|
| P9.1 | Results schema | `result_runs`, `student_exam_results`, `student_paper_results`, `approvals` | Migrations |
| P9.2 | Processing job | Load inputs set-based, compute via engine, bulk insert, `input_hash`, stale detection | Determinism test (run twice → identical) |
| P9.3 | Preview & anomalies | Distribution, pass %, anomalies (missing marks, all-max, absent-all, large deltas) API + UI | Tests + Playwright |
| P9.4 | Approval | Approve/reject with re-auth, content hash, input lock; single-step mode (maker-checker flag ready for V1) | Tests incl. stale run cannot be approved |
| P9.5 | Processing performance check | 8,000 × 6 measured (PT-6) | Result recorded |
| **Gate M4** | Results pipeline | | Import students & marks with errors → fix → process → preview → approve, on Thapar seed |

---

## Phase 10 — Publication, read model, student portal
| ID | Step | Details | Done when |
|---|---|---|---|
| P10.1 | Publication schema | `publications`, `published_results` (immutable grants + trigger), `exam_statistics`; covering index | Tests: app role cannot update snapshots |
| P10.2 | Snapshot builder | Payload schema (versioned), payload hash | Unit tests |
| P10.3 | Publish now / schedule / withdraw | Atomic publication; scheduled job; one-live-per-exam constraint; audit | Fault-injection test (rollback mid-way) |
| P10.4 | Student APIs | `/me/results`, `/latest`, `/{publication}`, `/stats` — identity from session only | Isolation tests (student X vs Y) |
| P10.5 | Student portal UI | Mobile-first dashboard, result detail, history, profile; bundle budget check in CI | Playwright on mobile viewport; budget < 150 KB gz |
| P10.6 | Load test harness | k6 scripts, synthetic data generator (`--students 8000`), metrics capture; run **scenario A and B baseline** | Baseline report in `benchmarks/results/` |
| **Gate M5a** | Result day (view) | | Publish → students view results; baseline numbers recorded (whatever they are) |

---

## Phase 11 — Marksheet PDFs & verification
| ID | Step | Details | Done when |
|---|---|---|---|
| P11.1 | Template system | Sandboxed Jinja HTML/CSS template, default template, tenant logo/name, QR code; external fetches blocked | Security test: template cannot fetch external URL |
| P11.2 | Render jobs | Pre-render at publication (ahead of go-live when scheduled; see docs/03 W9) in chunks of 50 to object storage, sha256, retries, `pdf` queue | Tests + timing measured per PDF |
| P11.3 | Download | Signed URL endpoint for own marksheet; admin download | Isolation tests |
| P11.4 | Verification records | 128-bit codes, status lifecycle tied to publication events | State tests |
| P11.5 | Verify page | Server-rendered page on verify host, masked data, status, hash, rate limit, noindex | E2E-4 |
| **Gate M5** | Result day (complete) | | Publish → view → download → scan QR → verified |

---

## Phase 12 — Notifications
| ID | Step | Details | Done when |
|---|---|---|---|
| P12.1 | In-app notifications | Schema, bulk fan-out on publish, inbox API & UI, unread count | Tests |
| P12.2 | Email channel | Provider adapter (SES/Postmark), templates (link only, no marks), batching, retries, delivery tracking; SPF/DKIM/DMARC documented | Integration with Mailpit; failure retry test |
| P12.3 | Notification preferences | Tenant setting to email on publish; student opt-out of non-essential | Tests |

---

## Phase 13 — Analytics (basic) & audit viewer
| ID | Step | Details | Done when |
|---|---|---|---|
| P13.1 | Exam statistics snapshot | Computed at publication (pass %, distribution, mean/median/stdev per paper) | Unit tests vs hand-computed fixtures |
| P13.2 | Admin analytics UI | Charts (lazy-loaded), per-paper drill-down | Playwright |
| P13.3 | Student stats view | Only tenant-permitted aggregates | Tests |
| P13.4 | Audit log viewer | Filter by entity/actor/date, before→after diff rendering | Tests + UI |
| P13.5 | Platform metrics overview | Tenants by plan/status, students, publications, errors, p95, cache hit rate, queue depth in console | E2E |

---

## Phase 14 — Performance engineering (measure → optimise → re-measure)
| ID | Step | Details | Done when |
|---|---|---|---|
| P14.1 | Full scenario runs | Scenarios A, B, C (D if feasible) × (pre-authenticated, cold login) per [11 §4](11-performance-architecture.md#4-benchmark-plan-scientifically-valid) on a documented environment | Reports with p50/p95/p99, RPS, errors, resources |
| P14.2 | Bottleneck analysis | `pg_stat_statements`, EXPLAIN ANALYZE of hot queries, profiling (py-spy), tracing in staging | Written analysis identifies top 3 bottlenecks |
| P14.3 | Targeted optimisations | Only for measured bottlenecks (e.g. Argon2 params & semaphore, pool sizes, PgBouncer, result-payload cache, worker counts) — one change at a time | Before/after report per change |
| P14.4 | Horizontal scaling demonstration | 1 vs 2 API nodes under the same scenario | Report (NFR-16) |
| P14.5 | Failure-under-load tests | Redis down, worker kill, DB restart during scenario B | Results recorded per [15 §6](15-testing-strategy.md#6-failure-testing) |

---

## Phase 15 — Security review & hardening
| ID | Step | Details | Done when |
|---|---|---|---|
| P15.1 | Threat model review | Update STRIDE table with as-built system | Doc updated |
| P15.2 | ASVS L2 checklist | Walk through relevant controls; file issues for gaps; fix critical/high | Checklist committed with status |
| P15.3 | Security test completion | Upload attacks, CSRF, headers, mass assignment, enumeration, log scrubbing | Suites green |
| P15.4 | DAST & scans | ZAP baseline on staging; Trivy images; dependency audit clean of high/critical | Reports saved |
| P15.5 | Admin protections | TOTP for owners, re-auth for sensitive actions | Tests |

---

## Phase 16 — Deployment, backups, monitoring, runbooks
| ID | Step | Details | Done when |
|---|---|---|---|
| P16.1 | Domains & DNS | Register domains (D23), Cloudflare, wildcard DNS, wildcard certificate (DNS-01) | `https://thapar.<domain>` resolves with valid TLS |
| P16.2 | Demo/production environment | VM (demo) or small-prod topology, `docker-compose.prod.yml`, secrets management, non-root containers | Smoke tests pass on deployed env |
| P16.3 | CD pipeline | Build → GHCR → staging auto deploy → prod on tag with approval; migrations job | A tagged release deploys without manual SSH |
| P16.4 | Backups & restore drill | Nightly encrypted dump to second storage; documented restore; first drill executed | Drill log with measured RTO |
| P16.5 | Monitoring & alerts | Metrics dashboards, Sentry, uptime checks, alert rules from [14 Q](14-deployment-and-operations.md#alerts-start-small-actionable-only) | Test alert received |
| P16.6 | Runbooks | DB restore, Redis outage, stuck publication, rollback, incident template | `docs/runbooks/` merged |

---

## Phase 17 — Thapar & demo tenants, documentation, presentation (MVP complete)
| ID | Step | Details | Done when |
|---|---|---|---|
| P17.1 | Thapar tenant polish | Branding (with permission — D25), realistic synthetic data across 2–3 sessions, credit/SGPA scheme, scheduled publication scenario | Demo script runs end-to-end |
| P17.2 | Demo School & Demo Coaching | Free and Growth plans showing limits and feature differences | Demo script |
| P17.3 | User documentation | Admin guide, faculty guide, student guide (`docs/user-guide/`) | Reviewed |
| P17.4 | Test & benchmark reports | Final test report with traceability, coverage, isolation results; final benchmark report | `docs/reports/` merged |
| P17.5 | Presentation | Slides + live demo script: multi-tenancy, isolation attempt, import errors, publish, verify, platform console, measured numbers | Dry run completed |
| **Gate M6** | **MVP** | | All MVP checklist items ticked |

---

## Phase 18+ — V1 (commercial launch) backlog
Ordered by value/effort; each becomes a mini-phase with its own checklist section when started:
1. Maker–checker approval · 2. Corrections with diff & versioned re-publication · 3. Custom domains (Caddy on-demand TLS) · 4. Razorpay billing & GST invoices · 5. Full branding & template library · 6. Advanced analytics · 7. Tenant data export & closure · 8. Support sessions · 9. API keys & webhooks · 10. SSE progress · 11. Audit hash chain · 12. CGPA, grace marks, supplementary exams, ranks.
