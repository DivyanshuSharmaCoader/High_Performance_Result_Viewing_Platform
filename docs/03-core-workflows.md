# 03 · Core Workflows — the full SaaS flow end to end

> Covers brief section **E** and §7 (core product workflow). Diagrams for these flows: [activity diagrams](diagrams/activity-diagrams.md), [sequence diagrams](diagrams/sequence-diagrams.md), [state machines](diagrams/state-diagrams.md).
> The import pipeline has its own deep dive: [13 Result ingestion](13-result-ingestion.md).

Each workflow lists: **actor → steps → system behaviour → guards (security/entitlement) → audit events**.

---

## Overview: the life of a tenant

```
 W1 Sign-up & tenant creation
   └► W2 Institution setup (profile, branding, staff)
        └► W3 Academic structure (sessions/terms, departments, programs, cohorts, courses)
             └► W4 Student roster import / activation
                  └► W5 Examination & grading configuration
                       └► W6 Marks capture (grid entry  OR  W7 file import)
                            └► W8 Result processing (compute, preview)
                                 └► W9 Review & approval
                                      └► W10 Publication (immediate or scheduled)
                                           ├► W11 Notification fan-out
                                           ├► W12 Student views result / downloads marksheet
                                           ├► W13 Third-party verification
                                           ├► W14 Analytics
                                           └► W15 Correction & re-publication (versioned)
 Cross-cutting: W16 Plan upgrade & limits · W17 Platform admin operations · W18 Data export / offboarding
```

---

## W1. Sign-up and tenant creation (self-serve)

**Actor:** prospective Institution Owner.

1. Visits `scorecode.in` → "Start free".
2. Enters: name, work email, phone, institution name, institution type (school / college / coaching / other), desired subdomain slug, password.
3. System validates slug (format `^[a-z0-9](-?[a-z0-9]){2,30}$`, not reserved — `www`, `admin`, `api`, `verify`, `app`, `status`, etc. — not taken).
4. Email verification (one-time link, 30 min TTL). **Tenant is created only after verification** to stop spam tenants squatting slugs.
5. In one DB transaction: create `tenant` (status `active`, plan `free`), `tenant_subscription`, owner `user` with role `institution_owner`, default `branding`, default grading scheme templates for the institution type, audit event `tenant.created`.
6. Redirect to `https://<slug>.scorecode.in/admin/setup` (onboarding checklist).

**Guards:** rate limit sign-ups per IP and per email domain; disposable-email blocklist; CAPTCHA only if abuse appears (avoid by default — friction).
**Platform policy option:** "approval required" mode where new tenants start `pending_review` (useful if abuse becomes a problem; off by default).

---

## W2. Institution setup

**Actor:** Institution Owner/Admin. Guided **onboarding checklist** (persistent, dismissible) drives activation:

| Step | Required for first publication? |
|---|---|
| Institution profile (official name, address, affiliation/board, logo) | Yes (appears on marksheet) |
| Branding (colours, login text) | No |
| Invite staff (admins, faculty) — email invite, 7-day token | No (admin can do everything alone) |
| Academic structure (W3) | Yes |
| Students (W4) | Yes |
| First exam (W5) | Yes |

Audit: `institution.updated`, `branding.updated`, `user.invited`, `user.role_changed`.

---

## W3. Academic structure

Generic model that fits schools, colleges and coaching without special-casing (see [07 Database](07-database-design.md)):

| Concept | School | College | Coaching |
|---|---|---|---|
| Academic session | 2025-26 | 2025-26 | 2025-26 |
| Term | Term 1 / Term 2 | Odd / Even semester | Phase 1 / Phase 2 (or single) |
| Department *(optional)* | Primary / Secondary wing | CSE, ECE | JEE, NEET |
| Program | Class 8 | B.E. Computer Engineering | JEE Advanced 2027 |
| Cohort | Class 8 – Section A (2025-26) | CSE 2nd year – Group 3 (2025-26) | Morning Batch A |
| Course | Mathematics | UCS301 Data Structures (4 credits) | Physics |

Admin can create these via UI or import (CSV templates). A **"copy previous session"** action clones structure into a new session (high-value time saver each year).

---

## W4. Student roster import and activation

1. Admin downloads the student template (CSV/XLSX) or uploads their own file and maps columns.
2. Same ingestion framework as marks (W7): validate → preview → commit. Checks: duplicate enrollment numbers (in file and vs existing), cohort exists, required fields, email/phone format.
3. **Entitlement check at commit:** `active_students_after_commit ≤ limit(max_students)`; if exceeded, show exactly how many rows over and offer upgrade (no partial silent truncation).
4. Account activation (choose per tenant):
   - **Invite by email/SMS:** each student gets a one-time activation link → sets password.
   - **Activation codes:** system generates a one-time code per student; admin downloads a printable slip sheet (useful for schools where students have no email). Code + enrollment number → set password.
   - *Not supported:* "default password = date of birth" — DOBs are guessable and widely known; this is a common cause of result leaks. (Possible as enterprise opt-in with forced reset only if a customer insists, with risk acknowledged in writing.)
