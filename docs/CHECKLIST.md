# ScoreCode — Implementation Checkpoints

> **Task 3 deliverable.** Tick a box **only when the step is implemented AND its tests pass in CI.** Each ID matches a step in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), where the details live.
> This file is your save point: after any break, you resume from here instead of starting over.

## ▶ Resume protocol (do this at the start of every work session)
1. `git pull` on `main` (and on your feature branch if one is open).
2. Read **Current position** below, then find the **first unticked box** in the lowest-numbered phase — that is your next step.
3. Open the same ID in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for details and the Definition of Done.
4. Check the **Work log** (bottom) for notes left last time (half-finished work, blockers, decisions).
5. Run `make test` (once Phase 1 exists) to confirm the tree is green before continuing.

## ✅ Ticking rules
- `[x]` only when: code merged to `main` · tests for it pass in CI · audit/authz/isolation tests added where relevant · docs updated.
- Partially done? Leave it `[ ]`, and add a line to the Work log (e.g. `P6.5 — parsers done, rule engine pending`).
- If a step turns out to be unnecessary, change it to `- [~] ~~step~~ (dropped: reason, date)` — never silently delete.
- A 🚩 gate is ticked only when every box above it in that phase is ticked and the gate demo works.
- Update **Current position** in the same commit as the tick.

## 📍 Current position
| | |
|---|---|
| Current phase | **Phase 10 — Publication, read model, student portal** (Phases 0–9 complete; Gates M1–M4 passed) |
| Next step | **Phase 10**: P10.1 publication schema and P10.2 snapshot builder in progress; then publish/schedule/withdraw, student APIs, portal, k6 baseline |
| Last updated | 2026-10-07 |
| Open blockers | None for code. D23 (domain), D24 (licence), D25 (Thapar branding) await owner action — safe defaults in place |

## 📊 Phase progress
| Phase | Name | Steps | Done |
|---|---|---|---|
| 0 | Product & architecture | 4 | 4 |
| 1 | Repository, tooling, CI, walking skeleton | 8 | 8 |
| 2 | Platform kernel: database, tenancy, RLS, audit, errors | 11 | 11 |
| 3 | Identity: authentication, sessions, RBAC | 11 | 11 |
| 4 | Onboarding, plans & entitlements, basic branding, platform console v0 | 8 | 8 |
| 5 | Academic structure | 4 | 4 |
| 6 | Directory & generic import framework | 8 | 8 |
| 7 | Examinations & grading engine | 6 | 6 |
| 8 | Marks entry & marks import | 7 | 7 |
| 9 | Result processing, preview, approval | 5 | 5 |
| 10 | Publication, read model, student portal | 6 | 0 |
| 11 | Marksheet PDFs & verification | 5 | 0 |
| 12 | Notifications | 3 | 0 |
| 13 | Analytics (basic) & audit viewer | 5 | 0 |
| 14 | Performance engineering (measure → optimise → re-measure) | 5 | 0 |
| 15 | Security review & hardening | 5 | 0 |
| 16 | Deployment, backups, monitoring, runbooks | 6 | 0 |
| 17 | Thapar & demo tenants, documentation, presentation (MVP complete) | 5 | 0 |

_Update the Done column when you tick boxes (or run `grep -c "\- \[x\]" docs/CHECKLIST.md` for the overall count)._

## ☑ Checkpoints

### Phase 0 — Product & architecture ✅

- [x] **P0.1** Write product, business, architecture, security, performance, testing docs · Done when: Docs 01–20 merged
- [x] **P0.2** Write SRS, SAS and diagrams · Done when: Merged, diagrams render on GitHub
- [x] **P0.3** Write implementation plan & checklist · Done when: IMPLEMENTATION_PLAN.md + CHECKLIST.md merged
- [x] **P0.4** **Confirm decisions D1–D25** and answer open questions in [18](18-risks-and-decisions.md) · Done when: Decision statuses updated to Accepted/Changed

