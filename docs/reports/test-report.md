# Test report (P17.4) — 2026-10-09

What is tested, how, what it found, and what is not tested. The numbers below were measured on this date
(local runs, and the CI runs named). Strategy: [15 Testing](../15-testing-strategy.md). Requirements:
[SRS](../SRS.md).

## 1. Suites
| Suite | Where | Tests | Runs on | Result |
|---|---|---|---|---|
| Backend unit | `backend/tests/unit` (grading engine, golden tables, properties, import engine, snapshots, codes, permissions…) | 319 | every push (CI) | pass |
| Backend integration | `backend/tests/integration`, real PostgreSQL, Redis, object storage and mail | 200 | every push (CI) | pass (4 skipped locally without WeasyPrint; required and run in CI) |
| Backend total | | **515 passed, 4 skipped** (local, 2026-10-09) | | |
| Frontend unit and component | Vitest + Testing Library | **80** (tenant 67, UI library 7, API client 4, site 2) | every push | pass |
| End-to-end | Playwright against the full container stack (`frontend/e2e`) | **36** in the regular run (32 + 4 accessibility) | every push | pass (CI ed958d9: all jobs; a11y spec added in 80d3e53) |
| Demo script | `e2e/demo.spec.ts` on `scorecode seed --with-history` | 8 | `demo.yml` | **8/8 passed** (run 37867772295, commit d458aad) |
| Load | k6 scenarios A and B, cold and pre-authenticated (`benchmarks/k6`) | — | `perf.yml` (manual) | [benchmark report](benchmark-report.md) |
| Failure injection | Redis stop, PostgreSQL restart, worker SIGKILL under load | 3 scenarios | `perf.yml` `chaos=` | all pass |
| Operations | alert delivered end to end; backup → destroy → restore | 2 jobs | `ops.yml` (weekly and on change) | pass (run 37847430260) |
| Deploy rehearsal | production compose: install, upgrade with backup, a broken release rolls back by itself | 1 job | `release.yml` | pass (runs 37846562794, 37847429961) |
| Security scans | Bandit, pip-audit, pnpm audit, gitleaks, Trivy (fs and image), ZAP baseline | — | CI and `dast.yml` | pass; ZAP: no High ([dispositions](../security/zap-baseline-2026-10-08.md)) |

## 2. Coverage (backend, line + branch, whole suite, 2026-10-09)
**81% overall** (12,299 statements, 2,476 branches). By module:

| Module | Coverage | | Module | Coverage |
|---|---|---|---|---|
| core (db, cache, jobs, security, …) | 90% | | publishing | 88% |
| verification | 93% | | results | 87% |
| grading (engine gate: ≥ 90% branches in CI, NFR-10) | 89% (module), gate met | | ingestion | 84% |
| documents (marksheets) | 82% | | entitlements | 81% |
| identity | 73% | | marks | 65% |

- **Lowest:** the marks module (65%). The mark sheet's edit paths are exercised more by E2E (grid
  entry, conflicts, import, submit and return) than by integration tests, and E2E isn't counted here.
- **Coverage is tracked, not gated,** except the grading engine (docs/14 §P). The platform console app
  has no unit tests; its flows are covered by E2E only (sign-in with TOTP, suspension, plans).

## 3. Tenant isolation (NFR-1)
The isolation suite (`test_isolation.py`) is generated from the live route table, so a new endpoint
is covered without anyone remembering to add it. A route with a path id the suite can't provision fails
the suite. It checks four things:
1. **ID swap:** A's owner calls every tenant route with B's ids. Every call gets 404, and B's data is
   unchanged.
2. **Host swap and cookie replay:** A's session on B's host gets 401 on every tenant route.
3. **Forged tenant ids** in queries and bodies are ignored or rejected.
4. **Database layer:** in A's context, every tenant table returns 0 rows of B's and rejects writes for
   B.

Other layers of the same defence, each tested:
- Forced RLS that **fails closed** without context (`test_kernel.py`).
- Composite foreign keys across tenant boundaries (`test_kernel.py`).
- The ORM's criteria.
- The read cache's keys (`test_read_cache.py`).
- Background jobs' tenant context (`test_kernel.py`).
- The restore drill's isolation fingerprint (RLS flags, policies and grants identical after a restore).

