# Software Requirements Specification — ScoreCode

| | |
|---|---|
| Document | Software Requirements Specification (SRS) |
| Product | ScoreCode — multi-tenant examination and result management SaaS |
| Version | 1.0 (draft, Phase 0) |
| Date | 2026-10-06 |
| Structure | Based on ISO/IEC/IEEE 29148:2018 (successor of IEEE 830) |
| Related | [SAS](SAS.md) · [Feature scope](04-feature-scope.md) · [Workflows](03-core-workflows.md) · [Testing](15-testing-strategy.md) |

---

## 1. Introduction

### 1.1 Purpose
This SRS specifies the functional and non-functional requirements of ScoreCode's MVP and V1. It is the reference for design, implementation, testing (each requirement maps to tests in §7) and academic evaluation.

### 1.2 Scope
ScoreCode lets educational institutions (tenants) manage academic structure, students and examinations; capture and import marks; validate, compute, approve and publish results; let students view results and download verifiable marksheets; and let ScoreCode operators run the platform with plans and entitlements. **Out of scope:** fees, attendance, timetable, transport, hostel, library, payroll, HR, LMS, admissions.

### 1.3 Definitions
| Term | Meaning |
|---|---|
| Tenant | An institution using ScoreCode; the unit of data isolation |
| Platform admin | ScoreCode operator staff |
| Cohort | A section/batch/group of students in a program for an academic session |
| Paper | A course examined within an examination, with components (e.g. internal, external) |
| Result run | One computation of results for an exam (revisioned) |
| Publication | A versioned, immutable release of an exam's results to students |
| Snapshot | The immutable per-student result document created at publication |
| Entitlement | A feature flag or limit a tenant has, derived from plan + overrides |
| RLS | PostgreSQL Row-Level Security |
| MVP / V1 | Release scopes defined in [04](04-feature-scope.md) |

### 1.4 References
ISO/IEC/IEEE 29148:2018; OWASP ASVS 4.x; India's Digital Personal Data Protection Act, 2023; project docs 01–20 in this folder.

---

## 2. Overall description

