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
| Current phase | **Phases 14, 16, 17 — closing** (Phases 0–13 and 15 complete; Gates M1–M5 passed) |
| Next step | **P14.4** closes on the one-worker scaling run (37866472727). **Owner actions:** D23 domain, then P16.1–P16.3 on a real server; P17.3 review of the user guides; P17.5 presentation dry run |
| Last updated | 2026-10-09 |
| Open blockers | P16.1–P16.3 need a domain (D23) and a server: everything up to that is built and rehearsed in CI (`release.yml`). D24 (licence), D25 (Thapar branding) await owner action; safe defaults in place |

## 📊 Phase progress
| Phase | Name | Steps | Done |
|---|---|---|---|
| 2026-10-09 | P17.4 ticked; ASVS gaps closed | P17.4: [reports](reports/README.md) verified by CI for bec0a0b (all 7 jobs; E2E 36 passed including the new accessibility spec, with the 8 demo steps skipped there and run by `demo.yml`). Also built after the reports, each tested with a caught mutant:<br>- **Accessibility (NFR-13, automated part):** axe on 15 screens. It found an unlabelled file input, off-screen save bars reachable by Tab (now `inert`), and unnamed selects.<br>- **Retention (ASVS 8.3.4):** `ops_purge()` every 6 h, per tenant under RLS. It also keeps audit partitions ahead, which before this only an API restart did.<br>- **Security notices (ASVS 2.2.3):** password and two-step changes are emailed to the person.<br>Remaining in 2.2.3: new-device sign-in. |
| 2026-10-09 | P14.3, P14.5, P16.4, P16.5, P16.6, P17.1, P17.2 ticked | Verified by CI for ed958d9 (all 7 jobs) and the runs named.

**P14.3:** same-runner comparison, 1e3b76b against 22d2b73 (perf run 37838765271). 322–327 → 573–593 req/s; 3.3–3.6% → 0% failed; p95 4.4 s → 0.24–0.28 s; SQL 6.86 → 1.65 per request. Plus the per-change in-process measurements ([read-path report](../benchmarks/results/2026-10-09-read-path.md)).

**P14.5:** Postgres-restart re-run with idle-only pings (run 37841311985): 57 retryable 503s in one window, no 500s, recovered.

**P16.4:** the restore drill (`ops.yml` run 37847430260). 8,000 students, age-encrypted backup to a second bucket, database container and volume destroyed, restored as the owner, fingerprints identical (46 forced-RLS tables, 50 policies, grants, functions). **RTO 57 s.** Two earlier runs found that forced RLS blocks `pg_restore`; that led to the three-step restore.

**P16.5:** `ops.yml` alerts job (run 37845231187). Promtool rule tests; every target up; API stopped → ScoreCodeAPIDown email in Mailpit after 101 s, then the resolved email. It also fixed `/metrics` with several workers (multiprocess) and added queue gauges.

**P16.6:** [runbooks](runbooks/README.md). Writing them found the secret-key rotation lockout, so `scorecode reencrypt-secrets` was added.

**P17.1/P17.2:** `scorecode seed --with-history`, and the [demo script](demo/README.md) runs end to end (`demo.yml` run 37867772295, 8/8).