## 4. Authorization (FR-2.9)
`test_authz_matrix.py` sweeps every route against every role, comparing with the committed
`permission_matrix.json`. A permission change shows up as a reviewed diff in that file.

## 5. Mutation checks (do the tests catch the bug they're for?)
For every security- or correctness-critical change, the code was deliberately broken and the tests
were required to fail. Recorded in commit messages and the checklist's work log. Examples:

| Mutant | Caught by |
|---|---|
| RLS `set_config` hook removed | 11 kernel tests |
| Tenant bound eagerly (no lazy transaction) | `test_a_unit_of_work_takes_no_connection_until_its_first_statement` |
| Pooled connections never pinged / pinged every time | 2 tests each (`test_outages.py`) |
| Metrics not aggregated across workers / not set up by the CLI | `test_metrics_multiprocess.py` |
| Operator job functions granted to the app role | `test_operators_list_and_retry_dead_jobs_and_the_app_role_cannot` |
| Verify page with an inline `style=` | `test_the_public_verify_page` (hash-pinned CSP) |
| Scheduled verification codes made verifiable, names unmasked, revocation ignored, a PDF fetcher that allows URLs (P11) | marksheet and verification suites |
| A non-monotonic grade band (P7) | Hypothesis property tests |

## 6. Traceability (SRS → evidence)
| Requirement group | Tests (backend unless noted) | E2E |
|---|---|---|
| F1 Tenant onboarding | `test_entitlements.py`, `test_trials.py`, `test_seed.py` | `signup.spec`, `plans.spec` |
| F2 Identity & access | `test_auth.py`, `test_mfa.py`, `test_activation.py`, `test_authz_matrix.py`, `test_isolation.py`, `test_breached_passwords.py` | `auth.spec`, `tenancy.spec` |
| F3 Entitlements | `test_entitlements.py` (race-safe limits), `test_trials.py` (one trial per institution) | `plans.spec` |
| F4 Branding | `test_admin_flows.py` | `tenancy.spec` (two tenants, one build) |
| F5 Academic structure | `test_academics.py` | `academics.spec` |
| F6 Directory | `test_directory.py`, `test_imports.py`, `test_import_engine.py`, `test_import_golden.py` | `students.spec` |
| F7 Examinations & grading | `test_exams.py`, `test_exam_states.py`, `test_grading_*.py` (engine, golden, properties) | `exams.spec`, `grading.spec` |
| F8 Marks capture | `test_marks.py` | `marks.spec` |
| F9 Import | `test_marks_import.py`, `test_import_marks_golden.py`, upload-attack cases in `test_imports.py` | `marks-import.spec`, `results.spec` |
| F10 Processing | `test_results.py`, `test_results_compute.py`, `test_sql_scale.py` | `results.spec` |
| F11 Approval | `test_results.py` (re-auth, maker-checker, stale runs) | `results.spec` |
| F12 Publication | `test_publishing.py`, `test_snapshot.py`, `test_idempotency.py` | `publish.spec`, `demo.spec` |
| F13 Student portal | `test_publishing.py`, `test_read_cache.py`, `test_analytics.py` | `publish.spec`, `analytics.spec` |
| F14 Marksheets | `test_marksheets.py`, `test_marksheet_render.py` (real WeasyPrint in CI) | `verify.spec` |
| F15 Verification | `test_marksheets.py`, `test_verification_codes.py` | `verify.spec`, `edge.spec` |
| F16 Notifications | `test_notifications.py` | `publish.spec` (bell) |
| F17 Analytics | `test_analytics.py`, `test_results_compute.py` (hand-worked statistics) | `analytics.spec` |
| F18 Audit | `test_audit.py` (route-level: every state change audited, NFR-11) | `audit` component tests |
| F19 Platform administration | `test_admin_flows.py`, `test_isolation.py` (platform realm) | `tenancy.spec` (suspension) |
| F20 Export & offboarding (V1) | not built; manual procedure in [runbooks](../runbooks/tenant-offboarding.md) | — |

