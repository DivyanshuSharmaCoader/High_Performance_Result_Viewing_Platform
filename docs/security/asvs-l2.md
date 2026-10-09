# OWASP ASVS 4.0.3 Level 2 — ScoreCode checklist (P15.2)

Reviewed 2026-10-08 against the code at the commit that adds this file. Status:
- **Met:** implemented, with a test or CI check named in the Evidence column.
- **Partial:** implemented but missing a piece (the gap is described).
- **Gap:** not implemented, with a tracking note.
- **N/A:** doesn't apply to this system.

Only the requirements relevant to a server-rendered, SPA-plus-JSON-API, multi-tenant SaaS are listed. The
whole standard has around 280 items; the left-out ones are chiefly mobile, desktop and native-crypto ones.
Gaps are listed with their next step, not hidden.

## V1 Architecture
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 1.1.2 | Threat model for design changes | Met | docs/10 §1 and §1.1 (as-built review) |
| 1.2.1 | Least-privilege service accounts | Met | Three database roles: runtime `NOBYPASSRLS`, platform, migrator. `test_each_role_connects_and_app_role_cannot_ddl` |
| 1.4.1 | Access control enforced server-side at a trusted point | Met | `require()` on every route; `test_every_route_declares_an_access_policy` |
| 1.4.4 | Single, vetted access-control mechanism | Met | Permissions map plus RLS. `test_authz_matrix.py` covers every route × role |
| 1.5.3 | Input validation enforced server-side | Met | Pydantic schemas with `extra="forbid"`; `test_mass_assignment_is_rejected` |
| 1.8.1 | Sensitive data identified and classified | Met | docs/10 §1 assets; marks and PII never in emails or logs |
| 1.14.6 | No unsupported/insecure client tech | Met | React SPA, no plugins; CSP `script-src 'self'` |

## V2 Authentication
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 2.1.1 | Passwords ≥ 12 characters | Met | 12 for staff and owners. **Students: 10.** A deliberate exception for school students, compensated by rate limits and the breach check; documented here |
| 2.1.2 | Passwords up to 64+ characters allowed | Met | Up to 256 |
| 2.1.4 | Any printable Unicode allowed | Met | No composition rules |
| 2.1.7 | Checked against breached passwords | Met | `app/core/breached.py` (HIBP k-anonymity; fails open); `test_breached_passwords.py` |
| 2.1.9 | No composition rules | Met | NIST-style rules only |
| 2.1.12 | Masked password with a reveal option | Met | `PasswordInput` |
| 2.2.1 | Anti-automation (rate limits, lockout) | Met | Per real client address, per account, progressive lockout. `test_auth.py`; client-address tests |
| 2.2.3 | Notify users of security events | Partial | Since 2026-10-09 a security notice is emailed for: a password changed or reset; two-step turned on or off; two-step reset by an administrator, naming who; new recovery codes; a recovery code used to sign in, with how many are left. It is sent in the change's own transaction, can't be turned off, and links to the account page (`identity/security_notices.py`; `test_mfa.py`, `test_admin_flows.py`, `test_auth.py`; the missing-notice mutant is caught). **Gap:** sign-in from a new device or location |
| 2.3.1 | Initial or recovery secrets random and short-lived | Met | Invitations, resets and activation use random tokens with expiry, hashed at rest |
| 2.4.1 | Passwords stored with an approved, salted, slow hash | Met | Argon2id t=2, m=19 MiB, p=1 (OWASP baseline); rehashed on parameter change |
| 2.5.1 | Recovery doesn't reveal the current password | Met | Emailed one-time link |
| 2.5.2 | No security questions | Met | None |
| 2.5.4 | No shared or default accounts | Met | Demo tenants are seeded with per-tenant users; production config refuses development secrets |
| 2.5.6 | Forgotten-password flow is secure | Met | Rate-limited; identical response whether or not the account exists; `test_password_reset_by_email_revokes_sessions` |
| 2.7.x | Out-of-band verifiers | N/A | No SMS or email codes used as an authentication factor |
| 2.8.1 | Time-based one-time passwords have a defined lifetime | Met | 30 s steps, ±1 step for drift |
| 2.8.4 | A TOTP can be used only once | Met | Last step stored; `test_mfa.py` replay check (caught under mutation) |
| 2.8.7 | Recovery mechanism for a lost second factor | Met | One-time recovery codes (hashed); an administrator can reset another staff member (audited; never the owner) |
| 2.9.x | Cryptographic verifiers (hardware keys) | Gap | WebAuthn and passkeys are not built; planned for V1 |