**Not ticked:**
- **P14.4:** the 2-worker comparison at 3,000 users showed a second container on one 4-vCPU machine adds processes, not CPU (failures 6–7.5% → 28–39%). The 1-worker-per-container run decides.
- **P16.1–P16.3:** no domain or server. `compose.prod.yml`, `deploy.sh` and `release.yml` are rehearsed in CI: install, upgrade with backup, automatic rollback of a broken release (runs 37846562794, 37847429961).
- **P17.3:** the user guides are written; the owner's review is the gate.
- **P17.4:** pending CI for 202842b.
- **P17.5:** the deck is written; the dry run is the presenter's. |
| 2026-10-09 | P15.1–P15.5, P14.1, P14.2 ticked | **P15:** P15.1–P15.3 and P15.5 verified by CI for 3da50e8 and b0f6c4b (all 7 jobs). P15.4 verified by CI for 8510a27, where E2E ran the new `edge.spec.ts` (32/32 passed). The ZAP baseline (run 37741788953) found no High alerts ([dispositions](security/zap-baseline-2026-10-08.md)). The Medium, `style-src 'unsafe-inline'`, is fixed on the verify page (stylesheet pinned by hash) and accepted on the SPAs as R-CSP, because sonner and react-style-singleton insert `<style>` at run time. COOP, CORP and COEP were added. Two edge bugs were found while analysing it and fixed: the deferred header block overwrote the verify page's `no-referrer`, and SPA HTML under app routes wasn't `no-cache`. **P14.1:** [runner report](../benchmarks/results/2026-10-08-runner-scenarios.md) from perf runs 37737458557 and 37737494369. A p95 ≤ 13 ms with 0 errors; B about 353 req/s, limited by API CPU (2 workers at about 97% each), with failures that are 5 s pool timeouts. **P14.2:** [profile analysis](../benchmarks/results/2026-10-09-read-path.md). The top costs are SQLAlchemy plus asyncpg (38.7%), a transaction per request (5%) and route matching (6.1%); the pool's pre-ping was found later (2.6%, half of all BEGINs). **P14.3**, four changes, each measured before and after in-process: read cache −20%, routers first −5%, lazy transaction −14%, idle-only ping −3% CPU per request. It stays open until the runner's same-machine comparison (`compare=ref:1e3b76b`) reports. P14.4 waits for `compare=replicas`; P14.5 waits for a Postgres-restart re-run with the new ping behaviour. |
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
| 10 | Publication, read model, student portal | 6 | 6 |
| 11 | Marksheet PDFs & verification | 5 | 5 |
| 12 | Notifications | 3 | 3 |
| 13 | Analytics (basic) & audit viewer | 5 | 5 |
| 14 | Performance engineering (measure → optimise → re-measure) | 5 | 4 |
| 15 | Security review & hardening | 5 | 5 |
| 16 | Deployment, backups, monitoring, runbooks | 6 | 3 |
| 17 | Thapar & demo tenants, documentation, presentation (MVP complete) | 5 | 3 |

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
- [x] **P4.9** Free caps and Pro trial *(added 2026-10-08 at the owner's request; after Gate M3)* · Done when: Abuse, expiry and conversion tests; Playwright trial flow

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

- [x] **P10.1** Publication schema · Done when: Tests: app role cannot update snapshots
- [x] **P10.2** Snapshot builder · Done when: Unit tests
- [x] **P10.3** Publish now / schedule / withdraw · Done when: Fault-injection test (rollback mid-way)
- [x] **P10.4** Student APIs · Done when: Isolation tests (student X vs Y)
- [x] **P10.5** Student portal UI · Done when: Playwright on mobile viewport; budget < 150 KB gz
- [x] **P10.6** Load test harness · Done when: Baseline report in `benchmarks/results/`
- [x] 🚩 **Gate M5a — Result day (view)** · Done when: Publish → students view results; baseline numbers recorded (whatever they are)

### Phase 11 — Marksheet PDFs & verification

- [x] **P11.1** Template system · Done when: Security test: template cannot fetch external URL
- [x] **P11.2** Render jobs · Done when: Tests + timing measured per PDF
- [x] **P11.3** Download · Done when: Isolation tests
- [x] **P11.4** Verification records · Done when: State tests
- [x] **P11.5** Verify page · Done when: E2E-4
- [x] 🚩 **Gate M5 — Result day (complete)** · Done when: Publish → view → download → scan QR → verified

### Phase 12 — Notifications

- [x] **P12.1** In-app notifications · Done when: Tests
- [x] **P12.2** Email channel · Done when: Integration with Mailpit; failure retry test
- [x] **P12.3** Notification preferences · Done when: Tests

### Phase 13 — Analytics (basic) & audit viewer

- [x] **P13.1** Exam statistics snapshot · Done when: Unit tests vs hand-computed fixtures
- [x] **P13.2** Admin analytics UI · Done when: Playwright
- [x] **P13.3** Student stats view · Done when: Tests
- [x] **P13.4** Audit log viewer · Done when: Tests + UI
- [x] **P13.5** Platform metrics overview · Done when: E2E

### Phase 14 — Performance engineering (measure → optimise → re-measure)

- [x] **P14.1** Full scenario runs · Done when: Reports with p50/p95/p99, RPS, errors, resources
- [x] **P14.2** Bottleneck analysis · Done when: Written analysis identifies top 3 bottlenecks
- [x] **P14.3** Targeted optimisations · Done when: Before/after report per change
- [ ] **P14.4** Horizontal scaling demonstration · Done when: Report (NFR-16)
- [x] **P14.5** Failure-under-load tests · Done when: Results recorded per [15 §6](15-testing-strategy.md#6-failure-testing)

### Phase 15 — Security review & hardening

- [x] **P15.1** Threat model review · Done when: Doc updated
- [x] **P15.2** ASVS L2 checklist · Done when: Checklist committed with status
- [x] **P15.3** Security test completion · Done when: Suites green
- [x] **P15.4** DAST & scans · Done when: Reports saved
- [x] **P15.5** Admin protections · Done when: Tests

### Phase 16 — Deployment, backups, monitoring, runbooks

- [ ] **P16.1** Domains & DNS · Done when: `https://thapar.<domain>` resolves with valid TLS
- [ ] **P16.2** Demo/production environment · Done when: Smoke tests pass on deployed env
- [ ] **P16.3** CD pipeline · Done when: A tagged release deploys without manual SSH
- [x] **P16.4** Backups & restore drill · Done when: Drill log with measured RTO
- [x] **P16.5** Monitoring & alerts · Done when: Test alert received
- [x] **P16.6** Runbooks · Done when: `docs/runbooks/` merged

### Phase 17 — Thapar & demo tenants, documentation, presentation (MVP complete)

- [x] **P17.1** Thapar tenant polish · Done when: Demo script runs end-to-end
- [x] **P17.2** Demo School & Demo Coaching · Done when: Demo script
- [ ] **P17.3** User documentation · Done when: Reviewed
- [x] **P17.4** Test & benchmark reports · Done when: `docs/reports/` merged
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
| 2026-10-08 | P13.1–P13.5 ticked; Phase 14 tooling written | Verified by CI for ad93769 (all 7 jobs, including analytics.spec). Phase 14: the laptop is on battery (22%) with Low Power Mode, so load tests move to a GitHub runner through a manual workflow `perf.yml`. It runs the stack plus synthetic data plus k6, with docker stats, pg_stat_statements, EXPLAIN plans and a py-spy profile, all uploaded as an artifact. Also: `API_WORKERS` is configurable, and Caddy balances across every API address (`dynamic a`, least_conn), which enables `--scale api=N` for P14.4. First evidence for P14.2, from local EXPLAIN on 8,000 students: all seven read-path queries are index lookups under 1 ms, so the database is not the bottleneck. |
| 2026-10-08 | P12.1–P12.3 ticked | Verified by CI for d2bc101 (all 7 jobs, including the P10 E2E with the phone student's notification). e3e3077 had failed the frontend typecheck: a local `pnpm -s` run had hidden the error. That's fixed, and checks now run without `-s`. **Next:** Phase 13. |
| 2026-10-08 | P12.1–P12.3 written (not ticked; CI pending) | Backend (b2044e1): migration 0012 (inbox with idempotent fan-out; per-channel deliveries; `users.notify_email`); a fan-out job when a publication goes live; email in throttled batches of 50 with retries; inbox, read, read-all and preferences API; email counts per publication. Six integration tests; five mutations caught (opt-out ignored, withdrawn still notified, read not scoped to the user, tenant switch ignored, duplicate fan-out). UI: a bell with an unread badge in the student header (count read on load and focus, never polled), the inbox panel, a result-email switch on the account page, and an email summary on the publication panel. Student bundle 141.0 kB. The P10 E2E now also checks the student's notification; it passes locally against the stack, as does E2E-4. SPF, DKIM and DMARC are documented in docs/14 §R. **Not built:** provider bounce webhooks (Phase 16, once the provider is chosen). |
| 2026-10-08 | P11.2 and Gate M5 ticked | Verified by CI for b64ff96 (all 7 jobs). Render time on the CI runner (run 37714377613): p50 202 ms, p95 292 ms per six-paper PDF on one thread, 20.7 KiB each; the laptop on battery measured p50 172 ms. Both are in benchmarks/results/2026-10-08-marksheet-render.md. The gate's demo, publish → view → download → verify, is E2E-4: CI checks the downloaded PDF's SHA-256 on the verify page. Carried into Phase 14: a process pool for rendering (one process takes about 25–28 min for 8,000 students). |
| 2026-10-08 | P11.1, P11.3, P11.4, P11.5 ticked | Verified by CI for 0ba609b (all 7 jobs). Integration ran 481 tests with none skipped, so the PDF tests ran with Pango. The E2E job passed E2E-4 with real rendering in the worker container. Five mutations were caught: scheduled codes made verifiable, names unmasked, revocation ignored, failed renders never marked failed, downloads not scoped to the student. So was a sixth in Docker: a fetcher that allows URLs. Locally, E2E-4 and P10 also passed against the rebuilt stack. After that: the admin drawer shows the issued marksheet with download and revocation (3806d5c). P11.2 stays open until CI reports a render time from a machine that isn't on battery. |
| 2026-10-08 | P11.1–P11.5 written (not ticked; CI pending) | **Marksheet PDFs and verification.** Migration 0011 adds `marksheet_documents` and `verification_records` (global 128-bit Crockford codes; status derived from the publication; column-level grants; `verification_lookup` definer). Publishing creates a pending document and a code per student and enqueues `documents.render` jobs (50 students each, `pdf` queue). A scheduled release renders ahead of go-live. Each job lays out PDFs in a thread without holding a connection and stores each in its own transaction. Failures retry; after the last attempt the document is `failed` and admins can retry. Marksheets count towards storage but never block. Students get signed 120 s download links located through their session, plus a shareable verification link. Admins get per-student downloads, progress, retry and per-student revocation (re-auth + audit). The public verify page is server-rendered with no scripts, masked identity, the PDF's SHA-256, noindex, no-referrer, a strict CSP and an HTML 429. The renderer uses a Jinja sandbox and refuses every non-`data:` fetch. Tests: 9 integration (flow, isolation, retries, lifecycle, page, rate limit, definer scope) and 3 PDF tests that run in CI and the Docker image (live-server SSRF suite with a control request; real render). They passed in the Docker image locally. The template was reviewed as rendered PDFs and the layout fixed. Mutation check: making scheduled codes verifiable was caught; the remaining mutation checks are still to redo. E2E-4 (`verify.spec.ts`) checks that the downloaded file's SHA-256 matches the verify page, axe passes, and a withdrawal shows. **Deviations:** rendering starts at publication, not approval (docs/03 W9). Only the `standard` template exists; `classic` and a template setting come later. "Superseded" can't be reached through the UI until the correction workflow ships, so it's covered by an integration test. **Not verified yet:** timing per PDF (waiting for AC power: the laptop is on battery with Low Power Mode); E2E-4 in CI. 478 backend tests pass locally; frontend tests pass; student bundle 140.0 kB. |
| 2026-10-08 | P10.6 and Gate M5a ticked | Verified by CI for fddb60b (all 7 jobs). The gate's demo, publish → students view results, is the Playwright publish journey; the baseline is in benchmarks/results/2026-10-08-k6-scenarios-A-B.md. Still open, and carried into Phase 14: B-cold after the fix on AC power. **Next:** Phase 11. |
| 2026-10-08 | P10.6 written (not ticked; CI pending); two result-day fixes | CI for 9eea1e5 green on all 7 jobs. **P10.6.** I ran k6 scenarios A and B, pre-authenticated (3 runs each) and cold (1 each), on one M2 laptop with the load generator co-located: benchmarks/results/2026-10-08-k6-scenarios-A-B.md, with raw data. A: p95 ≤ 11 ms, no errors; a sign-in costs 34 ms. B pre-authenticated: about 600 req/s, p95 0.5–0.7 s, 0.016% errors. The first limit is API CPU (two workers at 150–170%; Postgres about 45%), so docs/11's prediction holds only in part. **Found and fixed:** (1) The API keyed per-IP limits on the right-most X-Forwarded-For entry, which is the nearest proxy (a CDN edge in production), so 601 of 1,000 cold sign-ins got 429. Caddy now resolves the client address (`trusted_proxies_strict`) and overwrites X-Real-IP, which is the only header the API reads; 980 of 1,000 sign-ins then succeeded. (2) DB pool timeouts became 500s; they are now `503 overloaded` + Retry-After, in routes and in the middleware's tenant lookup. Both have tests that fail under mutation, and the client address was also checked end to end through Caddy. Also: the `compose.yml` login-limit override (stricter than the production default) is gone; a stale ENVIRONMENT row is gone; tests no longer read `trust_proxy_headers` from a developer's .env; and `benchmarks/k6/run.sh` refuses to run on battery. **Not verified:** B-cold after the fix on AC power. The later runs were on battery with Low Power Mode, which cut throughput by 32–44%, so they are reported only as controls. 460 backend tests pass locally. **Next:** CI, then tick P10.6 and Gate M5a; re-run B-cold on AC; Phase 11. |
| 2026-10-08 | P10.5 ticked; security hardening | P10.5 verified by CI for 0b58df4 (all 7 jobs; the bundle budget is enforced at 139.9 kB; Playwright on a phone viewport). Hardening, prompted by the owner's concern about competitors and students causing harm: (1) **result-day sign-in**: the per-IP login limit counted *every* attempt (20/min), so a school lab or a mobile carrier's NAT would have locked out real students. All attempts now meet only a flood ceiling (600/min); *failed* attempts per IP have their own bucket (60/min); per-account limits and lockout are unchanged. The limiter gained a Redis-aware non-consuming `check` and a non-raising `consume`. Tests: 80 students from one address all sign in; 65 failures from one address hit 429, and a correct password then waits too. (2) **signup honeypot**: a hidden field; bots that fill it get the normal answer, and nothing is stored or emailed (metric `scorecode_signup_honeypot_total`); tested. Docs: docs/10 rate-limit table, ENVIRONMENT. 457 backend tests locally. |
| 2026-10-08 | P4.9 ticked; P10.5 written | P4.9 verified by CI for e7b7ea6 (all 7 jobs, including the Playwright trial flow). P10.5: the student home leads with the latest result (outcome, SGPA or percentage) and lists earlier results. The result page shows marks per paper with a bar per component, the class average where the institution shares it, a revised-result notice and print. The admin preview renders the same `StudentResultView`. A Publication panel on the Results tab offers publish now (re-auth and Idempotency-Key), schedule (gated by plan, with a link to plans), cancel, withdraw with a reason, publish again, and history. Student first load went from 185 kB to 139.9 kB gzipped (lazy staff shell, side-effect-free UI package, lazy re-auth dialog and toaster, light account menu); the budget is now **enforced** in CI at 150 kB. Tests: 52 component tests (7 new for the portal and publishing); new E2E `publish.spec.ts` covers approve → publish from the UI → the seeded student sees exactly their result on a phone viewport. Local E2E 26/26. |
| 2026-10-08 | P10.1–P10.4 ticked; P4.9 written | P10.1–P10.4 verified by CI for 17aa98b (all 7 jobs). P4.9 (owner's request): researched free tiers. The hosted free tiers we checked cap at 100 students (ScholaBook, OurSchoolSoftware, Zoho Classes); trials are 3–30 days. Sources and date are in docs/02 §2.1. Free is now 150 students, 5 staff, 2 admins and 6 publications a year; a guarded data migration only changes values still at the old defaults. The 30-day Pro trial: owner only, no card, up to 1,000 students, without custom domain or API. It runs once per tenant (unique `tenant_trials`). Across tenants, a global `trial_claims` table that only the platform role can reach holds HMAC digests of normalised signals: hard (refuse) are the owner email with Gmail dots and +tags collapsed, the institutional domain, a server-issued device cookie and the tenant; soft (risk score; 2 or more goes to a person) are the unverified phone, the institution name and a busy network. Advisory locks plus a partial unique index handle concurrent attempts. Reminder and end jobs return the tenant to Free without deleting anything. Staff can grant or revoke from the console, and refusals are audited with signal kinds only. UI: the Plan & usage page has a trial card for each state (start, countdown ring, ended), usage with full-limit hints, and a plan comparison (table on desktop, cards on phones); the shell shows a trial banner; every plan-limit error offers "See plans"; site pricing copy is updated. Tests: 23 signal unit tests, 12 trial integration tests (two mutations caught), 6 component tests, and a Playwright trial flow. Local E2E 25/25. Known limit (docs/12 §6): without card or phone verification, a determined person with several real mailboxes, browsers and networks can still repeat a trial; the signals make that slow and visible. |
| 2026-10-07 | P10.1–P10.4 backend written (not ticked; CI pending) | Migration 0009: `publications` (one live and one scheduled per exam), immutable `published_results` and `exam_statistics` (app has SELECT and INSERT only, and a trigger refuses UPDATE or DELETE for every role, including the owner; tested). Pure snapshot builder (schema 1, canonical numbers, payload hash, no internal ids) with unit tests. Publish now or scheduled (re-auth, Idempotency-Key, approved run, scheduling feature, per-session publication limit counted live under a tenant lock), `publishing.go_live` job, cancel, withdraw, and republish as a new version. Fault injection: a failure after half the snapshots leaves nothing behind and the idempotency key isn't kept. Student APIs `/api/v1/me/results[/latest\|/{id}\|/{id}/stats]` take identity from the session only and send `no-store`. Tests: the same publication id returns each student's own row; withdrawn results are hidden. Two read-filter mutations were caught. The isolation suite now covers student-only routes with a real student. 420 backend tests pass locally. **Next:** tick after CI; P10.5 student portal UI and bundle budget (177 KB gz today, target 150); publish UI in the exam workspace; P10.6 k6 baseline; Gate M5a. |
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
