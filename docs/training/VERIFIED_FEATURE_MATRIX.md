# Verified feature matrix (training series)

What the training may show, and how each item was verified. Sources:
- the code: `backend/app/modules/entitlements/catalogue.py` (plans and features),
  `backend/app/modules/identity/permissions.py` (roles), `backend/openapi.json` (140 API paths), the
  three frontend apps;
- the automated tests that pass in CI (run 38622551671: 573 integration, 38 end-to-end);
- the training recordings themselves (`TEST_EVIDENCE.md`), which run on the real application.

**Verification** column: **Recorded** = done in a training recording on the real app (see
TEST_EVIDENCE) · **CI** = an automated test exercises it · **Code only** = the key exists but no code
uses it, so it **must not be presented as working**.

## 1. Roles (the only four school roles)

| Role in ScoreCode | Typical person in a CBSE school | Can | Cannot |
|---|---|---|---|
| **Owner** (`institution_owner`) | Principal or school owner who signed up | Everything an Administrator can, plus: start the free trial, transfer ownership, export all data, close the account | — |
| **Administrator** (`institution_admin`) | Office administrator, examination coordinator | Students, staff, academic structure, grading, exams, imports, marks for any paper, process, approve and publish results, analytics, audit log, settings, branding, plan usage | Trial, ownership transfer, full data export, closing the account |
| **Faculty** (`faculty`) | Subject teacher | Enter and import marks for **assigned** papers only, submit them, see statistics for their papers, two-step sign-in | Anything administrative: students, staff, exams, results, settings |
| **Student** | Student | See their own published results, class statistics (as the school allows), download their marksheet, notifications, preferences | Anything else |

Not present: separate Principal, Examination-coordinator or Parent roles, and any parent login (V2 in
docs/04). The training maps people to the four roles above.

## 2. Plans (live values, `GET /api/v1/plans`, checked 2026-10-16)

| | Free | Starter | Growth | Pro | 30-day trial | Enterprise (contract) |
|---|---|---|---|---|---|---|
| Price a year (catalogue) | ₹0 | ₹7,999 | ₹19,999 | ₹44,999 | ₹0 (once) | by contract  |
| Active students | 150 | 600 | 2,000 | 5,000 | 1,000 | unlimited  |
| Staff accounts (admins + faculty) | 5 | 15 | 60 | 200 | 40 | unlimited  |
| Administrator seats | 2 | 2 | 5 | 15 | 5 | unlimited  |
| File storage | 1 GB | 5 GB | 20 GB | 100 GB | 5 GB | unlimited  |
| Exam publications a year | 6 | unlimited | unlimited | unlimited | unlimited | unlimited  |
| Rows per spreadsheet import | 5,000 | 20,000 | 50,000 | 50,000 | 20,000 | 50,000  |
| Custom branding (colour, login text) | — | ✓ | ✓ | ✓ | ✓ | ✓  |
| Remove "Powered by ScoreCode" | — | — | — | ✓ | ✓ | ✓  |
| More than one department | — | — | ✓ | ✓ | ✓ | ✓  |
| Two-person (maker–checker) approval | — | — | ✓ | ✓ | ✓ | ✓  |
| Scheduled publication | — | — | ✓ | ✓ | ✓ | ✓  |
| Email students on publication | ✓ | ✓ | ✓ | ✓ | ✓ | ✓  |
| Credit-based grading (SGPA) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓  |
| Full disclosure on verification after a date-of-birth check | — | — | — | ✓ | ✓ | ✓  |


The **trial** is its own plan (code `trial`), not Pro: one per institution, for 30 days, started by the
owner from Plan & usage. Custom domain and API access are not in it.

**Enforced in code** (each limit is checked where it applies):
- students: student create and import;
- staff and administrator seats: staff invitations;
- storage: uploads;
- publications a year: publishing;
- import rows: imports;
- branding, departments, two-person approval, scheduled publication, email notices, credit grading,
  "Powered by" and the verification disclosure: each has a code path using it.

**Listed in plans but not implemented (Code only; never show as working):**
- custom domain;
- API access;
- marksheet templates (only the standard marksheet exists);
- advanced analytics (basic per-exam analytics exist on every plan);
- history years.

These appear in the catalogue, but nothing in the application reads them.

**Payments:** there is no online payment, invoice or GST handling. Plans are assigned by ScoreCode in
the platform console (decision D17). The training says so and shows no checkout.

## 3. Features by area