### 2.1 Product perspective
A new, self-contained, web-based SaaS. Interfaces: web browsers (users), email provider, object storage, payment provider (V1), institution ERPs via API (V1). See [context diagram](diagrams/component-diagram.md#1-system-context-c4-level-1).

### 2.2 Product functions (summary)
F1 Tenant onboarding · F2 Identity & access · F3 Entitlements · F4 Branding · F5 Academic structure · F6 Directory · F7 Examinations & grading · F8 Marks capture · F9 Import · F10 Processing · F11 Approval · F12 Publication & correction · F13 Student portal · F14 Marksheets · F15 Verification · F16 Notifications · F17 Analytics · F18 Audit · F19 Platform administration · F20 Data export.

### 2.3 User classes
| Class | Frequency | Technical skill | Key needs |
|---|---|---|---|
| Student | Few times per term, spiky | Low–medium, mobile | Speed, simplicity |
| Faculty | Daily during exam season | Medium | Fast entry, clear status |
| Institution admin/owner | Weekly; daily in season | Medium | Control, correctness, auditability |
| Platform admin | Daily | High | Overview, safe operations |
| Verifier | Rare, anonymous | Any | Trustworthy answer quickly |

### 2.4 Operating environment
Modern evergreen browsers (Chrome, Edge, Firefox, Safari — last 2 versions), Android Chrome on mid-range phones; server: Linux containers; PostgreSQL 16+; hosted in an Indian cloud region.

### 2.5 Design & implementation constraints
C-1 Modular monolith (FastAPI, PostgreSQL) · C-2 Shared-schema multi-tenancy with RLS · C-3 Host-based tenant routing · C-4 No fabricated performance claims · C-5 Infrastructure cost appropriate to small customers ([16](16-cost-model.md)) · C-6 Personal data handled per DPDP Act obligations as data processor.

### 2.6 Assumptions & dependencies
A-1 Institutions can provide student rosters and marks in CSV/XLSX. A-2 Students have an email or receive printed activation codes. A-3 A transactional email provider is available. A-4 Publication times are usually known in advance.

---

## 3. Use cases

Diagram: [use-case diagram](diagrams/use-case-diagram.md). Detailed specifications for the most important ones:

### UC-10 Import marks file
| | |
|---|---|
| Actors | Institution admin, Faculty (assigned papers only) |
| Preconditions | Exam in `MarksEntryOpen`; actor authenticated; papers configured |
| Main flow | 1. Actor uploads CSV/XLSX for an exam. 2. System stores and fingerprints file, parses it, proposes column mapping. 3. Actor confirms mapping. 4. System validates all rows and shows counts and issues. 5. Actor commits. 6. System upserts marks in one transaction, audits, marks results stale. |
| Alternate flows | 3a. Actor edits mapping → re-validation. 4a. Errors exist → actor downloads annotated file, fixes, re-uploads (new job supersedes old). 5a. Actor commits valid rows only → invalid rows listed in audit. 2a. Same file hash already committed → warning. |
| Exceptions | Unreadable file → job failed with reason. Paper locked → rows rejected (`PAPER_LOCKED`). |
| Postconditions | Marks stored; import job `Committed`; audit event recorded. |

### UC-12 Approve results
| | |
|---|---|
| Actors | Institution admin (checker ≠ processor in maker-checker mode) |
| Preconditions | Exam `Processed`, run not stale |
| Main flow | 1. Admin reviews preview and anomalies. 2. Admin re-authenticates and approves. 3. System freezes inputs, records content hash, pre-renders marksheets, prepares verification codes. |
| Alternate | 2a. Admin rejects with reason → exam returns to `MarksEntryClosed`. |
| Postconditions | Exam `Approved`; approval audited. |

### UC-13 Publish results
| | |
|---|---|
| Actors | Institution admin |
| Preconditions | Exam `Approved`; entitlement allows publishing |
| Main flow | 1. Admin chooses now or a scheduled time. 2. System creates publication and per-student snapshots. 3. At the time, system makes it live, activates verification, notifies students. |
| Alternate | 1a. Admin cancels a scheduled publication. 3a. Admin withdraws with reason → hidden from students, verification shows withdrawn. |
| Postconditions | Students can view results; notifications sent. |

### UC-15 View result
| | |
|---|---|
| Actors | Student |
| Preconditions | Student authenticated on own tenant host; publication live |
| Main flow | 1. Student opens dashboard. 2. System returns latest snapshot for that student only. 3. Student opens details, history, stats. |
| Exceptions | No publications → empty state. Overload → 429 with automatic retry. |

### UC-17 Verify marksheet
| | |
|---|---|
| Actors | Verifier (anonymous) |
| Main flow | 1. Scan QR → verification page. 2. System shows institution, exam, date, status, masked identity, document hash. |
| Alternate | 2a. Tenant allows challenge → verifier enters DOB/PIN to see full summary. 2b. Unknown code → generic not-found. |

---

## 4. Functional requirements

Priority: **M** = MVP, **V1**, **V2**. Each requirement is testable.

### F1 Tenant onboarding
| ID | Requirement | Pri |
|---|---|---|
| FR-1.1 | The system shall allow a prospective owner to sign up with name, email, password, institution name, type and slug. | M |
| FR-1.2 | The system shall validate slugs against format rules, reserved words and uniqueness. | M |
| FR-1.3 | The system shall create the tenant only after email verification, provisioning Free plan, owner account, default branding, settings and grading templates in one transaction. | M |
| FR-1.4 | The system shall present an onboarding checklist until the first publication. | M |
| FR-1.5 | The system shall support verified custom domains for tenants entitled to `custom_domain`. | V1 |

### F2 Identity & access
| ID | Requirement | Pri |
|---|---|---|
| FR-2.1 | Users shall authenticate with login id and password; passwords stored with Argon2id. | M |
| FR-2.2 | Sessions shall be opaque, server-side, stored hashed, delivered as `__Host-` HttpOnly Secure SameSite=Lax cookies, bound to a tenant. | M |
| FR-2.3 | A session shall be rejected on any host whose tenant differs from the session's tenant. | M |
| FR-2.4 | The system shall support logout, logout of all devices, and admin revocation of a user's sessions. | M |
| FR-2.5 | The system shall support password reset via single-use, expiring tokens without revealing account existence. | M |
| FR-2.6 | Staff shall be invited by email with single-use tokens valid for 7 days. | M |
| FR-2.7 | Students shall activate accounts with enrollment number plus single-use activation code or invite link. | M |
| FR-2.8 | The system shall enforce role permissions for `institution_owner`, `institution_admin`, `faculty`, `student`. | M |
| FR-2.9 | Faculty shall only access papers and cohorts assigned to them. | M |
| FR-2.10 | Platform users shall authenticate only on the platform host with mandatory TOTP. | M |
| FR-2.11 | Institution owners shall be able to enable TOTP (mandatory in V1). | M/V1 |
| FR-2.12 | Sensitive actions (publish, withdraw, role change, domain change, export) shall require re-authentication. | V1 |
| FR-2.13 | Login shall be rate-limited per IP and per account with progressive delays. | M |

### F3 Entitlements
| ID | Requirement | Pri |
|---|---|---|
| FR-3.1 | The system shall compute effective entitlements from active subscription plan values, tenant overrides (with expiry) and feature defaults. | M |
| FR-3.2 | Every limited action shall check the limit transactionally so concurrent requests cannot exceed it. | M |
| FR-3.3 | On limit breach the API shall return a problem response stating limit, current usage and maximum. | M |
| FR-3.4 | Platform admins shall change plans and create overrides; changes take effect immediately. | M |
| FR-3.5 | Expiry or downgrade shall not delete data; only new over-limit actions and premium features are blocked. | M |
| FR-3.6 | Online payment and GST invoices via payment provider. | V1 |

### F4 Branding
| ID | Requirement | Pri |
|---|---|---|
| FR-4.1 | Admins shall set display name, logo and primary colour; the tenant portal shall render with them. | M |
| FR-4.2 | Entitled tenants shall set secondary colour, font (allow-list), favicon, login text, footer, and hide "Powered by". | V1 |
| FR-4.3 | Colour choices shall be validated for WCAG AA contrast. | M |

### F5 Academic structure
| ID | Requirement | Pri |
|---|---|---|
| FR-5.1 | Admins shall manage academic sessions, terms, programs, cohorts and courses (create, edit, archive). | M |
| FR-5.2 | Departments shall be supported when the tenant is entitled to multiple departments. | M |
| FR-5.3 | Admins shall clone a session's structure into a new session. | V1 |
| FR-5.4 | Codes shall be unique per tenant (courses, programs) or per session (cohorts, terms). | M |

### F6 Directory
| ID | Requirement | Pri |
|---|---|---|
| FR-6.1 | Admins shall create, edit, archive and search students; enrollment numbers unique per tenant. | M |
| FR-6.2 | Admins shall import students via the import framework (F9). | M |
| FR-6.3 | Admins shall assign students to cohorts per session. | M |
| FR-6.4 | Admins shall manage staff accounts and roles; owner role transfer requires the current owner. | M |
| FR-6.5 | Admins shall assign faculty to exam papers and cohorts. | M |
| FR-6.6 | Admins shall generate printable activation-code sheets per cohort. | M |

### F7 Examinations & grading
| ID | Requirement | Pri |
|---|---|---|
| FR-7.1 | Admins shall create examinations for a term with cohorts and papers (course, components with maxima, pass rules, credits). | M |
| FR-7.2 | Admins shall define grading schemes using strategies: percentage bands, credit/SGPA, marks-only. | M |
| FR-7.3 | Grading scheme versions used by a result run shall be immutable. | M |
| FR-7.4 | Exam state transitions shall follow the [exam state machine](diagrams/state-diagrams.md#1-examination-lifecycle); illegal transitions rejected. | M |
| FR-7.5 | Ranks and percentiles shall be computable for marks-only exams. | V1 |
| FR-7.6 | CGPA across terms, grace-mark rules and supplementary exams. | V1 |

### F8 Marks capture
| ID | Requirement | Pri |
|---|---|---|
| FR-8.1 | Authorised users shall enter marks in a grid per paper × cohort with per-cell validation (range, precision, special codes). | M |
| FR-8.2 | Concurrent edits shall be detected with optimistic locking and reported as conflicts. | M |
| FR-8.3 | Faculty shall submit a paper; submitted papers are read-only for faculty until returned. | M |
| FR-8.4 | Admins shall view a completeness matrix of papers × cohorts by status. | M |

### F9 Import
| ID | Requirement | Pri |
|---|---|---|
| FR-9.1 | The system shall accept CSV and XLSX within configured size/row limits; macros and formulas are not executed. | M |
| FR-9.2 | The system shall store the raw file with SHA-256 and warn on duplicate content for the same target. | M |
| FR-9.3 | The system shall auto-map columns, allow manual mapping, and save mapping presets. | M (presets V1) |
| FR-9.4 | The system shall validate rows per [rule catalogue](13-result-ingestion.md#4-validation-rules) and report issues per row/column. | M |
| FR-9.5 | The system shall provide a downloadable annotated error file safe against formula injection. | M |
| FR-9.6 | The system shall not change live data until the user commits; commit is atomic and idempotent. | M |
| FR-9.7 | Pre-filled templates shall be downloadable per exam/paper. | M |

### F10 Processing
| ID | Requirement | Pri |
|---|---|---|
| FR-10.1 | Admins shall trigger result processing; computation runs asynchronously and is deterministic. | M |
| FR-10.2 | The system shall show a preview (distribution, pass %, per-student view) and anomaly list. | M |
| FR-10.3 | Any mark change after processing shall mark the run stale and block approval until re-processed. | M |

### F11 Approval
| ID | Requirement | Pri |
|---|---|---|
| FR-11.1 | Admins shall approve or reject processed results; approval records a content hash. | M |
| FR-11.2 | In maker-checker mode the approver shall differ from the processor. | V1 |
| FR-11.3 | Approval shall trigger marksheet pre-rendering and verification code preparation. | M |

### F12 Publication & correction
| ID | Requirement | Pri |
|---|---|---|
| FR-12.1 | Admins shall publish approved results immediately or at a scheduled time. | M |
| FR-12.2 | Publication shall create immutable per-student snapshots and statistics atomically. | M |
| FR-12.3 | Admins shall withdraw a publication with a mandatory reason. | M |
| FR-12.4 | Admins shall correct a published exam, producing a new version that supersedes the old; diff view shows changes. | V1 |
| FR-12.5 | Only one publication per exam shall be live at a time. | M |

### F13 Student portal
| ID | Requirement | Pri |
|---|---|---|
| FR-13.1 | Students shall view their latest result, result details, and history of all live publications. | M |
| FR-13.2 | Student APIs shall derive identity solely from the session (no student identifier parameters). | M |
| FR-13.3 | Students shall view aggregate statistics permitted by the tenant. | M |
| FR-13.4 | Students shall see revision notices on corrected results. | V1 |
| FR-13.5 | Students shall manage profile basics and password. | M |

### F14 Marksheets
| ID | Requirement | Pri |
|---|---|---|
| FR-14.1 | The system shall generate a PDF marksheet per student per publication using the tenant's template, logo and a QR code. | M |
| FR-14.2 | Marksheets shall be downloadable only by the owning student (and admins) via short-lived signed URLs. | M |
| FR-14.3 | Template library and custom templates per entitlement. | V1 |

### F15 Verification
| ID | Requirement | Pri |
|---|---|---|
| FR-15.1 | Each published marksheet shall have a 128-bit random verification code. | M |
| FR-15.2 | The public verification page shall show institution, exam, publication date, status and masked identity and document hash. | M |
| FR-15.3 | Verification status shall reflect superseded, withdrawn and revoked states. | M |
| FR-15.4 | Verification shall be rate-limited and not indexed by search engines. | M |
| FR-15.5 | Optional challenge (DOB/PIN) to disclose full summary. | V1 |
| FR-15.6 | PDF upload comparison against stored hash. | V1 |

### F16 Notifications
| ID | Requirement | Pri |
|---|---|---|
| FR-16.1 | On publication, affected students shall receive in-app notifications. | M |
| FR-16.2 | On publication, students with email shall receive an email containing a link but no marks. | M |
| FR-16.3 | Delivery status shall be tracked with retries. | M |
| FR-16.4 | Tenant-customisable templates; staggered sending. | V1 |
| FR-16.5 | SMS/WhatsApp channels. | V2 |

### F17 Analytics
| ID | Requirement | Pri |
|---|---|---|
| FR-17.1 | Per-exam statistics: pass %, grade distribution, mean/median/stdev per paper. | M |
| FR-17.2 | Trends across terms and comparisons for entitled tenants. | V1 |

### F18 Audit
| ID | Requirement | Pri |
|---|---|---|
| FR-18.1 | Every state-changing operation shall record who, what, when, tenant, entity, before/after, request context — in the same transaction. | M |
| FR-18.2 | Admins shall browse and filter the tenant audit log. | M |
| FR-18.3 | Audit records shall be append-only for the application. | M |
| FR-18.4 | Tamper-evident hash chain and export. | V1 |

### F19 Platform administration
| ID | Requirement | Pri |
|---|---|---|
| FR-19.1 | Platform admins shall list/search tenants with plan, status, students, last activity. | M |
| FR-19.2 | Platform admins shall suspend/reactivate tenants; suspended tenants show an unavailable page. | M |
| FR-19.3 | Platform admins shall view platform health and key metrics (requests, errors, latency, cache hit rate, queue depth). | M |
| FR-19.4 | Support sessions to view tenant data shall be time-boxed, reason-logged and visible to the tenant. | V1 |

### F20 Data export & offboarding
| ID | Requirement | Pri |
|---|---|---|
| FR-20.1 | Owners shall export all tenant data as CSV/JSON archive. | V1 |
| FR-20.2 | Tenant closure shall follow a grace period and then delete tenant data. | V1 |

---

## 5. Non-functional requirements

Performance figures are **targets to be measured** per [11](11-performance-architecture.md); acceptance is based on measured results recorded in `benchmarks/results/`.

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | Isolation | No request authenticated for tenant A can read or modify tenant B's data; verified by the automated isolation suite with 100% pass required for release. |
| NFR-2 | Security | Meet OWASP ASVS Level 2 controls relevant to the application before commercial launch. |
| NFR-3 | Performance | Student latest-result endpoint p95 < 150 ms server-side at the peak RPS of load scenario B (target, measured). |
| NFR-4 | Performance | Login p95 < 500 ms at scenario B login rate (target, measured). |
| NFR-5 | Performance | Validation of a 10,000-row marks file < 60 s (target, measured). |
| NFR-6 | Performance | Processing 8,000 students × 6 papers < 2 min (target, measured). |
| NFR-7 | Reliability | Error rate (5xx) < 0.1% during publication load scenarios (target, measured). |
| NFR-8 | Availability | Small production: architecture with no single application node; availability is reported from uptime monitoring, not claimed. |
| NFR-9 | Recoverability | RPO ≤ 5 min and RTO ≤ 4 h in small production, validated by monthly restore drills. |
| NFR-10 | Correctness | Grading computations deterministic; grading modules ≥ 90% branch coverage plus property-based tests. |
| NFR-11 | Auditability | 100% of state-changing endpoints emit audit events (checked by a route-level test). |
| NFR-12 | Usability | Student reaches latest result in ≤ 2 taps after login; student portal usable at 360 px width. |
| NFR-13 | Accessibility | WCAG 2.1 AA for student and admin portals (automated axe checks + manual review). |
| NFR-14 | Maintainability | Module boundaries enforced by import-linter; lint, type and test gates in CI. |
| NFR-15 | Portability | Runs via Docker on any Linux host; no provider-specific code outside adapters. |
| NFR-16 | Scalability | API and workers stateless and horizontally scalable; scaling demonstrated by comparing 1 vs 2 API nodes in load tests. |
| NFR-17 | Privacy | No marks/PII in logs; data hosted in India; minimal PII collected; export and deletion supported. |
| NFR-18 | Cost | Demo deployable for under ~₹3,000/month; small production under ~₹25,000/month (estimates in [16](16-cost-model.md)). |
| NFR-19 | Observability | Structured logs with request and tenant ids; metrics for RED, DB, cache, jobs; health endpoints. |
| NFR-20 | Frontend performance | Student initial JS < 150 KB gzipped (CI budget). |

---

## 6. External interface requirements
- **User interfaces:** responsive web (see [09](09-frontend-architecture.md)).
- **Software interfaces:** PostgreSQL 16+, Redis 7 (optional), S3-compatible storage, SMTP/HTTP email provider, Razorpay (V1).
- **Communication interfaces:** HTTPS only (TLS 1.2+), HSTS; REST/JSON API documented by OpenAPI 3.1.

---

## 7. Traceability matrix

Test IDs follow `T-<area>-<n>`; suites listed in [15](15-testing-strategy.md). (Populated progressively; this is the initial mapping.)

| Requirement | Design reference | Test(s) |
|---|---|---|
| FR-1.3 | [03 W1](03-core-workflows.md#w1-sign-up-and-tenant-creation-self-serve) | T-ONB-1 provisioning integration, E2E-1 |
| FR-2.2, FR-2.3 | [10 §2](10-security-architecture.md#2-authentication) | T-SEC-AUTH-*, T-ISO-HOSTSWAP |
| FR-2.9 | [10 §3](10-security-architecture.md#3-authorization-rbac--ownership--entitlements) | T-AUTHZ-MATRIX |
| FR-3.2 | [12 §3](12-entitlements.md#3-enforcing-limits-correctly-race-conditions) | T-ENT-RACE |
| FR-7.2, FR-7.3 | [08 §7](08-backend-architecture.md#7-grading-engine-heart-of-correctness) | T-GRD-GOLDEN-*, T-GRD-PROP-* |
| FR-9.4–9.6 | [13](13-result-ingestion.md) | T-IMP-RULE-*, T-IMP-GOLDEN-*, T-IMP-ATOMIC |
| FR-12.2, FR-12.5 | [05 §4](05-system-design.md#4-write-path-vs-read-path-cqrs-lite) | T-PUB-ATOMIC, T-PUB-ONELIVE |
| FR-13.2 | [06 L3](06-multi-tenancy.md#l3--application-layer) | T-ISO-STUDENT |
| FR-15.1–15.4 | [10 §10](10-security-architecture.md#10-result-verification-18) | T-VER-* |
| FR-18.1, NFR-11 | [10 §9](10-security-architecture.md#9-audit-logging-20) | T-AUD-ROUTES, T-AUD-TX |
| NFR-1 | [06](06-multi-tenancy.md) | T-ISO-* (merge gate) |
| NFR-3–7 | [11 §4](11-performance-architecture.md#4-benchmark-plan-scientifically-valid) | LOAD-A..D reports |
| NFR-9 | [10 §12](10-security-architecture.md#12-backup-recovery-deletion) | OPS-RESTORE-DRILL |
