# Master acceptance checklist

One row per test in [complete-platform-verification.md](complete-platform-verification.md). Tick the box
and write the result **you** saw in *Your result*. A row is PASS only when the real workflow worked;
an automated test listed in *CI coverage* is supporting evidence, not a pass.

**Who:** *Claude ran*: Claude ran the check on production itself (2026-10-16 unless dated). *You*: needs
your sign-in, your inbox or your judgement. *Blocked*: can't run yet; the reason is given. *Your decision*:
run only if you choose (it changes production or needs a business decision).

**CI coverage:** an automated test that covers the same behaviour and passed in CI run 38622551671
(commit f55a3c9: 350+38 unit, 573 integration, 38 end-to-end). It is not proof that production works.

Counts: PASS 27, PARTIAL 3, FAIL 1, BLOCKED 3, NOT TESTED 72, NOT IMPLEMENTED 1, READ 4, total 111.

| ✓ | Test ID | Feature | Where | Who | Status | Evidence / reference | CI coverage | Your result |
|---|---|---|---|---|---|---|---|---|
| [ ] | PRE-01 | Open the project and confirm it is the right one | Mac Terminal | Claude ran | **PASS** | commit f55a3c9, clean (before this audit's commit) |  | |
| [ ] | PRE-02 | Check the secrets file is complete (names only) | Mac Terminal | Claude ran | **PASS** | exit code 0 |  | |
| [ ] | PRE-03 | Which release is running, and is it healthy? | Mac Terminal | Claude ran | **PASS** | deployed v0.1.4; api, postgres, proxy, redis healthy |  | |
| [ ] | PRE-04 | Public smoke test (no secrets needed) | Mac Terminal | Claude ran | **PASS** | 8/8 through Cloudflare, normal TLS |  | |
| [ ] | PRE-05 | Provider logins work, nothing is written | Mac Terminal | Claude ran | **PASS** | 2026-10-16: cloudflare, smtp, ghcr, ssh all OK (ssh after the key was reloaded into the agent) |  | |
| [ ] | PRE-06 | What these tests will never do | Read | You (read) | **READ** |  |  | |
| [ ] | WEB-01 | Homepage and navigation | Browser | You | **NOT TESTED** |  |  | |
| [ ] | WEB-02 | Plans page and live plan data | Mac Terminal + Browser | Claude ran | **PASS** | 4 plans: free 150, starter 600, growth 2000, pro 5000 |  | |
| [ ] | WEB-03 | Phone layout | Browser | You | **NOT TESTED** |  |  | |
| [ ] | WEB-04 | Error pages | Browser | You | **NOT TESTED** |  |  | |
| [ ] | PLAT-01 | First sign-in with two-step | Browser | You | **NOT TESTED** |  |  | |
| [ ] | PLAT-02 | Console health page | Browser | You | **NOT TESTED** |  |  | |
| [ ] | PLAT-03 | Tenants list and detail | Browser | You | **NOT TESTED** |  |  | |
| [ ] | PLAT-04 | Suspend and reactivate the test school | Browser | You | **NOT TESTED** |  | test_entitlements, tenancy.spec | |
| [ ] | PLAT-05 | Closing a school (two approvals) | Browser | Your decision | **NOT TESTED** |  | test_closure | |
| [ ] | ONB-01 | Sign up a test school | Browser | You | **NOT TESTED** |  | test_trials, signup.spec | |
| [ ] | ONB-02 | Second test school (for isolation tests) | Browser | You | **NOT TESTED** |  |  | |
| [ ] | ONB-03 | Institution settings | Browser | You | **NOT TESTED** |  | test_admin_flows | |
| [ ] | ONB-04 | Branding and logo | Browser | You | **NOT TESTED** |  | test_admin_flows | |
| [ ] | ONB-05 | Export the school's data | Browser | You | **NOT TESTED** |  | test_exports | |
| [ ] | AUTH-01 | Wrong password is refused | Browser | You | **NOT TESTED** |  | test_auth, auth.spec | |
| [ ] | AUTH-02 | Repeated failures lock the account for a while | Browser | You | **NOT TESTED** |  | test_auth | |
| [ ] | AUTH-03 | Sessions are per school | Browser | You | **NOT TESTED** |  | test_isolation | |
| [ ] | AUTH-04 | Sign out everywhere | Browser | You | **NOT TESTED** |  | test_auth | |
| [ ] | AUTH-05 | Sensitive actions ask for your password again | Browser | You | **NOT TESTED** |  | test_results (_reauth) | |
| [ ] | AUTH-06 | Turn on two-step sign-in | Browser | You | **NOT TESTED** |  | test_mfa | |
| [ ] | AUTH-07 | Recovery code works once | Browser | You | **NOT TESTED** |  | test_mfa | |
| [ ] | AUTH-08 | An admin resets a colleague's two-step (never the owner's) | Browser | You | **NOT TESTED** |  | test_mfa | |
| [ ] | AUTH-09 | Password reset by email | Browser | You | **NOT TESTED** |  | test_auth | |
| [ ] | ACAD-01 | Session and terms | Browser | You | **NOT TESTED** |  | test_academics, academics.spec | |
| [ ] | ACAD-02 | Department, programme, cohort | Browser | You | **NOT TESTED** |  | test_academics | |
| [ ] | ACAD-03 | Courses | Browser | You | **NOT TESTED** |  | test_academics | |
| [ ] | ACAD-04 | Grading scheme | Browser | You | **NOT TESTED** |  | test_grading_*, grading.spec | |
| [ ] | STU-01 | Import students (valid file) | Mac Terminal + Browser | You | **NOT TESTED** |  | test_imports, students.spec | |
| [ ] | STU-02 | Import students (invalid file is rejected) | Browser | You | **NOT TESTED** |  | test_import_golden | |
| [ ] | STU-03 | Activation codes | Browser | You | **NOT TESTED** |  | test_activation | |
| [ ] | STU-04 | A student activates and signs in | Browser | You | **NOT TESTED** |  | test_activation | |
| [ ] | STU-05 | Invite staff | Browser | You | **NOT TESTED** |  | test_admin_flows | |
| [ ] | STU-06 | Roles limit what staff can do | Browser | You | **NOT TESTED** |  | test_authz_matrix | |
| [ ] | RES-01 | Create an exam | Browser | You | **NOT TESTED** |  | test_exams, exams.spec | |
| [ ] | RES-02 | Papers and components | Browser | You | **NOT TESTED** |  | test_exams | |
| [ ] | RES-03 | Marks entry by faculty | Browser | You | **NOT TESTED** |  | test_marks, marks.spec | |
| [ ] | RES-04 | Marks import (valid) | Browser | You | **NOT TESTED** |  | test_marks_import, marks-import.spec | |
| [ ] | RES-05 | Marks import (invalid is rejected) | Browser | You | **NOT TESTED** |  | test_import_marks_golden | |
| [ ] | RES-06 | Process and preview | Browser | You | **NOT TESTED** |  | test_results, results.spec | |
| [ ] | RES-07 | Approve | Browser | You | **NOT TESTED** |  | test_results | |
| [ ] | RES-08 | Publish now | Browser | You | **NOT TESTED** |  | test_publishing, publish.spec | |
| [ ] | RES-09 | The student sees their own result only | Browser | You | **NOT TESTED** |  | test_publishing, test_isolation | |
| [ ] | RES-10 | Marksheet PDF download | Browser | You | **NOT TESTED** |  | test_marksheets | |
| [ ] | RES-11 | Verify a marksheet publicly | Browser | You | **NOT TESTED** |  | verify.spec | |
| [ ] | RES-12 | Withdraw and publish again | Browser | You | **NOT TESTED** |  | test_publishing | |
| [ ] | RES-13 | Correct a published result | Browser | You | **NOT TESTED** |  | test_corrections, corrections.spec | |
| [ ] | COM-01 | A test email through the running app | Mac Terminal | Claude ran | **PARTIAL** | sent and accepted by Brevo (2026-10-14); inbox receipt not confirmed |  | |
| [ ] | COM-02 | Brevo's own record | Dashboard | You | **NOT TESTED** |  |  | |
| [ ] | COM-03 | In-app notification on publish | Browser | You | **NOT TESTED** |  | test_notifications | |
| [ ] | PLAN-01 | Plan & usage page | Browser | You | **NOT TESTED** |  | plans.spec | |
| [ ] | PLAN-02 | A limit is enforced | Browser | You | **NOT TESTED** |  | test_entitlements | |
| [ ] | PLAN-03 | Change plan in the console | Browser | You | **NOT TESTED** |  | test_entitlements | |
| [ ] | PLAN-04 | Feature gating | Browser | You | **NOT TESTED** |  | test_entitlements | |
| [ ] | PLAN-05 | One free trial | Browser | You | **NOT TESTED** |  | test_trials | |
| [ ] | PLAN-06 | Payments | Read | Your decision | **NOT IMPLEMENTED** | decision D17: billing is manual |  | |
| [ ] | JOB-01 | Queue is healthy | Mac Terminal | Claude ran | **PASS** | no due, running or dead jobs |  | |
| [ ] | JOB-02 | Failed marksheets can be retried | Browser | You | **NOT TESTED** |  | test_marksheets | |
| [ ] | JOB-03 | Worker restart is harmless | Mac Terminal | You | **NOT TESTED** |  |  | |
| [ ] | JOB-04 | Redis down, slow database | Read | Blocked | **BLOCKED** | isolated environment only | test_outages; perf.yml chaos | |
| [ ] | STO-01 | File storage as the app uses it | Mac Terminal | Claude ran | **PASS (2026-10-14)** | write, read, signed 200, unsigned/tampered 400, delete |  | |
| [ ] | STO-02 | A marksheet link expires | Browser | You | **NOT TESTED** |  | test_marksheets | |
| [ ] | STO-03 | One school can't fetch another's files | Browser | You | **NOT TESTED** |  | test_isolation | |
| [ ] | BAK-01 | Nightly backups exist | Mac Terminal | Claude ran | **PASS** | 8 backups; nightly 2026-10-14 and 2026-10-15 21:00 UTC |  | |
| [ ] | BAK-02 | A backup on demand | Mac Terminal | You | **NOT TESTED** |  |  | |
| [ ] | BAK-03 | The key file is right (no decryption) | Mac Terminal | You | **NOT TESTED** |  |  | |
| [ ] | BAK-04 | Synthetic decryption check | Mac Terminal | You | **NOT TESTED** |  |  | |
| [ ] | BAK-05 | Full restore test of the newest production backup | Mac Terminal | You | **FAIL → re-run** | your run on 2026-10-15 hung, then decryption failed; `restore-test.py` rewritten 2026-10-16 with step-by-step checks; recipients match (checked) | release rehearsal (206/207) | |
| [ ] | BAK-06 | The server's backup key can't delete | Mac Terminal | Claude ran | **PASS** | AccessDenied ×3 |  | |
| [ ] | BAK-07 | Lifecycle rules apply to the right prefixes | Mac Terminal | Claude ran | **PASS** | rule scorecode-prod-retention-35d; versioned |  | |
| [ ] | BAK-08 | Noncurrent versions and rule filters | Dashboard | Your decision | **NOT TESTED** |  |  | |
| [ ] | BAK-09 | Spending alerts | Dashboard | Your decision | **NOT TESTED** |  |  | |
| [ ] | SEC-01 | One school's session doesn't work at another school | Browser | You | **NOT TESTED** |  | test_isolation | |
| [ ] | SEC-02 | A record ID from school 1 can't be read in school 2 | Browser | You | **NOT TESTED** |  | test_isolation | |
| [ ] | SEC-03 | A student can't use staff endpoints | Browser | You | **NOT TESTED** |  | test_authz_matrix | |
| [ ] | SEC-04 | No session, no data | Mac Terminal | You | **NOT TESTED** |  | test_authz_matrix | |
| [ ] | SEC-05 | Forms need the CSRF token | Mac Terminal | Claude ran | **PASS** | 403 |  | |
| [ ] | SEC-06 | Security headers | Mac Terminal | Claude ran | **PASS** | all six headers; XFO DENY; HSTS 1 year |  | |
| [ ] | SEC-07 | HTTPS, certificate, redirect, old TLS refused | Mac Terminal | Claude ran | **PASS** | 301 → https; CN=scorecode.website, Let's Encrypt, to 2027-01-07; TLS 1.1 refused |  | |
| [ ] | SEC-08 | Uploads take only real spreadsheets | Browser | You | **NOT TESTED** |  | test_imports | |
| [ ] | SEC-09 | No secret value is in the repository | Mac Terminal | Claude ran | **PASS** | every name not found |  | |
| [ ] | SEC-10 | Audit logs | Browser | You | **NOT TESTED** |  | test_audit | |
| [ ] | SEC-11 | Monitoring and internal ports aren't public | Mac Terminal | Claude ran | **PASS** | /metrics → text/html; only 22 and 443 open |  | |
| [ ] | SEC-12 | SSH is keys-only, and root can be recovered | Mac Terminal | Claude ran | **PASS** | 2026-10-16: passwords refused; root key works; root by key only; ufw active |  | |
| [ ] | OBS-01 | Health endpoints | Mac Terminal | Claude ran | **PASS** | /healthz, /readyz, /plans 200 in ~0.14 s |  | |
| [ ] | OBS-02 | DNS and Cloudflare settings | Mac Terminal | Claude ran | **PASS** | 4 proxied A records; Brevo records present; strict, HTTPS on, TLS 1.2 |  | |
| [ ] | OBS-03 | Logs: structured and free of personal data | Mac Terminal | You | **NOT TESTED** |  |  | |
| [ ] | OBS-04 | Sentry receives a scrubbed error | Mac Terminal + Dashboard | Claude ran | **PARTIAL** | accepted by Sentry, HTTP 200 (2026-10-14); content not yet viewed in Sentry |  | |
| [ ] | OBS-05 | Alert emails arrive | Inbox | Claude ran | **PARTIAL** | test alert 2026-10-16 10:54 UTC: Alertmanager email notifications 0→1, 0 failed; inbox receipt not confirmed |  | |
| [ ] | OBS-06 | Time sync and the log-archive timer | Mac Terminal | Claude ran | **PASS** | NTP synced (samay1.nic.in); log timer last ran 2026-10-16 00:20 |  | |
| [ ] | OBS-07 | Disk, memory, swap | Mac Terminal | Claude ran | **PASS** | disk 9%, swap 2 GB / 0 used, load 0.26 |  | |
| [ ] | DEP-01 | CI is green on the deployed code | Mac Terminal | Claude ran | **PASS** | f55a3c9: CI, Ops, Release success |  | |
| [ ] | DEP-02 | Images are private | Mac Terminal | Claude ran | **PASS** | anonymous pull 401 |  | |
| [ ] | DEP-03 | API restart recovers | Mac Terminal | Claude ran | **PASS (2026-10-14)** | healthy after 14 s |  | |
| [ ] | DEP-04 | Rollback drill | Mac Terminal | Claude ran | **PASS (2026-10-14)** | v0.1.3→v0.1.2→v0.1.3, 59 s / 58 s |  | |
| [ ] | DEP-05 | Migration rollback | Read | Blocked | **BLOCKED** | needs a release with a migration | test_migrations | |
| [ ] | DEP-06 | How a release happens (read only) | Read | You (read) | **READ** |  |  | |
| [ ] | PERF-01 | What has been measured (read) | Read | Claude ran | **PASS (2026-10-14)** | 200 concurrent, 0 errors on the VPS |  | |
| [ ] | PERF-02 | Re-run the 200-student step on the server | Mac Terminal | Claude ran | **PASS** | 2026-10-16: 200 VUs, 0.00% failed both runs, p95 41–172 ms; MemAvailable ≥5,250 MB, swap 0, steal ≤17%; production 99/99 probes 200 |  | |
| [ ] | PERF-03 | Find the ceiling (400, then 600) | Read | Blocked | **BLOCKED** | needs a second machine for k6 |  | |
| [ ] | PERF-04 | Marksheet throughput in your own test | Browser | You | **NOT TESTED** |  |  | |
| [ ] | LEG-01 | Documents that exist (all DRAFT) | Read | You (read) | **READ** |  |  | |
| [ ] | LEG-02 | Controls already in the product | Read | You (read) | **READ** |  |  | |
| [ ] | LEG-03 | Decisions for you | Read | Your decision | **NOT TESTED** |  |  | |
| [ ] | LEG-04 | Before charging money (with a CA) | Read | Your decision | **NOT TESTED** |  |  | |
| [ ] | LEG-05 | For an Indian lawyer | Read | Your decision | **NOT TESTED** |  |  | |

## Before real schools: the critical rows
BAK-05 (restore with your key) · PLAT-01 (console sign-in) · ONB-01 → RES-11 (one school end to end) · 
SEC-01, SEC-02, SEC-03, STO-03 (isolation, with two test schools) · COM-01/COM-02 and AUTH-09 (emails
arrive) · SEC-12 (root recovery) · LEG-03 to LEG-05 · PLAN-06 before charging money.