| Area | Feature (as the user sees it) | Roles | Plans | Verification | Where in the app |
|---|---|---|---|---|---|
| Sign-up | Create the school's portal (name, type, address, owner), email verification, onboarding checklist | Owner | all | CI (`signup.spec.ts`), Recorded | scorecode.website/signup |
| Sign-in | Email or enrollment number and password; wrong password; lockout after 5 failures for 15 minutes | all | all | CI (`auth.spec.ts`, `test_auth.py`) | `<school>.scorecode.website/login` |
| Password | Forgot password (email link), change password | all | all | CI | Login → Forgot password; Account |
| Two-step sign-in | Authenticator app, recovery codes; an administrator can reset a colleague's (never the owner's) | staff | all | CI (`test_mfa.py`) | Account → Two-step sign-in |
| Sessions | Sign out, sign out everywhere; sessions belong to one school | all | all | CI | Account |
| Student accounts | Activation codes per cohort; student sets their own password | Owner, Admin; Student | all | CI (`test_activation.py`) | Students → Activation codes; `/activate` |
| Academic structure | Sessions (one current), terms, departments, programmes, cohorts (sections), courses with credits, copy structure to a new session, archive | Owner, Admin | all (several departments: Growth+) | CI (`academics.spec.ts`) | Structure |
| Grading | Schemes from templates (school bands, 10-point credit scale (SGPA), marks with ranks); versions; preview; default | Owner, Admin | all | CI (`grading.spec.ts`, golden tests) | Grading |
| Students | List, search, add, edit, cohorts, status (archive), counts | Owner, Admin | limit by plan | CI (`students.spec.ts`) | Students |
| Imports | Students and marks from CSV/XLSX: template, column mapping, check every row, error report XLSX, revalidate, commit, cancel; nothing saved until clean | Owner, Admin; Faculty for assigned marks | row limit by plan | CI (`marks-import.spec.ts`, `test_import_golden.py`) | Imports |
| Staff | Invite by email with a role; change role; deactivate; resend invitation; transfer ownership (owner) | Owner, Admin | seats by plan | CI (`test_admin_flows.py`) | Staff |
| Exams | Create (name, kind, term, cohorts, scheme); papers with components and pass minimum; assign faculty; open/close marks entry; states | Owner, Admin | all | CI (`exams.spec.ts`) | Exams |
| Marks entry | Grid per paper and cohort, saves as you type, conflicting edits refused, AB/EX/MP/WH codes, submit and return | Faculty (assigned), Admin | all | CI (`marks.spec.ts`) | Marks entry |
| Results | Process, preview with anomalies, approve (password again), reject, discard | Owner, Admin | two-person approval: Growth+ | CI (`results.spec.ts`) | Exams → exam → Results |
| Publication | Publish now; schedule (Growth+); cancel; withdraw; versions | Owner, Admin | publications/year by plan | CI (`publish.spec.ts`) | Results |
| Corrections | Correct after publishing, diff, only changed students notified, old marksheets "superseded" | Owner, Admin | all | CI (`corrections.spec.ts`) | Results → Correct results… |
| Marksheets | PDF per student with QR and code; retry failed; revoke one | Owner, Admin; Student downloads | all | CI (`test_marksheets.py`) | Results; student portal |
| Verification | Public page; code or QR; masked details | anyone | full disclosure: Pro+ | CI (`verify.spec.ts`) | verify.scorecode.website/v |
| Student portal | Latest result, history, class statistics, marksheet, notifications; Hindi and Punjabi | Student | all | CI (`results.spec.ts`, `languages.spec.ts`) | `<school>.scorecode.website` |
| Analytics | Per exam: pass rates, averages, median, spread, grade distribution, section comparison | Owner, Admin; Faculty for own papers | all | CI (`analytics.spec.ts`) | Exams → exam → Analytics |
| Notifications | In-app notices; email on publish (within the daily email budget) | all | all | CI (`test_notifications.py`) | Bell icon |
| Settings | Official name, address, contact, language, what students see of statistics; branding (logo on all plans; colours and login text on Starter+) | Owner, Admin | branding by plan | CI; logo fixed in v0.1.5 | Settings |
| Plan & usage | Current plan, limits, usage; start the 30-day trial | Owner (trial), Admin (view) | all | CI (`plans.spec.ts`) | Plan & usage |
| Audit log | Every change, with who, when and why | Owner, Admin | all | CI (`test_audit.py`) | Audit log |
| Your data | Export everything (ZIP of CSVs); close the account (30-day grace) | Owner | all | CI (`test_exports.py`, `test_closure.py`) | Settings → Your data |
