# ScoreCode platform audit — 2026-10-16

What is built, what is deployed, what has been verified and how, and what remains before paying schools.
Every status below comes from evidence named in the row. Where there is none, the row says NOT TESTED.
The step-by-step checks are in [complete-platform-verification.md](../runbooks/complete-platform-verification.md)
(test IDs such as `RES-07`), and their tick-list is in [acceptance-checklist.md](../runbooks/acceptance-checklist.md).

## 1. Baseline, as inspected on 2026-10-16

| Item | Found |
|---|---|
| Repository | `~/Desktop/ResultHub` = `github.com/DivyanshuSharmaCoader/High_Performance_Result_Viewing_Platform`, branch `claude/scorecode-design-docs-ffo0a1`, commit `f55a3c9` before this audit; working tree clean |
| Planning documents | `docs/CHECKLIST.md` (124 items ticked, 11 open), `docs/IMPLEMENTATION_PLAN.md`, `docs/04-feature-scope.md` (MVP / V1 / V2 scope), `docs/SRS.md`, docs 01–20. **`MASTER_PLAN.md`, `CLAUDE.md` and `PREFLIGHT.md` do not exist in this repository.** |
| Code | Backend: 21 modules under `backend/app/modules`, 140 API paths (`backend/openapi.json`), 22 migrations. Frontend: 3 apps (`site`: sign-up; `tenant`: school staff and students, 52 routes; `platform`: ScoreCode staff console, 6 routes) |
| Automated tests | 24 unit and 37 integration test files (334 test functions), 19 Playwright specs, 17 frontend test files |
| Last CI on `f55a3c9` | CI run 38622551671, all 7 jobs passed: backend 350 + 38 unit, 573 integration (RLS, isolation, authorisation matrix), frontend 87, Playwright 38, security scans, image scan. Ops and Release also passed |
| Production | `v0.1.4` deployed (`scorecode-ctl status`; releases kept: v0.1.1–v0.1.4). 11 containers up about 40 hours. Public smoke test passes through Cloudflare with normal certificate validation (8 of 8 checks) |
| Server | Hostinger KVM 2 (2 vCPU, 7.9 GB, 96 GB; 9% disk used, 2 GB swap, about 0 used), Ubuntu 24.04.5, Mumbai |
| Public domain | `scorecode.website`, `admin.`, `verify.`, `*.` → the VPS through Cloudflare (Full strict, Always HTTPS, TLS 1.2+); edge certificate Let's Encrypt, valid to 2027-01-07 |

**New findings during this audit**
- **Root SSH with the operator's key fails** (`Permission denied (publickey)`; `secrets-check --connect ssh`:
  key not accepted). It worked on 2026-10-14. The `deploy` account still works, so releases, `scorecode-ctl`
  and restore tests are unaffected. Root-only steps (re-running the server baseline, the Alertmanager test
  alert) are BLOCKED until the owner restores `~/.ssh/scorecode_vm.pub` in root's authorized keys
  (Hostinger hPanel → VPS → SSH keys) or says the change was intended.
- **The production restore test failed for the owner** (it hung, then decryption failed). Checked here
  without the private key:
  - The server encrypts backups to exactly the `BACKUP_AGE_RECIPIENT` in the secrets file (compared by
    checksum through the deploy account: match).
  - The owner had earlier confirmed the private key derives that same recipient (2026-10-14: MATCH).
  - So the key pair is not the cause. Likely causes: the key path passed to the script, the key file
    itself, or the old script, which gave no clue where it stopped.
  - `infra/ops/restore-test.py` is rewritten in this audit. It now checks the key file first (exists,
    private, an age identity without a passphrase, matches the recipient), verifies the download against
    the stored sha256, checks the decrypted stream is a PostgreSQL dump before sending anything, prints
    each step, and has time limits. Re-run with BAK-05.
- Nightly backups run (21:00 UTC on 14 and 15 Oct present; 8 dumps under `prod/db/`, 2.4 MB in total).