## V3 Session management
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 3.1.1 | Session tokens never in URLs | Met | HttpOnly cookie only |
| 3.2.1 | New token on authentication | Met | A new session on every sign-in |
| 3.2.2 | Tokens have ≥ 64 bits of entropy | Met | 256-bit random, stored hashed |
| 3.3.1 | Logout invalidates the session server-side | Met | `test_expired_and_revoked_sessions_are_rejected` |
| 3.3.2 | Idle and absolute timeouts | Met | Staff: 12 h idle, 7 days absolute. Students: 30-day sliding (documented trade-off for result day) |
| 3.3.3 | Option to end all other sessions | Met | "Sign out everywhere"; the session list on the account page |
| 3.3.4 | Users can see and end active sessions | Met | `/me/sessions` and logout-all |
| 3.4.1–3.4.5 | Cookie flags: Secure, HttpOnly, SameSite, `__Host-` prefix, path | Met | `__Host-` cookies when `cookie_secure`; production refuses `false` |
| 3.5.x | Token-based sessions (JWT) | N/A | Opaque server-side sessions |
| 3.7.1 | Re-authentication before sensitive operations | Met | `require_recent_auth` on publish, withdraw, role changes, ownership transfer, revocation and two-step resets; asks for both factors when two-step is on |

## V4 Access control
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 4.1.1 | Enforced on a trusted service layer | Met | Routes plus services; RLS beneath |
| 4.1.2 | Access attributes can't be manipulated by users | Met | Tenant from the host, identity from the session; tenant ids in input are ignored (isolation suite) |
| 4.1.3 | Least privilege | Met | Role map snapshot test (`permission_matrix.json`) |
| 4.1.5 | Fails securely | Met | RLS fails closed when no tenant context; `test_query_without_tenant_context_fails_closed` |
| 4.2.1 | Protection against IDOR | Met | `test_isolation.py` over every route; student routes keyed by session |
| 4.2.2 | CSRF protection | Met | Double-submit token on unsafe methods; `test_unsafe_request_without_csrf_token_is_rejected` |
| 4.3.1 | Administrative interfaces use extra protection | Met | Platform console on its own host with mandatory TOTP; tenant admins can use two-step |
| 4.3.2 | No directory browsing or metadata leakage | Met | Static hosting via Caddy without listings; production refuses `expose_docs` |

## V5 Validation, sanitisation, encoding
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 5.1.1 | Protection against HTTP parameter pollution | Met | Typed single-value parameters |
| 5.1.3 | All input validated with allow-lists | Met | Pydantic types, enums and lengths |
| 5.1.5 | Redirects only to allow-listed destinations | Met | `safeNext()` (open-redirect test in `auth.test.tsx`) |
| 5.2.1 | Untrusted HTML sanitised | Met | No user HTML is accepted; React escapes output |
| 5.2.6 | SSRF protection | Met | PDF renderer fetches only `data:`; no user-supplied URLs are fetched anywhere |
| 5.2.8 | Template injection prevented | Met | Jinja `SandboxedEnvironment`, StrictUndefined; templates aren't user-editable |
| 5.3.1 | Output encoding for the context | Met | React plus Jinja autoescape; verify-page XSS test |
| 5.3.4 | Parameterised queries | Met | SQLAlchemy throughout; arrays bound as parameters (`app/core/sql.py`) |
| 5.5.2 | Untrusted XML and XXE safe | Met | openpyxl parses through **defusedxml**, now a declared runtime dependency; `test_spreadsheets_are_parsed_with_defused_xml`; macros refused. *Found in this review:* defusedxml had arrived only through a dev tool, so the production image (`--no-dev`) parsed XLSX with the standard-library parser |

## V7 Errors and logging
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 7.1.1 | No credentials or session tokens in logs | Met | Redaction processor; `test_scrubber_removes_secrets_and_pii` |
| 7.1.3 | Security events logged | Met | Audit: sign-ins, lockouts, role changes, two-step events, recovery-code use, revocation |
| 7.2.1 | Authentication decisions logged | Met | `auth.login`, `user.login_locked`, `scorecode_logins_total` by outcome |
| 7.3.1 | Log injection prevented | Met | Structured JSON logging |
| 7.4.1 | Generic error messages | Met | problem+json with request id and no internals; database outages answer a retryable 503 (`test_outages.py`) |

## V8 Data protection
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 8.1.1 | Sensitive data not cached by intermediaries | Met | `private, no-store` on personal APIs; `no-store` default under `/api/` |
| 8.2.2 | No sensitive data in browser storage | Met | Only UI preferences in local storage; session in an HttpOnly cookie |
| 8.3.1 | Sensitive data in the body or headers, not the URL | Met | Verification codes are designed to be public; `Referrer-Policy: no-referrer` on the verify page |
| 8.3.4 | Sensitive data identified with a retention policy | Met | A retention table (docs/10 §12) applied by `ops_purge()` every 6 h, per tenant under RLS; `test_retention.py` (the window mutant is caught) |

