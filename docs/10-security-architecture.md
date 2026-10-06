# 10 · Security Architecture

> Covers brief section **L**, §18 (result verification), §19 (security), §20 (audit logging).
> Tenant isolation layers are detailed in [06 Multi-tenancy](06-multi-tenancy.md#3-the-five-isolation-layers) — this document covers everything else and the threat model.

---

## 1. Assets, actors, threats (lightweight STRIDE)

**Assets:** student results & marks (confidential until publication; integrity-critical forever), student PII (names, DOB, contacts — often minors), credentials/sessions, institution configuration, audit trail, issued marksheets' authenticity.

| Threat | Example | Primary controls |
|---|---|---|
| **S**poofing | Credential stuffing on student logins; phishing admin | Argon2id, rate limits + lockout, breached-password check, 2FA for admins (V1, mandatory for owners), host-only cookies |
| **T**ampering | Faculty changes marks after approval; insider edits DB; forged marksheet | State-machine locks, maker–checker, append-only audit, content hashes, QR verification, immutable publications |
| **R**epudiation | "I never published that" | Audit log with actor, IP, request id, before/after; hash chain (V1) |
| **I**nformation disclosure | IDOR across students/tenants; results before publication; PII in logs; public S3 bucket | 5-layer tenant isolation, `/me` APIs, publication gate on read model, private buckets + signed URLs, log scrubbing |
| **D**enial of service | Result-day flood; huge upload; expensive export loops | CDN, rate limits, upload size/row caps, per-tenant job concurrency, statement timeouts |
| **E**levation of privilege | Faculty calls admin endpoint; student mass-assigns `role` | Server-side permission checks per route, explicit Pydantic input schemas (no mass assignment), RBAC tests |

---

## 2. Authentication

### JWT vs server-side sessions
| | Stateless JWT (access + refresh) | **Opaque server-side session (chosen)** |
|---|---|---|
| Revocation (logout everywhere, disable user, suspend tenant) | Hard — needs denylist (state again) or short TTL + refresh complexity | Immediate: delete/revoke row |
| Token theft impact | Valid until expiry | Revocable; can bind to tenant/host |
| Storage in browser | Often `localStorage` (XSS-exposed) | HttpOnly cookie (not readable by JS) |
| Per-request cost | Signature verify, no DB | One indexed lookup — cached in Redis/in-process for ~60 s |
| Fits | Third-party APIs, microservices | First-party web app on its own domain |

**Decision:** opaque sessions for browsers; **API keys** (hashed, scoped, prefixed) for Pro integrations; OIDC/SAML (V2/Enterprise) creates a normal session after SSO.

### Session details
- 256-bit random token in cookie `__Host-sc_session` (the `__Host-` prefix forces `Secure`, `Path=/`, **no Domain** → host-only). `HttpOnly`, `SameSite=Lax`.
- DB stores only `SHA-256(token)` → a DB leak does not yield usable sessions.
- Lifetimes: students 30 days sliding (encourages pre-result-day login), staff 12 h idle / 7 days absolute, platform 8 h + re-auth for sensitive actions.
- Session rotation on login and privilege change (prevents fixation).
- "Log out of all devices" + admin "revoke all sessions for user".

### Passwords
- **Argon2id** (`argon2-cffi`), parameters tuned so one hash costs ~50–100 ms on production CPU (measure and document; re-hash on login when parameters change).
- Minimum length 10 (staff 12), no composition rules, check against a breached-password list (k-anonymity HIBP API or local top-N list), allow paste/password managers.
- Lockout: progressive delay per account + per IP; never reveal whether an account exists ("If an account exists, we sent an email").

### Student activation (avoid the DOB-password anti-pattern)
Activation code (one-time, 10 chars, expires) or invite link → student sets own password. See [03 W4](03-core-workflows.md#w4-student-roster-import-and-activation).

### Admin protection
- TOTP 2FA: mandatory for platform users from day one; mandatory for `institution_owner` in V1 (optional MVP), optional for others.
- Re-authentication (password prompt) for: publish, withdraw, role changes, domain changes, data export.

---

## 3. Authorization (RBAC + ownership + entitlements)

Three independent checks on every protected operation:
```
allowed = role_has_permission(principal.roles, "marks.enter")         # RBAC
          and resource_in_scope(principal, paper, cohort)              # ownership/assignment (ABAC-lite)
          and resource_state_allows(paper.status, "enter")             # state machine
          and entitlements.has(tenant, feature) / within_limit(...)    # commercial gate
```

| Role | Key permissions (abridged) |
|---|---|
| `institution_owner` | everything in tenant incl. subscription, branding, domain, owner transfer |
| `institution_admin` | structure, people, exams, imports, processing, approve*, publish*, analytics, audit view (*subject to approval mode) |
| `faculty` | view assigned papers, enter/import marks for assigned paper×cohort while open, submit, stats for assigned |
| `student` | `/me/*` only |
| `platform_admin` | platform console; tenant data only via audited support session |

- Permission checks live in services (not only routers) so jobs and internal calls are covered.
- **Default deny**: a route without an explicit permission dependency fails a CI test that enumerates all routes.

---

## 4. Input validation & injection prevention
- Pydantic v2 schemas for every request with `extra="forbid"` (blocks mass assignment like `{"role":"admin"}`).
- SQL only via SQLAlchemy Core/ORM with bound parameters; raw SQL forbidden except reviewed, parameterised migration/report code (Bandit/semgrep rule in CI).
- Output encoding: React escapes by default; `dangerouslySetInnerHTML` banned by lint rule. Tenant-supplied text (login message, footer) is plain text or a strict Markdown subset sanitised server-side.
- Marksheet templates: Jinja **sandboxed environment**, autoescape on, no file system or network access; PDF renderer configured to block external URL fetches (only our object-store assets via a URL allow-list) → prevents SSRF via templates.
- **CSV/formula injection**: any exported CSV/XLSX cell beginning with `= + - @` (tab/CR too) is prefixed with `'` so opening the error report in Excel cannot execute formulas.

## 5. CSRF, CORS, headers
- SameSite=Lax cookie + **double-submit CSRF token** (`X-CSRF-Token` header must match a non-HttpOnly cookie) on POST/PUT/PATCH/DELETE.
- CORS: not needed for same-origin SPA; no wildcard origins ever.
- Headers: `Strict-Transport-Security` (preload after stabilising), `Content-Security-Policy` (`default-src 'self'`; images from our CDN/object store; no inline scripts except hashed bootstrap), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` minimal, `frame-ancestors 'none'`.

## 6. File upload security
- Allow-list: `.csv`, `.xlsx` (imports); `.png`, `.jpg`, `.webp`, `.svg`→ **rasterised or rejected** (SVG can carry scripts) for logos.
- Max size (e.g. 10 MB imports, 1 MB logos), max rows (e.g. 50k per import), max columns, max sheet count; reject macros (`.xlsm`) and parse XLSX with `openpyxl` in **read-only mode**, data-only (formulas not evaluated), in the worker (not the API process), with a CPU/time limit — protects against zip bombs and decompression attacks (also check uncompressed size).
- Content sniffing (magic bytes) must match extension.
- Stored in private object storage under `tenants/{tenant_id}/uploads/{uuid}`; original filename only in DB metadata.
- Malware scan (ClamAV sidecar) — V1 for logos/templates; imports are parsed as data, never served back raw to other users.

## 7. Rate limiting & abuse prevention
| Bucket | Example limit (tune after load tests) |
|---|---|
| Login per IP | 20/min, burst 10 |
| Login per account | 5 failures → exponential backoff |
| Password reset per account/IP | 3/hour |
| Activation attempts per enrollment no. | 5/hour |
| Activation attempts per IP | 120/hour, burst 60 — a whole class often activates from one school network; a 10-character code stays unguessable at this rate (`SCORECODE_RATE_ACTIVATION_IP_PER_HOUR`) |
| Verification lookups per IP | 60/min |
| Authenticated API per session | 300/min |
| Imports per tenant | 10/hour |
| Sign-ups per IP | 5/hour |
Implemented as token buckets in Redis (Lua, atomic) with in-process fallback; edge (Cloudflare) rules as an outer layer. Responses: `429` + `Retry-After`.

## 8. Secrets & keys
- Secrets via environment from a secret manager / SOPS-encrypted files; rotated on staff change; separate per environment.
- Application-level encryption (AES-GCM via `cryptography`) for especially sensitive columns: TOTP secrets, integration credentials. Student marks are not field-encrypted (they must be queried/aggregated) — protected by DB encryption at rest (managed DB) + access control.
- TLS everywhere, including app → DB (`sslmode=verify-full` on managed DBs).

---

## 9. Audit logging (§20)

Every state-changing service call records an event **in the same transaction** as the change (so there is never a change without its audit record, and never an audit record for a rolled-back change).

| Field | Answers |
|---|---|
| `actor_type`, `actor_id`, (`impersonated_by` for support sessions) | **WHO** |
| `action` (e.g. `marks.updated`, `publication.published`) | **WHAT** |
| `occurred_at` (UTC) | **WHEN** |
| `tenant_id` | **WHICH TENANT** |
| `entity_type`, `entity_id` | **ON WHAT** |
| `before`, `after` (field-level diff; for bulk ops a summary + reference to import job) | **WHAT CHANGED / FROM → TO STATE** |
| `request_id`, `ip`, `user_agent`, `reason` (mandatory for sensitive actions) | context |

Events (minimum set): `tenant.created/suspended/plan_changed`, `user.invited/role_changed/disabled/login_failed_lockout`, `student.created/updated/archived/imported`, `exam.created/updated/unlocked`, `marks.updated` (cell-level diffs), `import.committed`, `results.processed/approved/rejected`, `publication.scheduled/published/withdrawn/corrected`, `branding.updated`, `domain.verified`, `settings.updated`, `export.requested`, `support_session.started/ended`.

Integrity:
- App DB role has `INSERT, SELECT` only on `audit_logs`.
- V1: per-tenant **hash chain** — `hash = SHA-256(prev_hash || canonical_json(event))`; a verifier job recomputes chains nightly; the latest chain head per tenant is periodically copied to the platform audit (and optionally to object storage with object-lock) so silent rewrites are detectable.
- Monthly partitions; old partitions exported to object storage before detachment.

---

## 10. Result verification (§18)

### Design
```
QR on marksheet → https://verify.scorecode.in/v/7KQ3-M9XD-PA2F-8RTC-WV6H-Q (code)
```
| Concern | Design |
|---|---|
| Token generation | 128 bits from `secrets.token_bytes(16)`, Crockford base32 (26 chars, grouped). **Random**, not derived from student/exam IDs → not guessable, not enumerable (2^128). Unique index. |
| Tamper resistance | The page shows the authoritative data from our DB, not data from the QR. It also shows the **SHA-256 of the issued PDF**; a verifier can compare it (or upload the PDF for automatic comparison — V1). Edited PDFs fail the hash; forged QR codes point to non-existent or mismatching records. |
| Privacy | Default disclosure: institution, exam, publication date, status, **masked** name (`An*** Sh***`) and masked enrollment no. Full marks only after a challenge (DOB or a per-marksheet consent PIN printed beside the QR) if the tenant enables it. `noindex` meta + `X-Robots-Tag` so pages aren't search-indexed. |
| Revocation | `verification_records.status`: `active` → `superseded` (correction), `withdrawn` (publication withdrawn), `revoked` (fraud/error, with reason). Page shows status prominently with date. |
| Records | Every lookup increments counters (aggregated; no verifier PII stored beyond rate-limit IP window). |
| Abuse | Per-IP rate limit, generic "not found" for bad codes, CDN caching of *not-found* responses briefly. |
| V2 | Offline-verifiable signed payload: QR includes an Ed25519 signature over a canonical summary, verifiable with ScoreCode's published public key even without network; key rotation via `kid`. |

---

## 11. Privacy & compliance (India)
- **Digital Personal Data Protection Act, 2023 (DPDP)** and its Rules: institutions are *data fiduciaries*; ScoreCode acts as a *data processor* on their behalf → Data Processing Agreement in Terms of Service; purpose limitation; security safeguards; breach notification process; deletion on contract end. Processing children's data has additional obligations (verifiable parental consent) that sit primarily with the institution — **get a lawyer's review before onboarding schools**; the product should support consent records if required.
- Data residency: host in an Indian region by default (e.g. AWS `ap-south-1` Mumbai, or Indian DCs of DigitalOcean/Azure/GCP).
- Data minimisation: DOB optional; Aadhaar numbers **never collected**.
- Export & deletion: [03 W18](03-core-workflows.md#w18-data-export-and-offboarding).

## 12. Backup, recovery, deletion
| | Target (to be validated by drills) |
|---|---|
| RPO (data loss window) | ≤ 5 min with managed PITR (small prod); ≤ 24 h on demo tier |
| RTO (time to restore) | ≤ 4 h small prod; documented runbook |
| Backup copies | Managed snapshots + nightly encrypted `pg_dump` to a second provider/region object storage; object storage versioning for PDFs |
| Drills | Monthly automated restore to a scratch DB + smoke test; result recorded in ops log |

## 13. Security testing & process
SAST (Bandit/semgrep, ESLint security rules), dependency scanning (pip-audit, `pnpm audit`, Dependabot), secret scanning (gitleaks), container scanning (Trivy), DAST baseline (OWASP ZAP) against staging, tenant-isolation suite, authorization matrix tests, and a pre-launch manual review against the **OWASP ASVS Level 2** checklist. Details: [15 Testing](15-testing-strategy.md).
