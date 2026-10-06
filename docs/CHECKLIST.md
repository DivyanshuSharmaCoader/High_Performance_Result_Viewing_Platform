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
| Current phase | **Phases 1–4 in progress** (backend kernel, identity, entitlements built and tested locally; no frontend yet) |
| Next step | Platform console router (P4.7), isolation suite (P3.10), seed (P4.8), then frontend workspace (P1.4) |
| Last updated | 2026-10-06 |
| Open blockers | Domain name (D23), licence/visibility (D24), Thapar branding permission (D25) |

## 📊 Phase progress
| Phase | Name | Steps | Done |
|---|---|---|---|
| 0 | Product & architecture | 4 | 4 |
| 1 | Repository, tooling, CI, walking skeleton | 8 | 0 |
| 2 | Platform kernel: database, tenancy, RLS, audit, errors | 11 | 0 |
| 3 | Identity: authentication, sessions, RBAC | 11 | 0 |
| 4 | Onboarding, plans & entitlements, basic branding, platform console v0 | 8 | 0 |
| 5 | Academic structure | 4 | 0 |
| 6 | Directory & generic import framework | 8 | 0 |
| 7 | Examinations & grading engine | 6 | 0 |
| 8 | Marks entry & marks import | 7 | 0 |
| 9 | Result processing, preview, approval | 5 | 0 |
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

