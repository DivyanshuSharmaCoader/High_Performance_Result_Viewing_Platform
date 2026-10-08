# 10 · Security Architecture

> Covers brief section **L**, §18 (result verification), §19 (security), §20 (audit logging).
> Tenant isolation layers are detailed in [06 Multi-tenancy](06-multi-tenancy.md#3-the-five-isolation-layers) — this document covers everything else and the threat model.

---

## 1. Assets, actors, threats (lightweight STRIDE)

**Assets:** student results & marks (confidential until publication; integrity-critical forever), student PII (names, DOB, contacts — often minors), credentials/sessions, institution configuration, audit trail, issued marksheets' authenticity.

| Threat | Example | Primary controls |
|---|---|---|
| **S**poofing | Credential stuffing on student logins; phishing admin | Argon2id, rate limits + lockout, breached-password check, two-step sign-in for staff (built in P15.5; see §1.1), host-only cookies |
| **T**ampering | Faculty changes marks after approval; insider edits DB; forged marksheet | State-machine locks, maker–checker, append-only audit, content hashes, QR verification, immutable publications |
| **R**epudiation | "I never published that" | Audit log with actor, IP, request id, before/after; hash chain (V1) |
| **I**nformation disclosure | IDOR across students/tenants; results before publication; PII in logs; public S3 bucket | 5-layer tenant isolation, `/me` APIs, publication gate on read model, private buckets + signed URLs, log scrubbing |
| **D**enial of service | Result-day flood; huge upload; expensive export loops | CDN, rate limits, upload size/row caps, per-tenant job concurrency, statement timeouts |
| **E**levation of privilege | Faculty calls admin endpoint; student mass-assigns `role` | Server-side permission checks per route, explicit Pydantic input schemas (no mass assignment), RBAC tests |

### 1.1 As built (P15.1 review, 2026-10-08)
Each row below names the threat, the attack we expect against ScoreCode, the control that exists *in code*, and the evidence: a test, a measurement or a CI job. "Open" items are tracked below the table.

| Threat | Concrete attack | Control as built | Evidence |
|---|---|---|---|
| S · credential stuffing on result day | Botnet replays leaked passwords against student logins | Argon2id (t=2, m=19 MiB) with bounded concurrency; failure bucket 60/min per **real client address** (Caddy-resolved `X-Real-IP`, never a CDN edge); per-account limit + progressive lockout; **breached-password check** (HIBP k-anonymity) on every new password | `test_auth.py` rate-limit/lockout tests; `test_client_address_comes_only_from_the_header_our_proxy_overwrites`; `test_breached_passwords.py`; k6 B-cold found and fixed shared-bucket bug |
| S · admin account takeover | Phished owner password | **Two-step sign-in** for staff (TOTP, single-use codes, recovery codes); re-auth with both factors for publish/withdraw/role/ownership/revocation; owner's second factor not resettable by admins | `test_mfa.py` (4 mutations caught) |
| S · forged marksheet / verifier fooled | Edited PDF, fake QR to look-alike domain | 128-bit random codes; verify page shows DB truth + PDF SHA-256; never data from the QR; status derived from the publication | `test_marksheets.py` lifecycle; E2E-4 compares the downloaded file's hash |
| T · marks changed after approval | Faculty/admin edits marks once results are approved | Exam state machine; marks writers lock the exam row; approval rechecks the input hash; maker-checker | `test_results.py`, `test_marks.py` |
| T · snapshot edited in the DB | Insider `UPDATE published_results` | App role lacks UPDATE; trigger refuses UPDATE/DELETE for **every** role incl. owner | `test_snapshots_cannot_be_changed_by_anyone` |
| T · audit trail edited | Cover-up after a bad change | App role SELECT/INSERT only on `audit_logs`; written in the same transaction as the change | `test_kernel.py` append-only tests; `test_audit.py` (UPDATE refused) |
| R · "I never did that" | Disputed publication/withdrawal/revocation | Audit with actor, IP (real client), request id, before/after, reason | Audit viewer filters + `test_audit.py` |
| I · cross-tenant read | IDOR with another tenant's ids; replayed session cookie on another host | Host-bound tenant; RLS forced + fail-closed; composite FKs; ORM tenant criteria; isolation suite generated from the live route table | `test_isolation.py` (every route), `test_kernel.py` RLS coverage |
| I · another student's result | Student swaps a publication id | Student APIs take identity from the session only; `no-store` | `test_publishing.py`, `test_marksheets.py` (same id → own marksheet) |
| I · results before publication | Guess scheduled publication ids; verify a scheduled code | Read model gated by publication status; verify lookup treats scheduled/cancelled as unknown | `test_a_scheduled_publication_cannot_be_verified_until_it_goes_live` |
| I · SSRF / local file read via PDFs | Name or template pointing at `http://169.254.169.254` or `file:///etc/passwd` | Sandboxed Jinja + autoescape; WeasyPrint fetcher serves `data:` only | `test_rendering_never_fetches_external_urls` (live server + control) |
| I · PII in logs/emails | Marks in notification emails; secrets in logs | Emails carry links only; structured logging redacts secrets; delivery errors store exception type only | `test_notifications.py` (no marks in email), `test_core.py` redaction |
| D · result-day overload | 1,000 students at once | Measured baselines; pool exhaustion → retryable 503; DB outage → retryable 503; SPA jittered retries; no polling of inbox counts | `benchmarks/results/2026-10-08-k6-*.md`; `test_connection_usage.py`; `test_outages.py` |
| D · hostile uploads | Zip bomb XLSX, 1 M-row CSV, polyglot files | Magic-byte sniffing, size/row/column/uncompressed caps, streamed parsing, markup refused | `test_import_engine.py`, `test_imports.py` |
| D · trial/sign-up abuse | Scripted sign-ups, repeat trials | Honeypot, per-IP limits, hashed identity signals with advisory locks | `test_trials.py`; sign-up honeypot in `test_admin_flows.py` |
| E · faculty → admin | Faculty calls admin routes; mass-assigns `role` | Per-route permissions; `extra="forbid"` schemas; authz matrix over every route × role | `test_authz_matrix.py`, `test_mass_assignment_is_rejected` |

**Open (tracked):** email bounce webhooks (provider choice, Phase 16); DAST against a deployed staging host (P15.4 runs ZAP against the CI stack instead: [results](security/zap-baseline-2026-10-08.md)); `style-src 'unsafe-inline'` on the SPAs (accepted risk R-CSP, §5); per-tenant policy to *require* two-step for administrators (today: available + nudged); WebAuthn/passkeys (V1).

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
- **As built (edge, `infra/caddy/Caddyfile`; checked by `e2e/edge.spec.ts`).**
  - **SPAs:**
    - CSP is `default-src 'self'; script-src 'self'`, with no inline or evaluated script at all, plus `frame-ancestors 'none'` and `object-src 'none'`.
    - Images may come from the files origin.
    - Isolation headers: `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin` and `Cross-Origin-Embedder-Policy: credentialless`, so the pages are cross-origin isolated. Logos still load from the files host, by signed URL and without credentials.
  - **Accepted risk R-CSP:** `style-src` keeps `'unsafe-inline'` on the SPAs.
    - Why: toasts (sonner) and the dialogs' scroll lock (react-style-singleton) insert `<style>` elements at run time.
    - Exposure: an attacker would first need an HTML-injection bug (React escapes all text), and then could only restyle the page or probe attributes with selectors. Script execution stays impossible under `script-src 'self'`.
    - What removes it: nonces, which need per-request HTML, i.e. the SPA's `index.html` rendered by the edge.
  - **Defaults, never overrides:** `Referrer-Policy`, `Permissions-Policy`, COOP and CORP are set by the edge only when the response didn't set them.
    - Before 2026-10-09 the edge overwrote them, which replaced the verify page's `no-referrer` with `strict-origin-when-cross-origin`. Found while analysing the ZAP baseline.
    - `X-Content-Type-Options`, `X-Frame-Options` and the removal of `Server` are always applied.
  - **Caching:** `index.html` is revalidated under every app route (`no-cache`), and hashed assets are immutable.
    - An asset name a deploy removed answers 404 `no-store`, rather than `index.html` cached for a year under that name.

## 6. File upload security
- Allow-list: `.csv`, `.xlsx` (imports); `.png`, `.jpg`, `.webp`, `.svg`→ **rasterised or rejected** (SVG can carry scripts) for logos.
- Max size (e.g. 10 MB imports, 1 MB logos), max rows (e.g. 50k per import), max columns, max sheet count; reject macros (`.xlsm`) and parse XLSX with `openpyxl` in **read-only mode**, data-only (formulas not evaluated), in the worker (not the API process), with a CPU/time limit — protects against zip bombs and decompression attacks (also check uncompressed size).
- Content sniffing (magic bytes) must match extension.
- Stored in private object storage under `tenants/{tenant_id}/uploads/{uuid}`; original filename only in DB metadata.
- Malware scan (ClamAV sidecar) — V1 for logos/templates; imports are parsed as data, never served back raw to other users.

## 7. Rate limiting & abuse prevention
| Bucket | Example limit (tune after load tests) |
|---|---|
| Login per IP, every attempt | 3,000/min, burst 1,000: a flood ceiling only. A school lab, or thousands of phones behind one mobile carrier's NAT, share an address on result day (`SCORECODE_RATE_LOGIN_IP_PER_MINUTE`) |
| Login per IP, **failed** attempts | 60/min, burst 60 (credential stuffing); once exhausted, that address waits even with a correct password (`SCORECODE_RATE_LOGIN_FAILURES_IP_PER_MINUTE`). Each account also has its own limit and progressive lockout |
| Login per account | 5 failures → exponential backoff |
| Password reset per account/IP | 3/hour |
| Activation attempts per enrollment no. | 5/hour |
| Activation attempts per IP | 120/hour, burst 60 — a whole class often activates from one school network; a 10-character code stays unguessable at this rate (`SCORECODE_RATE_ACTIVATION_IP_PER_HOUR`) |
| Verification lookups per IP | 60/min |
| Authenticated API per session | 300/min |
| Imports per tenant | 10/hour |
| Sign-ups per IP | 5/hour, plus a hidden honeypot field: bots that fill it get the normal "check your email" answer and nothing is created or sent (counted in `scorecode_signup_honeypot_total`) |
| Free-trial starts per IP | 5/hour; one trial per institution, enforced with hashed identity signals (docs/12 §6) |
Implemented as token buckets in Redis (Lua, atomic) with in-process fallback; edge (Cloudflare) rules as an outer layer. Responses: `429` + `Retry-After`.

**Which address is "the IP".** Per-IP limits are only as good as the address they key on. Caddy works it
out: `trusted_proxies` lists the proxies in front of it (a CDN's published ranges in production;
`TRUSTED_PROXIES`), and with `trusted_proxies_strict` it reads `X-Forwarded-For` from the right and takes
the first hop it does not trust. A client can prepend whatever it likes to that header and it is never
reached. Caddy then **overwrites** `X-Real-IP` with that address, and the API reads only `X-Real-IP`
(when `SCORECODE_TRUST_PROXY_HEADERS`), never `X-Forwarded-For`. The right-most `X-Forwarded-For` entry is
the nearest proxy: behind a CDN that is an edge server shared by a whole city, so keying on it put every
student in one sign-in bucket. The P10.6 load test found exactly that: 601 of 1,000 cold sign-ins got
429 (benchmarks/results/2026-10-08-k6-scenarios-A-B.md). Covered by
`test_client_address_comes_only_from_the_header_our_proxy_overwrites` and
`test_students_behind_one_cdn_edge_get_their_own_sign_in_buckets`.

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

**As built (P11.1–P11.5):**
- **Lookup.** The verify host has no tenant, so a code is the only key. `verification_lookup(code)` (SECURITY DEFINER) returns the tenant id and status and nothing else; the record is then read under that tenant's RLS. Status is derived from the publication, so it can't drift.
- **Disclosure.**
  - Shown: masked name (`Aa*** Gu***`), masked enrollment no. (`10*****01`), institution, exam, issue date, version, status with its date, and the PDF's SHA-256.
  - Never shown: marks, or the revocation reason.
  - Codes from scheduled or cancelled publications look exactly like unknown codes. An institution that has left shows nothing about the student.
- **Page.** Server-rendered with no scripts.
  - CSP `default-src 'none'; style-src 'sha256-…'; img-src data:; form-action 'self'`. The hash is that of the page's one stylesheet, computed from the template at start-up. There are no `style` attributes, so no `'unsafe-inline'`.
  - `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy: same-origin`, plus `Cross-Origin-Embedder-Policy: require-corp`.
  - `X-Robots-Tag: noindex, nofollow, noarchive` and `Referrer-Policy: no-referrer`, because the code is in the URL.
  - `no-store` when a statement is found; `public, max-age=60` for not-found, so a CDN can absorb repeated bad lookups.
  - Per-IP limit of 60/min with a burst of 30, answered with an HTML 429 page and `Retry-After`.
  - Autoescaped, so tenant-controlled names are printed, never interpreted (tested with a `<script>` institution name).
- **PDF generation (SSRF).**
  - Jinja `SandboxedEnvironment` with autoescape and StrictUndefined.
  - WeasyPrint gets a fetcher that serves only `data:` URIs (the logo, from sniffed PNG/JPEG/WebP bytes, never SVG; and the QR code). `http(s)`, `file:` and everything else are refused.
  - Tested against a live local HTTP server: stylesheets, `@import`, fonts, images, `file:///etc/passwd`, objects and iframes all produce zero requests. A control request proves the server was reachable.
- **Downloads.** Signed object-storage URLs that expire in 120 s, with `Content-Disposition: attachment` and a sanitised filename. A student's marksheet is located through the student linked to the session only.
- **Revocation.** Per student, with re-authentication, a reason and an audit entry. It can't be undone; issue a corrected result instead.

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
