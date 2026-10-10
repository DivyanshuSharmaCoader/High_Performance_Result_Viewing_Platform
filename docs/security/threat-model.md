# Threat model (P18.7)

What could go wrong for a school using ScoreCode, what stops it, how we know, and what is left. The
attack-by-attack table with its tests is in [10 §1.1](../10-security-architecture.md#11-as-built-p151-review-2026-10-08);
this document adds the OWASP Top 10 (2021) view, the threats the production mission names, the features
added since (corrections, exports, Sentry, the server), scan results, and the risks that remain.
It claims no "zero vulnerabilities": it records what ran and what it found.

**Assets.** Marks and results (confidential until published, integrity-critical for ever); students'
personal data, mostly about minors (names, dates of birth, guardians, contacts); staff credentials and
sessions; issued marksheets' authenticity; the audit trail; backups; the operator's secrets.

**Actors.** Anonymous internet users; students and parents (one student account per child, by activation
code); faculty; institution administrators and owners; ScoreCode staff (platform console); the operator
(server, secrets); our providers (Cloudflare, Hostinger, R2, AWS S3, Brevo, Sentry, GitHub).

**Trust boundaries.** Browser ↔ Cloudflare ↔ Caddy (TLS: Cloudflare edge, then Cloudflare's origin
certificate); Caddy ↔ API (private network); API/worker ↔ PostgreSQL (three roles; forced RLS) and Redis;
API/worker ↔ object storage and SMTP (credentials from the server's env files); CI ↔ GHCR ↔ server (signed
in with tokens; the server pulls); operator laptop ↔ server (SSH key).

## 1. OWASP Top 10 (2021)

| | Risk for ScoreCode | Controls | Evidence |
|---|---|---|---|
| **A01 Broken access control** | A student reads another student's result; a faculty member acts as an administrator; one school reads another's data; an IDOR on student, result, file or tenant ids | Tenant from the verified host and session only, never a client field; PostgreSQL RLS forced and fail-closed on all 47 tenant tables; composite foreign keys; per-route permissions; student APIs take identity from the session; files only through short signed links issued after a permission check | `test_isolation.py` (every route with another tenant's ids), `test_authz_matrix.py` (every route × every role), `test_publishing.py` / `test_marksheets.py` (own result only), RLS coverage test |
| **A02 Cryptographic failures** | Passwords or two-step secrets readable; traffic intercepted | Argon2id; TOTP secrets encrypted with a key derived from `SCORECODE_SECRET_KEY`; HTTPS only (HSTS, `__Host-` Secure cookies; production refuses to start otherwise); backups age-encrypted to a public key whose private half never touches the server | `test_mfa.py`, `test_core.py` (production config refuses insecure settings), restore drill (P16.4) |
| **A03 Injection** | SQL injection; XSS through names or file contents; template injection in marksheets | SQLAlchemy bound parameters everywhere (literal SQL only for constant queries); React escaping; CSP without `unsafe-eval`; sandboxed Jinja with autoescape for PDFs and the verify page; text a spreadsheet would run as a formula is quote-prefixed in import error reports and data exports | semgrep (OWASP + Python rules) and bandit in CI; `test_data_in_the_snapshot_is_printed_never_interpreted`; ZAP baseline |
| **A04 Insecure design** | Results visible before publication; corrections silently changing what students saw; "unpublish" losing history | Exam state machine as data (every status × action tested); immutable published snapshots, versioned publications, superseded marksheets verify as such; corrections keep the live version until replaced and notify only students whose result changed | `test_exam_states.py` (160 cases), `test_corrections.py`, `test_snapshots_cannot_be_changed_by_anyone` |
| **A05 Security misconfiguration** | Debug docs exposed; default secrets; permissive headers; containers as root | Production refuses development secrets, `expose_docs`, insecure cookies; CSP, COOP/CORP/COEP, `nosniff`, referrer policy at the edge; containers read-only, no capabilities, no new privileges, non-root (except PostgreSQL's own entrypoint and Caddy binding 443); the server's firewall rules are written by `bootstrap.sh` | `edge.spec.ts`, ZAP baseline, release rehearsal "Hardening as deployed" |
| **A06 Vulnerable components** | A known-vulnerable library or base image | pip-audit, pnpm audit, Trivy on every image, Dependabot-style updates by hand | CI security job; results in §4 |
| **A07 Identification and authentication failures** | Credential stuffing on result day; phished administrator; reset or invitation links reused | Per-address failure buckets and per-account lockout; breached-password check; two-step sign-in for staff, re-authentication for sensitive actions; reset and invite tokens hashed, single use, short-lived; security notices by email when a password or two-step setting changes | `test_auth.py`, `test_mfa.py`, `test_admin_flows.py`, `test_breached_passwords.py` |
| **A08 Software and data integrity failures** | A tampered image deployed; a marksheet forged | Images built and scanned in CI, pulled by version from GHCR; the server runs only what a release's bundle image contains (the deploy user can't supply scripts); marksheets carry a verification code and the PDF's SHA-256 is what verification checks | release rehearsal; `scorecode-deploy`; `test_marksheets.py` |
| **A09 Logging and monitoring failures** | An attack nobody notices; personal data in logs or error reports | Append-only audit log in the same transaction as each change; structured logs with redaction; Prometheus alerts (API down, 5xx, slow reads, pool exhaustion, stale backups, queue backlog); Sentry with a scrubber that removes people and secrets | `test_audit.py`, `alerts.test.yml` (promtool), `test_sentry_scrub.py` (what leaves the process) |
| **A10 SSRF** | A logo URL or template fetching internal addresses; a webhook to the metadata service | No user-supplied URLs are fetched; WeasyPrint's fetcher serves `data:` only; logos are uploaded bytes, sniffed | `test_rendering_never_fetches_external_urls` (live listener + control) |

## 2. The mission's named threats

| Threat | Control | Evidence | Left over |
|---|---|---|---|
| **Authentication** | as A07 | as A07 | Two-step is offered and nudged, not yet required per school; passkeys are V1 |
| **CSRF** | Double-submit token (`__Host-` cookie + header) on every unsafe method; SameSite cookies; JSON-only APIs | `test_auth.py` and `test_security_hardening.py` CSRF tests | — |
| **XSS** | as A03; CSP | ZAP baseline; `edge.spec.ts` | `style-src 'unsafe-inline'` on the SPAs (accepted risk R-CSP: two libraries insert `<style>`) |
| **SQL injection** | as A03 | semgrep, bandit | — |
| **SSRF** | as A10 | as A10 | — |
| **Uploads** | Magic-byte sniffing; size, row, column and uncompressed-size caps; XLSX parsed without formulas or external links; per-plan storage quota; stored privately, served through signed links; import files deleted 30 days after the import ends | `test_import_engine.py`, `test_imports.py`, `test_retention.py` | — |
| **Reset and invitation abuse** | Neutral responses (no account enumeration); tokens hashed, single use, expiring; per-address limits; the link goes only to the address on file | `test_auth.py`, `test_admin_flows.py` | Email deliverability is the provider's (bounces aren't processed yet) |
| **Brute force** | as A07; result lookup needs a per-student activation code then a password (roll numbers are not secrets); activation limited per address and per enrollment number | `test_activation.py`, `test_auth.py` | — |
| **Bulk enumeration of results** | No public lookup by roll number; students see only their own results; the verify page needs a 128-bit code and shows a masked name by default | `test_publishing.py`, `test_marksheets.py` | — |
| **Supply chain** | Locked dependencies (uv.lock, pnpm-lock); audits and Trivy in CI; images pinned by version; GitHub Actions from known publishers | CI | Actions are pinned by tag, not by commit SHA (a compromised action tag would run in CI, not on the server) |
| **Backup theft** | Dumps encrypted with age to a public key; the private key is held by the owner offline; the backup bucket is another provider with its own keys | restore drill (P16.4) | The files bucket's copy in the backup bucket is protected by that bucket's privacy and server-side encryption, not by age (PDFs can't be re-encrypted incrementally) |
| **Secrets in logs, images and repositories** | Settings only from the environment; `SecretStr` never printed; structured-log redaction; secrets reach the server over SSH stdin, never a command line; `leak-scan.py` checks history for the real values; gitleaks in CI and pre-commit | `test_core.py` redaction, `leak-scan.py` run (2026-10-10: no secret value found) | — |
| **Insider misuse** | Every change audited with actor, reason and before/after; the app role cannot UPDATE or DELETE snapshots, approvals or the audit log; maker–checker on plans that include it; data export owner-only, re-authenticated and audited; ScoreCode staff act through the platform console (audited separately) | `test_audit.py`, `test_kernel.py` append-only tests, `test_exports.py` | A database superuser (the operator) can still do anything: mitigated by keeping that role off the network and the server's SSH to one key |

## 3. Since the last review

| Feature | New risk | Control | Evidence |
|---|---|---|---|
| Corrections after publication (P18.3) | Changing published results without a trace; telling everyone about one student's fix | Reason + re-auth to start; the live version stays; new version supersedes; only changed students notified; audit records the version replaced and the count changed | `test_corrections.py`, `corrections.spec.ts` |
| Data export (P18.5) | Exfiltration of every student's data | Owner only, re-auth, five a day, explicit column lists (no hashes, tokens or IPs), private object, five-minute links, each audited, deleted after seven days | `test_exports.py` |
| Hindi and Punjabi (P18.4) | Text injection through translations | Catalogues are code (reviewed); the marksheet escapes both languages | `test_marksheet_labels.py` |
| Sentry (P18.6) | Personal data shipped to a third party | Errors only; no user, locals, source lines, bodies, cookies, query strings; scrubber; failure drops the event | `test_sentry_scrub.py` |
| The server (P18.8) | A stolen CI key becoming root | The deploy user isn't in the docker group; it may run two root-owned wrappers that take scripts from the release image; inputs validated | release rehearsal (sudo limits, refused bad arguments) |

## 4. Scans (ran, passed, found)

Latest complete run of every scanner: CI run 38015210466 (commit 6c44380, 2026-10-10).

| Scanner | Scope | Result |
|---|---|---|
| gitleaks 8.24.3 | the pushed commits | no leaks |
| `leak-scan.py` (real values) | every blob in history + working tree | no secret value found (the files bucket's name equals the template example; the admin password value is guessable and must be changed — owner action) |
| pip-audit `--strict` | backend runtime dependencies | no known vulnerabilities |
| bandit `-ll` | backend/app | no medium or high findings |
| semgrep (p/owasp-top-ten, p/python, severity ERROR) | backend/app, infra/ops | 0 findings (66 rules, 186 files) |
| pnpm audit `--audit-level high` | frontend | 0 vulnerabilities |
| Trivy (critical, fixable) | backend image (Debian 12.15) and, on releases, proxy, postgres, backup | 0 |
| shellcheck `-S error` | operations scripts | clean |
| ZAP baseline | the CI stack | no High alerts ([dispositions](zap-baseline-2026-10-08.md)) |

**Not run yet:** DAST against the deployed server (blocked until it is reachable); an external penetration
test (recommended before the first paying school's result day).

## 5. Residual risks (owner to accept or fund)

1. **One server** is a single point of failure: an outage of the VM is an outage of ScoreCode (backups
   restore in about a minute on a new one; RTO measured 57 s for the database, plus provisioning).
2. **Shared CPU** at the host: noisy neighbours can slow result day; measured on the target before go-live
   (P18.11).
3. **R-CSP**: inline styles allowed on the SPAs.
4. **Names in free text**: the Sentry scrubber can't recognise a person's name inside an arbitrary error
   message; ScoreCode's own messages don't include names.
5. **Two-step not mandatory** for school administrators.
6. **Translations** not yet reviewed by native speakers.
7. **Legal**: the documents in docs/legal are drafts for a lawyer's review; nothing here is a compliance
   claim.