- [ ] **P1.1** Monorepo skeleton · Done when: Structure matches [SAS §7](SAS.md#7-development-view-41-development)
- [ ] **P1.2** Backend project · Done when: `curl /livez` → 200; unit test for config validation
- [ ] **P1.3** Backend quality tooling · Done when: `make lint test` passes locally
- [ ] **P1.4** Frontend workspace · Done when: `pnpm -r build` and `pnpm -r test` pass
- [ ] **P1.5** Docker & compose · Done when: `docker compose up` → `http://demo.localhost:8080/api/livez` 200 and SPA placeholder loads
- [ ] **P1.6** CI pipeline v1 · Done when: CI green on PR; branch protection on `main`
- [ ] **P1.7** Job queue spike (D8) · Done when: ADR written with chosen option; spike code removed or promoted
- [ ] **P1.8** ADRs · Done when: ADR files merged
- [ ] 🚩 **Gate M1 — Walking skeleton** · Done when: Compose up works on a fresh clone in < 10 min following README

### Phase 2 — Platform kernel: database, tenancy, RLS, audit, errors

- [ ] **P2.1** DB roles & connection · Done when: Integration test connects with each role; app role cannot `CREATE TABLE`
- [ ] **P2.2** Conventions & base classes · Done when: Unit tests for id generation ordering
- [ ] **P2.3** Tenancy tables · Done when: Migration up/down test
- [ ] **P2.4** Tenant resolution middleware · Done when: Tests for each host type and suspended/unknown
- [ ] **P2.5** Unit of Work + RLS context · Done when: Test: query without context errors; with context only own rows
- [ ] **P2.6** RLS policy helper + coverage test · Done when: Test fails if a tenant table lacks RLS
- [ ] **P2.7** Composite FK pattern · Done when: Integration test
- [ ] **P2.8** Audit module · Done when: Test: rolled-back change leaves no audit row; app role cannot UPDATE/DELETE
- [ ] **P2.9** Errors & API conventions · Done when: Unit + integration tests
- [ ] **P2.10** Cache abstraction · Done when: Test: Redis down → fallback works
- [ ] **P2.11** Observability basics · Done when: Test: scrubber removes password/token fields

### Phase 3 — Identity: authentication, sessions, RBAC

- [ ] **P3.1** Users & roles schema · Done when: Migrations + RLS test pass
- [ ] **P3.2** Password hashing · Done when: Unit tests; measured value documented
- [ ] **P3.3** Login/logout · Done when: Integration tests incl. wrong tenant host → 401
- [ ] **P3.4** Session validation dependency · Done when: Tests: expired, revoked, cross-host replay
- [ ] **P3.5** CSRF protection · Done when: Test: POST without token → 403
- [ ] **P3.6** RBAC · Done when: Authz matrix test scaffold green
- [ ] **P3.7** Rate limiting · Done when: Tests incl. Redis-down fallback
- [ ] **P3.8** Password reset & invites · Done when: Integration tests with Mailpit API
- [ ] **P3.9** Platform realm auth · Done when: Tests: platform login on tenant host fails
- [ ] **P3.10** Tenant isolation suite v1 · Done when: Suite runs in CI as required check
- [ ] **P3.11** Frontend auth · Done when: Playwright: login/logout for each role
- [ ] 🚩 **Gate M2 — Secure multi-tenant core** · Done when: Two seeded tenants on two hosts; isolation suite green; live demo of blocked cross-tenant access

### Phase 4 — Onboarding, plans & entitlements, basic branding, platform console v0

- [ ] **P4.1** Plans & features schema + seed · Done when: Migration + seed idempotent
- [ ] **P4.2** Entitlement service · Done when: Table-driven tests + race test
- [ ] **P4.3** Tenant provisioning service · Done when: Integration test
- [ ] **P4.4** Self-serve sign-up · Done when: E2E-1 passes
- [ ] **P4.5** Basic branding · Done when: E2E: two tenants render different branding
- [ ] **P4.6** Onboarding checklist · Done when: Component + API tests
- [ ] **P4.7** Platform console v0 · Done when: E2E: suspend → tenant portal shows unavailable page
- [ ] **P4.8** Seed tenants · Done when: Fresh clone + `make seed` shows 3 branded portals
- [ ] 🚩 **Gate M3 — Self-serve SaaS** · Done when: Sign-up to branded portal works end-to-end; platform console shows all tenants

### Phase 5 — Academic structure

- [ ] **P5.1** Schema · Done when: Migrations + constraint tests
- [ ] **P5.2** Services & APIs · Done when: API tests + authz matrix entries
- [ ] **P5.3** Admin UI · Done when: Playwright create/edit/archive
- [ ] **P5.4** Thapar & demo seed data · Done when: Seed script idempotent

### Phase 6 — Directory & generic import framework

- [ ] **P6.1** Students & staff schema · Done when: Migrations + tests
- [ ] **P6.2** Student service · Done when: Tests incl. limit and race
- [ ] **P6.3** Staff management · Done when: Tests
- [ ] **P6.4** Files module · Done when: Security tests (wrong type, oversize)
- [ ] **P6.5** Import framework core · Done when: Golden-file tests on messy corpus
- [ ] **P6.6** Student import profile · Done when: Tests + E2E import with errors → fix → commit
- [ ] **P6.7** Student activation · Done when: E2E: student activates and logs in
- [ ] **P6.8** Admin UI · Done when: Playwright

### Phase 7 — Examinations & grading engine

- [ ] **P7.1** Grading engine (pure) · Done when: ≥ 90% branch coverage; Hypothesis properties (monotonic, bounded, deterministic)
- [ ] **P7.2** Golden grading tables · Done when: Golden tests pass
- [ ] **P7.3** Grading schemes schema & UI · Done when: Immutability trigger test
- [ ] **P7.4** Exams schema · Done when: Migrations + tests
- [ ] **P7.5** Exam state machine · Done when: Exhaustive transition tests
- [ ] **P7.6** Exam setup UI · Done when: Playwright

### Phase 8 — Marks entry & marks import

- [ ] **P8.1** Mark entries schema & service · Done when: Tests incl. conflict 409
- [ ] **P8.2** Faculty scope enforcement · Done when: Authz matrix tests
- [ ] **P8.3** Marks grid UI · Done when: Playwright: enter, paste, conflict
- [ ] **P8.4** Paper submission workflow · Done when: Tests + UI
- [ ] **P8.5** Marks import profile · Done when: Rule tests + golden files
- [ ] **P8.6** Pre-filled templates · Done when: Test opens generated file and checks validations
- [ ] **P8.7** Import performance check · Done when: Result in `benchmarks/results/`

### Phase 9 — Result processing, preview, approval

- [ ] **P9.1** Results schema · Done when: Migrations
- [ ] **P9.2** Processing job · Done when: Determinism test (run twice → identical)
- [ ] **P9.3** Preview & anomalies · Done when: Tests + Playwright
- [ ] **P9.4** Approval · Done when: Tests incl. stale run cannot be approved
- [ ] **P9.5** Processing performance check · Done when: Result recorded
- [ ] 🚩 **Gate M4 — Results pipeline** · Done when: Import students & marks with errors → fix → process → preview → approve, on Thapar seed

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
| 2026-10-06 | P0.4, P1.1–P1.3, P1.5 (infra only), P1.7–P1.8, P2.1–P2.11, P3.1–P3.9 (backend), P4.1–P4.3, P4.4 (backend) | Built and tested locally, not in CI yet (no CI workflow exists), so nothing is ticked except P0.4. Passing locally: 56 backend tests (26 unit + 30 integration), ruff, mypy --strict. Written but **not tested yet**: staff invites/roles API, settings/subscription API, sign-up + handoff, audit viewer, job status endpoint, platform service (`app/modules/platform/service.py` has no router yet). Not started: frontend (P1.4), CI (P1.6), compose app profile/Caddy (P1.5 proxy), `scorecode seed` (`app/seed.py` missing), Phases 5–17. Backend Docker image build started but not verified. D23–D25 still need the owner's input. |
| 2026-10-06 | P0.1–P0.3 | Architecture docs, SRS, SAS, diagrams, plan and checklist written. Next: confirm decisions in docs/18 (P0.4), then P1.1. |