## 2. Feature matrix

Status words, as asked: **IMPLEMENTED** (code exists) · **DEPLOYED** (in v0.1.4) · **AUTO PASS** (a named
automated test passed in CI 38622551671) · **MANUAL PASS** · **PROD VERIFIED** · **PARTIAL** · **FAIL** ·
**BLOCKED** · **NOT TESTED**. "Owner" = needs the owner's action. Priority: C critical (before paying
schools), H high, M medium, L low.

| ID | Feature and outcome | Implementation | Production | Verification | Evidence | Remaining work | P | Depends on |
|---|---|---|---|---|---|---|---|---|
| F-01 | Public site: homepage, plans, sign-up pages; responsive | IMPLEMENTED | DEPLOYED | AUTO PASS; PROD VERIFIED (pages answer 200, headers) | `frontend/apps/site`; e2e `signup.spec.ts`, `a11y.spec.ts`, `plans.spec.ts`; public smoke | Manual look on a phone and a desktop (WEB-01–04) | M | — |
| F-02 | Self-serve school sign-up with email verification and a reserved-name check | IMPLEMENTED | DEPLOYED | AUTO PASS; reserved name PROD VERIFIED (`www` refused); full flow NOT TESTED in production | `tenancy/signup_router.py`; `test_trials.py`, `signup.spec.ts` | Owner signs up a test school with their own email (ONB-01) | C | Owner's inbox |
| F-03 | School settings, branding, logo, locale | IMPLEMENTED | DEPLOYED | AUTO PASS | `/admin/settings`, `branding` module; `test_admin_flows.py`, `languages.spec.ts` | ONB-03, ONB-04 | M | ONB-01 |
| F-04 | Tenant lifecycle: suspend, reactivate, closure with 30-day grace and two-approval erasure | IMPLEMENTED | DEPLOYED | AUTO PASS | `platform/router.py`, `tenancy/closure.py`; `test_closure.py`, `tenancy.spec.ts` | PLAT-04, PLAT-05 on the test school only | H | Console sign-in |
| F-05 | Staff sign-in (Argon2id), sessions (HttpOnly, `__Host-`), logout, logout-all, re-authentication for sensitive actions | IMPLEMENTED | DEPLOYED | AUTO PASS; CSRF and cookie flags PROD VERIFIED | `identity/router.py`; `test_auth.py`, `auth.spec.ts`; login without CSRF → 403 | AUTH-01–05 | C | ONB-01 |
| F-06 | Two-step sign-in (TOTP) for staff, recovery codes, admin reset | IMPLEMENTED | DEPLOYED | AUTO PASS | `/me/mfa/*`; `test_mfa.py` | AUTH-06–08 | H | ONB-01 |
| F-07 | Password reset by email | IMPLEMENTED | DEPLOYED | AUTO PASS; NOT TESTED in production | `/auth/password/forgot`, `/reset`; `test_auth.py` | AUTH-09 (sends one email to the owner) | C | ONB-01 |
| F-08 | Staff invitations by email; roles (owner, admin, faculty); role change, deactivate, transfer ownership | IMPLEMENTED | DEPLOYED | AUTO PASS; NOT TESTED in production | `/admin/staff*`, `/auth/invitations/*`; `test_admin_flows.py`, `test_authz_matrix.py` | STU-05, STU-06 | C | A second inbox the owner controls |
| F-09 | Student accounts by activation code; student sign-in by enrollment number | IMPLEMENTED | DEPLOYED | AUTO PASS | `/admin/activation-codes`, `/auth/activate`; `test_activation.py`, `students.spec.ts` | STU-03, STU-04 | C | STU-01 |
| F-10 | Platform console (ScoreCode staff): sign-in with TOTP, tenants list and detail, plan change, trials, overrides, suspend, erase, health, audit | IMPLEMENTED | DEPLOYED; admin account created 2026-10-14 (Argon2id, TOTP pending) | AUTO PASS; first sign-in NOT TESTED | `platform` module, `frontend/apps/platform`; `test_trials.py`, `test_entitlements.py` | PLAT-01 (owner scans the enrolment file). **Gap:** there is no password reset for console accounts (no endpoint or command); a lost console password currently needs a database-level procedure | C | Owner |
| F-11 | Academic structure: sessions, terms, departments, programmes, cohorts, courses; copy structure; archive | IMPLEMENTED | DEPLOYED | AUTO PASS | `academics` module; `test_academics.py`, `academics.spec.ts` | ACAD-01–03 | H | ONB-01 |
| F-12 | Grading schemes: templates (SGPA credit scale, school bands, marks with ranks), versions, preview, default | IMPLEMENTED | DEPLOYED | AUTO PASS (incl. golden and property tests) | `grading` module; `test_grading_engine.py`, `test_grading_golden.py`, `test_grading_properties.py`, `grading.spec.ts` | ACAD-04 | H | ONB-01 |
| F-13 | Students: create, edit, archive, cohorts; CSV/XLSX import with row-level validation and nothing saved until clean | IMPLEMENTED | DEPLOYED | AUTO PASS | `directory`, `ingestion`; `test_imports.py`, `test_import_golden.py`, `students.spec.ts` | STU-01, STU-02 | C | ONB-01 |
| F-14 | Exams, papers, components, faculty assignment; marks entry grid with optimistic locking; submit/return | IMPLEMENTED | DEPLOYED | AUTO PASS | `examinations`, `marks`; `test_exams.py`, `test_marks.py`, `exams.spec.ts`, `marks.spec.ts` | RES-01–03 | C | ACAD |
| F-15 | Marks import (CSV/XLSX template pre-filled, attendance codes AB/EX/MP/WH, error report XLSX, revalidate, cancel) | IMPLEMENTED | DEPLOYED | AUTO PASS | `ingestion/marks.py`; `test_marks_import.py`, `test_import_marks_golden.py`, `marks-import.spec.ts` | RES-04, RES-05 (a bad file must be rejected) | C | RES-01 |
| F-16 | Process results, preview with anomalies, approve (re-auth), reject, discard | IMPLEMENTED | DEPLOYED | AUTO PASS | `results` module; `test_results.py`, `test_results_compute.py`, `results.spec.ts` | RES-06, RES-07 | C | RES-04 |
| F-17 | Publish now / schedule / cancel / withdraw; immutable snapshots; versioned re-publication | IMPLEMENTED | DEPLOYED | AUTO PASS | `publishing`; `test_publishing.py`, `test_snapshot.py`, `publish.spec.ts` | RES-08, RES-12 | C | RES-07 |
| F-18 | Corrections after publication (diff, only changed students notified, old QR → superseded) | IMPLEMENTED | DEPLOYED | AUTO PASS | `publishing/changes.py`; `test_corrections.py`, `corrections.spec.ts` | RES-13 | H | RES-08 |
| F-19 | Student portal: latest result, history, class statistics, marksheet download; Hindi and Punjabi | IMPLEMENTED | DEPLOYED | AUTO PASS; load-tested on the VPS at 200 concurrent (0 errors) | `/me/results*`; `results.spec.ts`, `languages.spec.ts`; benchmarks/results/2026-10-14-result-day-vps.md | RES-09, RES-10 with a real (test) student | C | RES-08 |
| F-20 | Marksheet PDFs with QR and verification code; pre-rendered; retry failed; revoke one | IMPLEMENTED | DEPLOYED | AUTO PASS; rendering PROD VERIFIED only in the isolated VPS test stack | `documents`; `test_marksheets.py`, `test_marksheet_render.py` | RES-10, RES-11 | C | RES-08 |
| F-21 | Public verification page (masked details) | IMPLEMENTED | DEPLOYED | AUTO PASS; page PROD VERIFIED (200) | `verification`; `verify.spec.ts`; public smoke | RES-11 with a real code | H | RES-10 |
| F-22 | Notifications: in-app and email on publish; preferences; only changed students on correction | IMPLEMENTED | DEPLOYED | AUTO PASS | `notifications`; `test_notifications.py` | COM-03 | H | RES-08 |
| F-23 | Email delivery through Brevo; retries; daily email budget (280 in any 24 h; 60 reserved for account emails; notices skipped after 48 h) | IMPLEMENTED | DEPLOYED | AUTO PASS; SMTP login PROD VERIFIED; app's test email accepted by Brevo (2026-10-14); inbox receipt NOT confirmed | `core/mailer.py`, `notifications/budget.py`; `test_mail_budget.py`, `test_cli_checks.py` | COM-01, COM-02 (owner confirms receipt) | C | Owner |
| F-24 | Plans and limits (students, staff, admins, storage, import rows, exams/year); usage page; near-limit alert | IMPLEMENTED | DEPLOYED (4 plans live from `/api/v1/plans`) | AUTO PASS | `entitlements`; `test_entitlements.py`, `plans.spec.ts` | PLAN-01–04 | H | ONB-01 |
| F-25 | Trials: one 30-day Pro trial per institution; abuse signals | IMPLEMENTED | DEPLOYED | AUTO PASS | `test_trials.py`, `test_trial_signals.py` | PLAN-05 | M | ONB-01 |
| F-26 | **Online payment, invoices, GST** | **Not implemented** (decision D17: billing is manual; Razorpay planned for V1) | ABSENT | — | `docs/18-risks-and-decisions.md` D17 | Before charging: a payment method (manual bank/UPI with proper invoices, or Razorpay), GST registration decision, invoice format (legal matrix T1–T3) | C (to charge) | Owner, CA |
| F-27 | Data export (owner; ZIP of CSVs; 7-day link) | IMPLEMENTED | DEPLOYED | AUTO PASS | `exports`; `test_exports.py` | ONB-05 | M | ONB-01 |
| F-28 | Audit logs (school and platform), append-only | IMPLEMENTED | DEPLOYED | AUTO PASS | `audit`; `test_audit.py` | SEC-10 | H | ONB-01 |
| F-29 | Background jobs: Postgres queue, retries, dead jobs, maintenance tasks; worker memory and CPU limits | IMPLEMENTED | DEPLOYED (worker 1 CPU, 2.5 GB; PDF processes recycled) | AUTO PASS; PROD VERIFIED (`jobs stats`: no due, running or dead jobs) | `core/jobs.py`; `test_kernel.py`, `test_outages.py` | JOB-01–03 | H | — |
| F-30 | Redis cache (optional; app degrades without it) | IMPLEMENTED | DEPLOYED | AUTO PASS (`test_outages.py`); Redis-down drill only in CI | `core/cache.py`; perf.yml chaos | JOB-04 in an isolated stack only | M | — |
| F-31 | File storage on R2: per-tenant keys, signed links, unsigned and tampered links refused, delete; quotas | IMPLEMENTED | DEPLOYED | PROD VERIFIED (`scorecode-ctl storage-test`, 2026-10-14: write, read, signed 200, unsigned 400, tampered 400, delete) | `core/storage.py`, `cli.py storage-test`; `test_cli_checks.py`, `test_isolation.py` | STO-01; STO-03 (cross-school file access) with two test schools | H | ONB-01 ×2 |
| F-32 | PostgreSQL with forced RLS on 47 tenant tables; migrations expand-only; up/down round trip | IMPLEMENTED | DEPLOYED (migration 0022 head) | AUTO PASS (`test_migrations.py`, `test_isolation.py`) | `backend/migrations` | DEP-05 (migration rollback not drilled in production) | M | — |
| F-33 | Encrypted nightly backups to S3 (age; the key never on the server); restore tooling | IMPLEMENTED | DEPLOYED; nightly backups present | Backup PROD VERIFIED; restore AUTO PASS (release rehearsal, 206/207 fingerprint lines); **production restore FAIL for the owner, tooling fixed, re-run pending** | `infra/backup`, `scorecode-ctl restore-test`, `infra/ops/restore-test.py` | BAK-05 (owner) | **C** | Owner's key |
| F-34 | Backup bucket safety: delete refused for the server key, versioning, lifecycle by prefix (35 d / 1 d / 1 d) | Bucket configured by the owner | — | PROD VERIFIED from object metadata (2026-10-14) | docs/runbooks/backup-and-restore.md | BAK-07, BAK-08: noncurrent-version expiry on the two 1-day rules not visible to the backup key | M | Owner (AWS console) |
| F-35 | Cost safeguards: backup-size alert at 4 GB; email budget; container limits; AWS budget | App side IMPLEMENTED | DEPLOYED | AUTO PASS (alert unit tests in Ops) | `alerts.yml`, docs/16 §5 | BAK-09: AWS Budget and Free Tier alerts (owner; the backup key can't see billing) | M | Owner |
| F-36 | Sentry, errors only, scrubbed (emails, phones, IDs, marks, tokens, mixed enrollment numbers) | IMPLEMENTED | DEPLOYED | AUTO PASS (`test_sentry_scrub.py`); PROD VERIFIED (`sentry-test` HTTP 200 accepted, 2026-10-14) | `core/sentry.py` | OBS-04: owner opens the event in Sentry and confirms it carries nothing personal | H | Owner's Sentry login |
| F-37 | Monitoring: Prometheus, Alertmanager (email), node and Postgres exporters; alerts for health, queue, disk, memory, backup age and size, SMTP failures, email budget, near-limit | IMPLEMENTED | DEPLOYED (monitoring profile up) | Alert rules AUTO PASS (Ops `promtool test`); a test alert was accepted by Brevo (1 sent, 0 failed, 2026-10-14); **receipt not confirmed** | `infra/monitoring` | OBS-05 (owner confirms the 2026-10-14 alert email; a new one needs root, BLOCKED) | H | Owner; root SSH |
| F-38 | Health and readiness (`/healthz`, `/readyz`), structured logs, 365-day log archive in India, NIC/NPL time | IMPLEMENTED | DEPLOYED | PROD VERIFIED (`/healthz`, `/readyz` 200 publicly; log timer enabled; time from samay1.nic.in, 2026-10-14) | `scorecode-ctl archive-logs` | OBS-01, OBS-06 | M | — |
| F-39 | Release pipeline: build, Trivy scan (critical stops it), private GHCR, sudo-only deploy, automatic restore-point backup, automatic rollback, branch-level image scan | IMPLEMENTED | v0.1.1–v0.1.4 released this way | PROD VERIFIED (v0.1.0 stopped by Trivy as designed; four releases; rollback drill v0.1.3→v0.1.2→v0.1.3, 59 s / 58 s) | `.github/workflows/release.yml` | DEP-05 migration rollback | M | — |
| F-40 | Server hardening: deploy user without docker group, sudo for two programs, key-only SSH, ufw 22/443, swap, unattended upgrades | IMPLEMENTED | Applied 2026-10-14 | PROD VERIFIED 2026-10-14; **root key access now FAIL (see §1)** | `infra/ops/server/bootstrap.sh` | Restore root's key or confirm; SEC-12 | H | Owner |
| F-41 | Security controls: tenant isolation (RLS + host-bound sessions), authorisation matrix, CSRF, rate limits, breached-password check, security headers, honeypot on sign-up | IMPLEMENTED | DEPLOYED | AUTO PASS (`test_isolation.py`, `test_authz_matrix.py`, `test_security_hardening.py`, `test_breached_passwords.py`); headers and CSRF PROD VERIFIED | docs/security/threat-model.md | SEC-01–04 with two test schools | C | ONB-01 ×2 |
| F-42 | Performance: result-day journey | IMPLEMENTED (k6, perf.yml, VPS script) | — | 200 concurrent on the VPS: 0 errors, p95 ≤ 0.65 s; CI 2-vCPU runner: 1,000 concurrent with 3–6% refused | benchmarks/results/2026-10-14-*.md | PERF-03: 400 and 600 with k6 on another machine; **nothing above 200 is shown to work on this server** | H | A second machine for k6 |
| F-43 | Legal documents and readiness matrix (DPDP Act/Rules, IT Act, CERT-In, consumer, GST) | Drafts written | Not published in the product | Not reviewed | docs/legal/ | Lawyer and CA review; owner decisions (backup location, grievance officer, entity) | C | Lawyer, CA |

## 3. Summary

**Genuinely complete, with production evidence:** the deployed stack and its pipeline (F-39), public HTTPS
and DNS (F-01 pages, F-38), server baseline (F-40, except the new root-key issue), R2 storage through the
app (F-31), nightly encrypted backups (F-33 backup side), backup bucket protections (F-34), Sentry
acceptance (F-36), SMTP login and acceptance (F-23 sending side), plans served (F-24), security headers
and CSRF (F-41 partly), rollback (F-39).

**Implemented and automatically tested, but not yet exercised on production:** every school workflow:
sign-up, staff and students, academics, grading, exams, marks entry and import, processing, approval,
publication, corrections, student portal, marksheets, verification, notifications, exports, audit
(F-02 to F-22, F-27, F-28). The same code passes 573 integration tests and 38 end-to-end tests in CI, but
no real (test) school has gone through it on production yet. **This is the main gap.**

**Partial:** monitoring (alerts defined and tested; receipt not confirmed), backup safety (noncurrent
versions on the 1-day rules unverified), performance (200 concurrent proven; 1,000 not).

**Broken or unavailable:** the owner's production restore (F-33; fixed tooling, re-run pending) and root
SSH access (§1).

**Not implemented:** online payments, invoices and GST handling (F-26). Plans are enforced, but there is
no way to take money in the product.

**Legal, privacy, security or commercial concerns:**
- Backups are stored in Australia (ap-southeast-2) while the database and logs are in India. They are
  encrypted, but this is still a cross-border transfer question for a lawyer (matrix L8a).
- The children's-data exemption question (matrix L3) is open.
- Every legal document is a DRAFT.
- Per-student erasure is not self-service (matrix L7).
- The email plan sends 300 a day, so result notices for schools with more than about 220 students arrive
  over two days or are skipped (docs/16 §5).

**Needs the owner:** platform console first sign-in (PLAT-01); a test school with your own email (ONB-01);
the restore re-run (BAK-05); confirming the test emails and alert arrived (COM-01, OBS-05); root SSH key
(§1); AWS budget alerts (BAK-09); legal and tax reviews (LEG-*).

**Before real schools use it (blockers):**
1. BAK-05: a production restore that succeeds with your key.
2. A complete school workflow on production with a test school (ONB-01 → RES-11), including email receipt.
3. Two-school isolation checked on production (SEC-01–03).
4. PLAT-01: your console sign-in works, so you can manage plans and suspend schools.
5. Root SSH restored, or recovery confirmed through the Hostinger console.
6. Legal: DPA and privacy notice reviewed; grievance contact named. To charge money: payments and
   invoices (F-26) and the GST decision.
7. Capacity: either prove more than 200 concurrent students (PERF-03), or limit early schools to sizes the
   measured capacity covers.

**Can wait until after the first schools:** online checkout (if billing stays manual), higher-capacity
hosting, a paid email plan (only once a school larger than about 220 students wants email notices),
migration-rollback drill, custom domains and other V1 items in docs/04.

## 4. Verdict
**ScoreCode is partially verified.** The infrastructure, security baseline, pipeline and integrations are
verified on production. The school workflows are verified by automated tests only, and a production
restore has not yet succeeded for the owner. It is **not yet verified for real schools**. The first manual
step is PLAT-01, then ONB-01 (see the playbook).
