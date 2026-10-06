# ADR 0006 — Student activation codes

**Decision.** Students activate with enrollment number + a 10-character Crockford code (≈50 bits) printed on a slip or sent by email, then set their own password. Codes are stored as SHA-256 of `(tenant, enrollment, code)`, single-use, expiring, and rate-limited per enrollment and per IP. Date-of-birth passwords are not supported.