5. **Strong recommendation in the product:** activate students *before* result day so the login spike does not coincide with the publication spike (see [11 Performance](11-performance-architecture.md)).

Audit: `student.imported` (batch with counts), `student.created/updated/archived`.

---

## W5. Examination and grading configuration

1. Admin creates an **Examination**: name ("Mid-Term 2025", "End Semester Dec 2025"), term, type (unit test / term / semester / supplementary), cohorts sitting it.
2. Adds **papers** = (course × exam) with components and maximums, e.g. Theory: Internal 40 + External 60, pass mark 40% overall and 35% in external.
3. Chooses a **grading scheme** (tenant-defined, versioned): percentage bands → grade, or grade points + credits → SGPA/CGPA, or marks only (coaching, with ranks).
4. Assigns **faculty to papers/cohorts** (who may enter marks).
5. Opens marks entry (`exam.status = marks_entry_open`), optionally with a deadline.

Guard: modifying papers/components after marks exist requires "unlock" with reason (audited).

---

## W6. Marks capture — grid entry

**Actor:** Faculty (only for assigned papers × cohorts), or Admin.

- Spreadsheet-like grid: rows = students in cohort, columns = components; keyboard navigation; paste from Excel supported.
- Inline validation on each cell (range, numeric, allowed codes like `AB` absent, `MP` malpractice, `WH` withheld).
- Autosave with **optimistic concurrency** (`version` per mark entry): if two people edit the same cell, the second gets a conflict, not a silent overwrite.
- Faculty clicks **"Submit paper"** → paper state `submitted` → locked for faculty; admin may return it (`returned` with comment).

Audit: `marks.entered` (batched per save: who, paper, changed cells with from→to), `paper.submitted`, `paper.returned`.

---

## W7. Marks capture — file import (major feature)

Summary (full design in [13 Result ingestion](13-result-ingestion.md)):

```
Upload ─► Store raw file (immutable, hashed) ─► Parse (worker) ─► Map columns ─► Validate rows into staging
       ─► Show report: ✓ valid / ⚠ warnings / ✗ errors  (download errors as XLSX)
       ─► Fix & re-upload  (or edit in staging)
       ─► Commit valid rows (only when 0 blocking errors, or admin chooses "commit valid, skip invalid")
       ─► Marks now in mark_entries ─► continue to W8
```

---

## W8. Result processing (compute and preview)

1. Admin opens exam → "Process results". Preconditions: all papers `submitted` (or admin overrides, audited).
2. Background job computes per student: per-paper totals, pass/fail per component rule, grade, grade points, SGPA/term percentage, overall status, optional rank. Grading scheme **version is pinned** into the computation.
3. Output written to `student_exam_results` (working table, revision n). Computation is **deterministic and idempotent** — re-running yields identical output for identical input.
4. **Preview** screen: distribution chart, pass %, anomalies list (e.g. students with no marks, marks exactly at max in every paper, absent in all papers, totals that changed vs previous run), and per-student preview rendered with the *actual* student-facing component.
5. Any change to marks → results marked `stale`; must re-process before approval.

---

## W9. Review and approval

- **Single-step (Free/Starter):** an admin approves.
- **Two-step maker-checker (Growth+):** the person who processed cannot approve; a second admin with `results.approve` must approve. Configurable per tenant.
- Approval **freezes** the input: marks for that exam are locked; computed results are hashed (`content_hash`) so we can prove later that what was published equals what was approved.
- When results are **published** (or scheduled), the `pdf` worker renders marksheet PDFs and every student gets a verification code. A scheduled release renders ahead of go-live, so result day does no heavy work. *(As built, P11.2: rendering starts at publication rather than at approval. A PDF prints the snapshot the student sees and its verification code, and both exist only once a publication is created. Approval-time rendering would mean rendering twice whenever a schedule changes.)*

Audit: `results.processed`, `results.approved` (with content hash), `results.rejected` (with reason).

---

## W10. Publication

1. Admin chooses **Publish now** or **Schedule** (date/time, tenant timezone, default Asia/Kolkata).
2. Publication creates `publication` (version 1 for this exam) and an **immutable snapshot** row per student in `published_results` (JSON payload exactly as the student will see it). This is the *read model*.
3. At publish time (job at scheduled instant): `publication.status = published`, verification records → `active`, cache warmed for the tenant's "latest results" endpoint, notifications enqueued.
4. Student read path from now on reads only `published_results` (single indexed lookup) — never recomputes.