### Phase 1 — Repository, tooling, CI, walking skeleton

- [x] **P1.1** Monorepo skeleton · Done when: Structure matches [SAS §7](SAS.md#7-development-view-41-development)
- [x] **P1.2** Backend project · Done when: `curl /livez` → 200; unit test for config validation
- [x] **P1.3** Backend quality tooling · Done when: `make lint test` passes locally
- [x] **P1.4** Frontend workspace · Done when: `pnpm -r build` and `pnpm -r test` pass
- [x] **P1.5** Docker & compose · Done when: `docker compose up` → `http://demo.localhost:8080/api/livez` 200 and SPA placeholder loads
- [x] **P1.6** CI pipeline v1 · Done when: CI green on PR; branch protection on `main`
- [x] **P1.7** Job queue spike (D8) · Done when: ADR written with chosen option; spike code removed or promoted
- [x] **P1.8** ADRs · Done when: ADR files merged
- [x] 🚩 **Gate M1 — Walking skeleton** · Done when: Compose up works on a fresh clone in < 10 min following README

### Phase 2 — Platform kernel: database, tenancy, RLS, audit, errors

- [x] **P2.1** DB roles & connection · Done when: Integration test connects with each role; app role cannot `CREATE TABLE`
- [x] **P2.2** Conventions & base classes · Done when: Unit tests for id generation ordering
- [x] **P2.3** Tenancy tables · Done when: Migration up/down test
- [x] **P2.4** Tenant resolution middleware · Done when: Tests for each host type and suspended/unknown
- [x] **P2.5** Unit of Work + RLS context · Done when: Test: query without context errors; with context only own rows
- [x] **P2.6** RLS policy helper + coverage test · Done when: Test fails if a tenant table lacks RLS
- [x] **P2.7** Composite FK pattern · Done when: Integration test
- [x] **P2.8** Audit module · Done when: Test: rolled-back change leaves no audit row; app role cannot UPDATE/DELETE
- [x] **P2.9** Errors & API conventions · Done when: Unit + integration tests
- [x] **P2.10** Cache abstraction · Done when: Test: Redis down → fallback works
- [x] **P2.11** Observability basics · Done when: Test: scrubber removes password/token fields

### Phase 3 — Identity: authentication, sessions, RBAC

- [x] **P3.1** Users & roles schema · Done when: Migrations + RLS test pass
- [x] **P3.2** Password hashing · Done when: Unit tests; measured value documented
- [x] **P3.3** Login/logout · Done when: Integration tests incl. wrong tenant host → 401
- [x] **P3.4** Session validation dependency · Done when: Tests: expired, revoked, cross-host replay
- [x] **P3.5** CSRF protection · Done when: Test: POST without token → 403
- [x] **P3.6** RBAC · Done when: Authz matrix test scaffold green
- [x] **P3.7** Rate limiting · Done when: Tests incl. Redis-down fallback
- [x] **P3.8** Password reset & invites · Done when: Integration tests with Mailpit API
- [x] **P3.9** Platform realm auth · Done when: Tests: platform login on tenant host fails
- [x] **P3.10** Tenant isolation suite v1 · Done when: Suite runs in CI as required check
- [x] **P3.11** Frontend auth · Done when: Playwright: login/logout for each role
- [x] 🚩 **Gate M2 — Secure multi-tenant core** · Done when: Two seeded tenants on two hosts; isolation suite green; live demo of blocked cross-tenant access

### Phase 4 — Onboarding, plans & entitlements, basic branding, platform console v0

- [x] **P4.1** Plans & features schema + seed · Done when: Migration + seed idempotent
- [x] **P4.2** Entitlement service · Done when: Table-driven tests + race test
- [x] **P4.3** Tenant provisioning service · Done when: Integration test
- [x] **P4.4** Self-serve sign-up · Done when: E2E-1 passes
- [x] **P4.5** Basic branding · Done when: E2E: two tenants render different branding
- [x] **P4.6** Onboarding checklist · Done when: Component + API tests
- [x] **P4.7** Platform console v0 · Done when: E2E: suspend → tenant portal shows unavailable page
- [x] **P4.8** Seed tenants · Done when: Fresh clone + `make seed` shows 3 branded portals
- [x] 🚩 **Gate M3 — Self-serve SaaS** · Done when: Sign-up to branded portal works end-to-end; platform console shows all tenants

### Phase 5 — Academic structure

- [x] **P5.1** Schema · Done when: Migrations + constraint tests
- [x] **P5.2** Services & APIs · Done when: API tests + authz matrix entries
- [x] **P5.3** Admin UI · Done when: Playwright create/edit/archive
- [x] **P5.4** Thapar & demo seed data · Done when: Seed script idempotent

### Phase 6 — Directory & generic import framework

- [x] **P6.1** Students & staff schema · Done when: Migrations + tests
- [x] **P6.2** Student service · Done when: Tests incl. limit and race
- [x] **P6.3** Staff management · Done when: Tests
- [x] **P6.4** Files module · Done when: Security tests (wrong type, oversize)
- [x] **P6.5** Import framework core · Done when: Golden-file tests on messy corpus
- [x] **P6.6** Student import profile · Done when: Tests + E2E import with errors → fix → commit
- [x] **P6.7** Student activation · Done when: E2E: student activates and logs in
- [x] **P6.8** Admin UI · Done when: Playwright

### Phase 7 — Examinations & grading engine

- [x] **P7.1** Grading engine (pure) · Done when: ≥ 90% branch coverage; Hypothesis properties (monotonic, bounded, deterministic)
- [x] **P7.2** Golden grading tables · Done when: Golden tests pass
- [x] **P7.3** Grading schemes schema & UI · Done when: Immutability trigger test
- [x] **P7.4** Exams schema · Done when: Migrations + tests
- [x] **P7.5** Exam state machine · Done when: Exhaustive transition tests
- [x] **P7.6** Exam setup UI · Done when: Playwright

### Phase 8 — Marks entry & marks import

- [x] **P8.1** Mark entries schema & service · Done when: Tests incl. conflict 409
- [x] **P8.2** Faculty scope enforcement · Done when: Authz matrix tests
- [x] **P8.3** Marks grid UI · Done when: Playwright: enter, paste, conflict
- [x] **P8.4** Paper submission workflow · Done when: Tests + UI
- [x] **P8.5** Marks import profile · Done when: Rule tests + golden files
- [x] **P8.6** Pre-filled templates · Done when: Test opens generated file and checks validations
- [x] **P8.7** Import performance check · Done when: Result in `benchmarks/results/`

### Phase 9 — Result processing, preview, approval

- [x] **P9.1** Results schema · Done when: Migrations
- [x] **P9.2** Processing job · Done when: Determinism test (run twice → identical)
- [x] **P9.3** Preview & anomalies · Done when: Tests + Playwright
- [x] **P9.4** Approval · Done when: Tests incl. stale run cannot be approved
- [x] **P9.5** Processing performance check · Done when: Result recorded
- [x] 🚩 **Gate M4 — Results pipeline** · Done when: Import students & marks with errors → fix → process → preview → approve, on Thapar seed

### Phase 10 — Publication, read model, student portal

- [ ] **P10.1** Publication schema · Done when: Tests: app role cannot update snapshots
- [ ] **P10.2** Snapshot builder · Done when: Unit tests
- [ ] **P10.3** Publish now / schedule / withdraw · Done when: Fault-injection test (rollback mid-way)
- [ ] **P10.4** Student APIs · Done when: Isolation tests (student X vs Y)
- [ ] **P10.5** Student portal UI · Done when: Playwright on mobile viewport; budget < 150 KB gz
- [ ] **P10.6** Load test harness · Done when: Baseline report in `benchmarks/results/`
- [ ] 🚩 **Gate M5a — Result day (view)** · Done when: Publish → students view results; baseline numbers recorded (whatever they are)

### Phase 11 — Marksheet PDFs & verification

- [ ] **P11.1** Template system · Done when: Security test: template cannot fetch external URL
- [ ] **P11.2** Render jobs · Done when: Tests + timing measured per PDF
- [ ] **P11.3** Download · Done when: Isolation tests
- [ ] **P11.4** Verification records · Done when: State tests
- [ ] **P11.5** Verify page · Done when: E2E-4
- [ ] 🚩 **Gate M5 — Result day (complete)** · Done when: Publish → view → download → scan QR → verified

### Phase 12 — Notifications

- [ ] **P12.1** In-app notifications · Done when: Tests
- [ ] **P12.2** Email channel · Done when: Integration with Mailpit; failure retry test
- [ ] **P12.3** Notification preferences · Done when: Tests

### Phase 13 — Analytics (basic) & audit viewer

- [ ] **P13.1** Exam statistics snapshot · Done when: Unit tests vs hand-computed fixtures
- [ ] **P13.2** Admin analytics UI · Done when: Playwright
- [ ] **P13.3** Student stats view · Done when: Tests
- [ ] **P13.4** Audit log viewer · Done when: Tests + UI
- [ ] **P13.5** Platform metrics overview · Done when: E2E

### Phase 14 — Performance engineering (measure → optimise → re-measure)

- [ ] **P14.1** Full scenario runs · Done when: Reports with p50/p95/p99, RPS, errors, resources
- [ ] **P14.2** Bottleneck analysis · Done when: Written analysis identifies top 3 bottlenecks
- [ ] **P14.3** Targeted optimisations · Done when: Before/after report per change
- [ ] **P14.4** Horizontal scaling demonstration · Done when: Report (NFR-16)
- [ ] **P14.5** Failure-under-load tests · Done when: Results recorded per [15 §6](15-testing-strategy.md#6-failure-testing)

### Phase 15 — Security review & hardening

- [ ] **P15.1** Threat model review · Done when: Doc updated
- [ ] **P15.2** ASVS L2 checklist · Done when: Checklist committed with status
- [ ] **P15.3** Security test completion · Done when: Suites green
- [ ] **P15.4** DAST & scans · Done when: Reports saved
- [ ] **P15.5** Admin protections · Done when: Tests

### Phase 16 — Deployment, backups, monitoring, runbooks

- [ ] **P16.1** Domains & DNS · Done when: `https://thapar.<domain>` resolves with valid TLS
- [ ] **P16.2** Demo/production environment · Done when: Smoke tests pass on deployed env
- [ ] **P16.3** CD pipeline · Done when: A tagged release deploys without manual SSH
- [ ] **P16.4** Backups & restore drill · Done when: Drill log with measured RTO
- [ ] **P16.5** Monitoring & alerts · Done when: Test alert received
- [ ] **P16.6** Runbooks · Done when: `docs/runbooks/` merged

### Phase 17 — Thapar & demo tenants, documentation, presentation (MVP complete)

- [ ] **P17.1** Thapar tenant polish · Done when: Demo script runs end-to-end
- [ ] **P17.2** Demo School & Demo Coaching · Done when: Demo script
- [ ] **P17.3** User documentation · Done when: Reviewed
- [ ] **P17.4** Test & benchmark reports · Done when: `docs/reports/` merged
- [ ] **P17.5** Presentation · Done when: Dry run completed
- [ ] 🚩 **Gate M6 — **MVP**** · Done when: All MVP checklist items ticked

---

### V1 backlog (Phase 18+)
Created as a new checklist section when V1 work starts — see [IMPLEMENTATION_PLAN.md § Phase 18+](IMPLEMENTATION_PLAN.md#phase-18--v1-commercial-launch-backlog).

---

## 📝 Work log
Newest first. One line per session: date · what was done · what's next · blockers.

| Date | Step(s) | Notes / next / blockers |
|---|---|---|
| 2026-10-07 | P9.3, P9.5, Gate M4 ticked — Phase 9 complete | Verified by CI for 6ffe04d (all 7 jobs). That run includes 86b5332, whose own run had no E2E job because of the GitHub outage. Gate M4 evidence on the Thapar seed, both from CI: `students.spec` (student import with errors → fixed file → commit) and `results.spec` (marks with an error → fixed file → close → process → preview → approve → marks read-only). It is not one timed manual run. |
| 2026-10-07 | P9.5 measured | [Benchmark](../benchmarks/results/2026-10-07-result-processing-8000x6.md): 8,000 × 6 processed in 9.59 s on the laptop under Rosetta (target < 2 min), with identical content hashes across 3 runs. The first measurement was 18.44 s; 77% of it was writing 56,000 rows through ORM-entity inserts, and Core inserts (65d0caa) halved it. Approval takes 1.16 s because it recomputes the input hash. GitHub returned 500s on 2026-10-07 (a run with the E2E job missing, a failed re-run request, one rejected push); CI evidence for 86b5332 comes from the next run. |
| 2026-10-07 | P9.1, P9.2, P9.4 ticked; P9.3 UI written | P9.1/P9.2/P9.4 verified by CI for 706319d (all 7 jobs). P9.3 UI: the exam workspace now has Setup and Results tabs. Results shows run status and actions (process with a reason when papers are unsubmitted, sent with an Idempotency-Key; approve with re-auth; reject, revoke, back to marks entry), pass rate and averages, a percentage histogram, grades (paper grades for credit schemes), per-paper figures, the anomaly list, and a filterable student list with a result-preview sheet (`ResultCard`, to be reused by the student portal). Five component tests. New E2E `results.spec.ts` covers the Gate M4 flow on the Thapar seed: marks file with an error → fixed file → close entry → process → preview → approve → marks read-only. Local E2E 24/24. Found by looking at screenshots, then fixed: credit schemes showed "This scheme doesn't give grades" (now paper grades); section header actions overflowed on phones (shared `Section` header now wraps); student names truncated on phones (Total column hidden below `sm`). Found by the E2E: a one-paper exam demanded a course column for the simplest file (now read as that paper; integration test). |
| 2026-10-07 | P9.1, P9.2, P9.4 backend; P9.3 API | Migration 0008: `result_runs`, `student_exam_results`, `student_paper_results`, `approvals`, with RLS. Results and approvals are insert-only for the app (tested). Processing job: set-based loads, engine in a thread, bulk insert, input and content hashes, statistics and anomalies; the exam row is locked against mark writers for the whole run. Determinism is tested at three levels: unit, Hypothesis order-independence, and processing twice end to end. Staleness: an admin mark edit after processing sets results aside, and approval recomputes the input hash as a backstop. Approval needs re-auth and the latest run, records the content hash and locks papers; maker-checker; reject, revoke and discard. Mutation-checked: staleness hook, approval hash recheck, maker-checker rule, input-hash coverage, sort order. Caught on the way: `.capitalize()` lowercased grades in the change notes; a Result-prefixed name avoids an OpenAPI collision (`ReasonIn`, caught by the guard test). 418 backend tests locally. Not built: marksheet pre-render on approval (Phase 11). |
| 2026-10-07 | P8.5, P8.6 ticked — Phase 8 complete | Verified by CI for 90d6199 (all 7 jobs, including the two new marks-import E2E tests). Next: Phase 9. |
| 2026-10-07 | P8.7 ticked; P8.5/P8.6 UI written | P8.7 verified by CI for 00330db (all 7 jobs, including the array-binding fix from fd6f172). Marks import UI: Students/Marks tabs in Imports (exam and paper pickers, template link), kind-aware review and done pages, *Import from Excel* on the mark sheet with that cohort's template, and links in the exam workspace. Faculty review at `/marking/imports/{id}`. The new E2E caught a real bug: returning to a cached mark sheet after an import showed the old marks, because the grid starts from cached data and ignores the later refetch. Fixed generally: a sheet always fetches on open and waits for that fetch (component test, mutation-checked). Local E2E 23/23 (new: admin import with an error row plus template download; invited faculty import, return through the app, submit). |
| 2026-10-07 | P8.3, P8.4 ticked; P8.5/P8.6 backend; P8.7 measured | P8.3/P8.4 verified by CI for baa5cb7 (Playwright marks spec: enter, paste, two-session conflict). P8.5/P8.6 backend in 51b57d2: marks profile with single, long and wide shapes and all docs/13 §4 rules; golden files reviewed by hand; template test opens the workbook and checks the validations. Its CI failed only on `ruff format` (one test file), fixed in fd6f172. P8.7: [benchmark](../benchmarks/results/2026-10-07-marks-import-10k.md). Validated report for 10k rows in 1.59 s (CSV) / 2.69 s (XLSX) on the laptop under Rosetta (target < 60 s). The first run **failed**: Postgres hit `stack depth limit exceeded` on the commit's row-value IN-list. Fixed with array-bound predicates (`app/core/sql.py`), which also avoid asyncpg's 32,767-parameter limit in the students import. Regression test at 40k values / 20k pairs, mutation-checked. Next: marks import UI. |
| 2026-10-07 | P7.6, P8.1, P8.2 ticked | P7.6 verified by CI for a3f6c22; P8.1/P8.2 by CI for 0a388ee (380 backend tests). P8.3/P8.4 UI written: Marks entry work list (faculty now land there), mark sheet grid with Enter/↑/↓ navigation, Excel block paste, AB/EX/MP/WH codes, inline validation shown in the row, debounced autosave with versions, conflict state that loads the colleague's values, submit/return. Deviation: the grid isn't JS-windowed; rows use CSS `content-visibility: auto` (cohorts are usually < 200 students) — to be measured in Phase 14. Design note: attendance codes are per paper (as in the data model and the import rule ABSENT_WITH_MARKS), so a code next to marks is flagged instead of overwriting them — a component test caught the first version silently discarding marks. Local E2E: 21/21 including the new marks spec (real two-session conflict). |
| 2026-10-07 | P7.4, P7.5 ticked | Verified by CI run for a7a2f4d (all 7 jobs). Exhaustive state tests: all 10 statuses × 14 actions against an independent copy of the diagram. The exams API first shipped with a `CohortOut` schema name that collided with academics (FastAPI renamed both and broke the client types; CI's frontend job would have failed) — fixed with Exam-prefixed names plus a unit test that fails on any colliding schema name. P7.6 UI written: exams list/new-exam dialog, workspace Setup tab (readiness checklist, open/close/reopen with reason, papers with component presets, faculty per paper × cohort, cohorts, details); 3 component tests; Playwright exams spec passes locally (20/20 E2E). Known limit: the add-paper course picker lists the first 200 courses. |
| 2026-10-07 | P7.1–P7.3 ticked | P7.1/P7.2 verified by CI run for 63b6586 (engine coverage gate: 99.05%). P7.3 verified by CI run 37542061168 (d49265c): migration 0005 (append-only versions: no UPDATE grant + trigger tested against the owner role), scheme API, onboarding steps, demo default schemes, editor UI with live preview; Playwright grading spec. Caught on the way: `scorecode seed` failed in CI because the CLI didn't import every model (new FK) — all entrypoints now import the model registry, with a regression test; an `alembic check` drift test now guards models vs migrations. Local environment: Docker Desktop's credential helper hung on the Keychain, blocking pulls; builds were done with a credential-free DOCKER_CONFIG (documented in docs/ENVIRONMENT.md) and the unneeded `# syntax=` pins were dropped. |
| 2026-10-07 | P6.1–P6.8, P3.11, Gate M2 ticked; P7.1–P7.2 written | Verified by CI run 37538058576 (all 7 jobs, incl. Playwright on the full stack: student import with errors → fixed file → commit, activation code → student sign-in/out, seeded demo student lands on /me). Phase 6 backend: 172 integration+unit tests locally. Found and fixed during the phase: the API process didn't register job handlers (enqueue would fail outside tests); activation was rate-limited 5/hour **per IP** (would block a classroom on one network) — now 5/hour per enrollment no. as docs/10 specifies plus a 120/hour per-IP bucket; `pluralize()` misuse ("2 new 2 students") caught by a component test. Not built in P6 (documented in docs/13 §8): mapping presets, per-cell edits/row exclusion in staging, import-row retention purge job (Phase 16). Tenant initial JS now 177.1 KB gz (P10.5). P7.1: pure engine (`app/modules/grading/engine`, import-linter purity contract re-added), 26 hand-computed unit cases, 4 Hypothesis properties × 300 examples (a deliberately injected non-monotonic band was caught), 99% branch coverage (CI gate ≥ 90%). P7.2: 3 golden tables with hand-worked expectations; the credit table is a generic CBCS-style scale, **not** Thapar's official policy (unverified, D25). Local note: Docker Desktop hung on this Mac on 2026-10-07 (image pulls and then `docker info`), so the last local full-stack E2E run was before the final UI polish; CI ran it green. |
| 2026-10-06 | P1.1, P1.4, P1.5, Gate M1, P4.4–P4.8, Gate M3, P5.1–P5.4 ticked | Verified by CI run 37501337189 (backend lint/types/unit/integration, frontend lint/types/tests/build, Playwright E2E on the full compose stack from a fresh checkout: 2m09s for the whole job). 109 backend tests, 21 frontend unit tests, 15 E2E tests. Gate M1 evidence is the CI fresh-checkout run, not a timed human run on a new laptop. P4.8: CI seeds all three demo tenants; E2E checks two branded portals, `test_seed` checks all three. P3.11 stays open until the student role exists (P6.7). Tenant initial JS is 171 KB gz, over the 150 KB student target (fix in P10.5). Next: Phase 6. |
| 2026-10-06 | P1.2, P1.3, P1.6–P1.8, P2.1–P2.11, P3.1–P3.10, P4.1–P4.3 ticked | Verified by CI run 37462856524 (all 5 jobs green: lint & types, unit, integration incl. RLS/isolation/authz-matrix, security scans, Docker build + Trivy). Branch protection on the default work branch (no `main` exists): required checks, no force-push/deletion, admins may push. 98 backend tests. Argon2id measured (benchmarks/results). `scorecode seed` written and run locally (idempotent) — P4.8 waits for the UI. Next: P1.4 frontend. |
| 2026-10-06 | P0.4, P1.1–P1.3, P1.5 (infra only), P1.7–P1.8, P2.1–P2.11, P3.1–P3.9 (backend), P4.1–P4.3, P4.4 (backend) | Built and tested locally, not in CI yet (no CI workflow exists), so nothing is ticked except P0.4. Passing locally: 56 backend tests (26 unit + 30 integration), ruff, mypy --strict. Written but **not tested yet**: staff invites/roles API, settings/subscription API, sign-up + handoff, audit viewer, job status endpoint, platform service (`app/modules/platform/service.py` has no router yet). Not started: frontend (P1.4), CI (P1.6), compose app profile/Caddy (P1.5 proxy), `scorecode seed` (`app/seed.py` missing), Phases 5–17. Backend Docker image build started but not verified. D23–D25 still need the owner's input. |
| 2026-10-06 | P0.1–P0.3 | Architecture docs, SRS, SAS, diagrams, plan and checklist written. Next: confirm decisions in docs/18 (P0.4), then P1.1. |