| NFR | Status | Evidence |
|---|---|---|
| NFR-1 Isolation | **Met** | §3 |
| NFR-2 ASVS L2 | **Met for MVP scope** | [checklist](../security/asvs-l2.md); TLS and HSTS in production not verified (no server yet) |
| NFR-3 Student read p95 < 150 ms server-side | **Not yet demonstrated at scenario B** | End to end (k6, through the proxy, on the shared machine) `latest` p95 is 240–281 ms at 1,000 users. Server-side duration is now recorded per run (`perf.yml`, `timeline.py --latency`); the next run gives the figure |
| NFR-4 Login p95 < 500 ms | **Met at scenario A**; at B, logins queue behind saturated workers | benchmark report |
| NFR-5 10,000-row validation < 60 s | **Met** (1.6 s CSV, 2.7 s XLSX) | benchmarks/results/2026-10-07-marks-import-10k.md |
| NFR-6 8,000 × 6 processing < 2 min | **Met** (9.6 s) | benchmarks/results/2026-10-07-result-processing-8000x6.md |
| NFR-7 5xx < 0.1% at publication load | **Met at 1,000 users** (0.00% after P14.3); above capacity the API answers retryable 503s by design | benchmark report |
| NFR-8 Availability | **Not verified**: needs production and uptime monitoring | — |
| NFR-9 RPO ≤ 5 min, RTO ≤ 4 h | **RTO measured: 57 s** (drill, 8,000 students); RPO 24 h with nightly dumps, 5 min needs managed PITR (production) | [drill log](../runbooks/drills/README.md) |
| NFR-10 Grading correctness | **Met** | golden tables, properties, ≥ 90% branch gate |
| NFR-11 Auditability | **Met** | `test_audit.py` route sweep |
| NFR-12 Student in ≤ 2 taps, 360 px | **Met** | E2E mobile project (Pixel 7), `publish.spec` on a 390 px phone |
| NFR-13 WCAG 2.1 AA | **Automated part met; manual review not done** | `e2e/a11y.spec.ts`: WCAG 2.1 A/AA axe checks on 15 screens (public, student portal at 360 px, eight exam-office screens, console) plus `auth.spec` and `verify.spec`. Found and fixed: an unlabelled file input, off-screen save bars reachable by Tab, unnamed selects (80d3e53) |
| NFR-14 Maintainability | **Met** | import-linter contracts, ruff, mypy, ESLint, tsc gates |
| NFR-15 Portability | **Met** | containers only; S3/SMTP behind adapters |
| NFR-16 Scalability | **Stateless and scalable; demonstrated within one machine's limits** | benchmark report §4 |
| NFR-17 Privacy | **Met in code** (no PII in logs, tested); export and deletion are a manual procedure until V1 | `test_security_hardening.py`, runbook |
| NFR-18 Cost | Estimate only | [16 Cost model](../16-cost-model.md) |
| NFR-19 Observability | **Met** | metrics (multiprocess-correct), alert pipeline tested end to end (101 s to email) |
| NFR-20 Student JS < 150 KB gz | **Met** (CI budget) | `frontend/scripts/check-budget.mjs` |

## 7. Bugs the tests found (selected)
- **Load tests:**
  - A client-address bug: 601 of 1,000 cold sign-ins got 429, because limits used the wrong
    `X-Forwarded-For` entry.
  - A pool deadlock.
  - Pool timeouts and database outages surfacing as 500.
- **Integration tests:** a 10,000-row IN-list failure in imports.
- **The DAST analysis:** the edge overwrote the verify page's `Referrer-Policy`, and SPA HTML wasn't
  revalidated after deploys.
- **The restore drill:** forced RLS blocked `pg_restore` twice, as described in the drill log.
- **The deploy rehearsal:** a production template missing `SCORECODE_EXPOSE_DOCS=false`, caught by the
  app refusing to start.
- **Writing the runbooks:** rotating the secret key would have locked out every two-step sign-in, so
  `scorecode reencrypt-secrets` was added.

## 8. Not tested, or not verifiable here
- A real deployment: domain, TLS from Cloudflare, uptime from two regions (P16.1–P16.3, NFR-8).
- WCAG manual review (NFR-13); multi-region failover; email deliverability from a real provider (SPF,
  DKIM, DMARC).
- Network latency or loss to the database (Toxiproxy), and object storage outages.