## V9 Communications
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 9.1.1 | TLS for all connections | Partial | Configured at the edge (Phase 16); production refuses `public_scheme` other than https; HSTS sent when `cookie_secure`. **Not verified** until deployment |
| 9.2.x | Server-to-server TLS | Partial | `sslmode=verify-full` documented for managed databases; to verify in Phase 16 |

## V10 Malicious code
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 10.3.2 | Dependencies from trusted sources, scanned | Met | Lock files; `pip-audit`, `pnpm audit --audit-level high`, Trivy and gitleaks in CI |

## V11 Business logic
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 11.1.1 | Steps processed in order | Met | Exam state machine; `test_exam_states.py` |
| 11.1.2 | Rate limits on business functions | Met | Sign-up, trial, activation, verify lookups, imports |
| 11.1.4 | Anti-automation on high-value functions | Met | Trial anti-abuse signals; publication limits per plan |
| 11.1.5 | Business-logic limits and alerts | Met | Plan caps enforced transactionally (`test_entitlements.py`) |

## V12 Files and resources
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 12.1.1 | Large files refused | Met | `SCORECODE_MAX_UPLOAD_BYTES`; row, column and uncompressed caps |
| 12.1.2 | Compressed files checked against bombs | Met | XLSX uncompressed-size cap; `test_import_engine.py` |
| 12.2.1 | File type checked by content | Met | Magic-byte `sniff()`; markup refused |
| 12.3.1 | User filenames never used on the filesystem | Met | Object keys are `tenants/<id>/<kind>/<uuid7>`; download names sanitised |
| 12.4.1 | Files stored outside the web root, served safely | Met | Private bucket; signed URLs (120 s for marksheets) with `Content-Disposition: attachment` |
| 12.5.1 | Web tier serves only allowed file types | Met | Caddy serves SPA builds only |
| 12.6.1 | No requests to user-supplied URLs | Met | None exist; PDF fetcher refuses all but `data:` |

## V13 API
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 13.1.1 | Same encoding and parsers everywhere | Met | JSON only; problem+json errors |
| 13.1.3 | API URLs don't expose sensitive information | Met | No tokens in paths, except verification codes, which are public by design |
| 13.2.1 | Only allowed HTTP methods | Met | 405 for others |
| 13.2.3 | CSRF protection on cookie-authenticated APIs | Met | See 4.2.2 |
| 13.2.5 | Content type checked | Met | FastAPI JSON validation; multipart only on upload routes |

## V14 Configuration
| # | Requirement | Status | Evidence / note |
|---|---|---|---|
| 14.1.1 | Repeatable, automated builds | Met | Docker multi-stage images; CI |
| 14.2.1 | Dependencies up to date, no known vulnerabilities | Met | CI audits fail on high/critical |
| 14.3.2 | No debug modes in production | Met | Production refuses development secrets, insecure cookies, http and public API docs; `test_production_rejects_dev_secret_and_insecure_cookies` |
| 14.4.1 | Content-Type with charset on every response | Met | Starlette/Caddy |
| 14.4.3 | Content-Security-Policy | Met | SPA: `script-src 'self'`, `frame-ancestors 'none'`; `style-src 'unsafe-inline'` is accepted risk R-CSP (docs/10 §5). API: `default-src 'none'`. Verify page: no scripts, its stylesheet pinned by hash, no `'unsafe-inline'`. `e2e/edge.spec.ts` checks for no violations in Chromium |
| 14.4.4 | `X-Content-Type-Options: nosniff` | Met | `test_security_headers_present` |
| 14.4.5 | HSTS | Met | Sent when `cookie_secure`; preload once the domain is final (Phase 16) |
| 14.4.6 | Referrer-Policy | Met | `strict-origin-when-cross-origin`; `no-referrer` on the verify page. Until 2026-10-09 the edge overwrote the verify page's value; it is now a default only (`e2e/edge.spec.ts`) |
| 14.4.7 | Framing restricted | Met | `X-Frame-Options: DENY` plus `frame-ancestors 'none'` |
| 14.4.x | Cross-origin isolation (not an ASVS 4 requirement; ZAP 90004) | Met | COOP `same-origin` and CORP `same-origin` everywhere; COEP `credentialless` on the SPAs, `require-corp` on the verify page |
| 14.5.3 | CORS allow-list | Met | No CORS: every app is same-origin with its API |

## Gaps to close, by priority
1. **New-device sign-in notices (2.2.3)**: the other security notices are built (2026-10-09). This one needs a record of known devices per user.
2. ~~**Automated retention (8.3.4)**~~: done (`ops_purge()`, 2026-10-09). Remaining: uploaded import *files* in object storage are not yet purged with their staging rows.
3. **TLS verification (9.x)**: verified when deploying (Phase 16).
4. **WebAuthn and passkeys (2.9)**: V1 roadmap.
5. **Policy to require two-step for administrators**: tenant setting; today it's available and nudged.
