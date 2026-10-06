# ADR 0005 — Opaque sessions, host-only cookies, double-submit CSRF

**Decision.** 256-bit random session token in an HttpOnly, SameSite=Lax, host-only cookie (`__Host-sc_session` when `SCORECODE_COOKIE_SECURE=true`). The DB stores only SHA-256(token). Validation is cached ≤60 s in Redis and ≤10 s in-process; revocation deletes the cache entry. Unsafe API requests require `X-CSRF-Token` equal to the non-HttpOnly `sc_csrf` cookie. Lifetimes: students 30-day sliding; staff 12 h idle / 7 days absolute; platform 8 h with mandatory TOTP.

**Consequences.** Immediate revocation (logout everywhere, suspension) within the local-cache bound (≤10 s on other processes). Argon2id login cost is the main result-day hotspot — mitigated by long student sessions and a bounded hashing semaphore.