**Withdraw (unpublish):** allowed with mandatory reason; snapshot hidden from students; verification shows "withdrawn". Audited and visible in publication history.

---

## W11. Notification fan-out

- On publish: create one in-app notification per affected student (bulk insert) + enqueue email batches (provider batch API, throttled to provider limits).
- Notification links to `https://<tenant-host>/results/<exam>`; the link does **not** contain the result (no marks in emails/SMS — privacy, and screenshots of emails spread).
- Delivery status tracked per channel; failures retried with backoff; bounces mark the address invalid.
- *As built (P12):*
  - The fan-out runs as a job once a publication is live (publish now or a scheduled go-live) and
    skips one withdrawn in the meantime. A retried job notifies nobody twice.
  - Email goes only when the tenant setting is on, the plan includes it, the student has an address
    and hasn't opted out, in throttled batches of 50.
  - A revised version is announced as a revision.
  - The inbox count is read on page load and focus, never polled, so result day isn't spent answering
    "any news?".
  - Bounce webhooks come with the provider choice (docs/14 §R).

---

## W12. Student views result and downloads marksheet

```
Login (or existing session) ─► Dashboard (latest publication card) ─► Result detail
     ─► Download marksheet (pre-rendered PDF via short-lived signed URL)
     ─► History (all past publications, latest version of each)
     ─► Notifications · Profile
```
- APIs are `/api/v1/me/...` — **no student ID in the URL**; identity comes only from the session. This makes cross-student IDOR structurally impossible on the student surface.
- If a result was corrected, the student sees the latest version with a "Revised on <date>" note; old versions remain in their history.

---

## W13. Third-party verification

1. Verifier scans QR on marksheet → `https://verify.scorecode.in/v/<code>`.
2. Page shows: institution name & logo, student name **partially masked** (e.g. `An*** Sh***`), enrollment number masked, exam name, publication date, result status (`Valid` / `Superseded by a newer version` / `Withdrawn` / `Revoked`), and the marksheet's document hash.
3. Optional (tenant setting): show full result summary if the verifier enters the student's DOB or a consent code printed on the marksheet.
4. Rate-limited; codes are 128-bit random so enumeration is infeasible. Details: [10 Security](10-security-architecture.md#10-result-verification-18).

---

## W14. Analytics

- Per exam: pass %, grade distribution, mean/median/stdev per paper, top/bottom performers, component-wise analysis, cohort comparison.
- Advanced (Growth+): trends across terms, subject difficulty over years, teacher/paper comparison (sensitive — permission-gated).
- Computed from `student_exam_results` at publication time and stored as an `exam_statistics` snapshot (no heavy queries on result day). Students see only aggregate stats the institution allows (e.g. class average, their percentile).

---

## W15. Correction and re-publication

1. Admin opens a published exam → "Start correction" with reason (e.g. re-evaluation).
2. A new **draft revision** is created; only affected marks are edited (through grid or import).
3. Re-process → preview shows **diff vs published version** (which students changed, old → new).
4. Approve → publish **version n+1**. Previous `published_results` rows are kept, marked `superseded`. Verification of old marksheets shows *"Superseded — a revised result was issued on <date>"*.
5. Only changed students are notified ("Your result has been revised").

This versioning is a key trust feature and good SE evidence (immutability, event history).

---

## W16. Plan upgrade and limits

- Every gated action asks the entitlement service (`can(tenant, feature)`, `within_limit(tenant, limit, delta)`), never `if plan == "pro"`.
- When a limit blocks an action, the UI shows *what* limit, current usage, and the upgrade path.
- V1 billing: upgrade request → invoice (manual / Razorpay payment link) → platform admin activates subscription. Automated online checkout is V1.x once demand is proven.
- Downgrade never deletes data; it blocks *new* actions beyond the lower limit (e.g. cannot add students) and makes data beyond history retention read-only/archived, after advance warning.

---

## W17. Platform admin operations

- View tenants (status, plan, students, last activity, storage), suspend/reactivate (suspension → students see a neutral "temporarily unavailable" page; admins see billing message), change plan, set entitlement overrides (e.g. +500 students for 30 days), view platform health & usage.
- **Support access:** platform admin can view tenant metadata freely, but viewing tenant academic data requires a time-boxed, reason-logged **support session** that the tenant can see in its audit log (V1; tenant may disable it).

---

## W18. Data export and offboarding

- Admin can export all tenant data (students, structure, marks, results, publications, audit log) as a ZIP of CSV/JSON (background job, download link valid 24h).
- Tenant closure: 30-day grace (read-only), then deletion of tenant data from the primary DB; backups age out per retention policy (documented). Issued verification codes return "Institution no longer on ScoreCode" (keeps verification semantics honest without retaining data) — decision to confirm with legal advice.
