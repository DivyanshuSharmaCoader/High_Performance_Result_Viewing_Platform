# ADR 0003 — Users belong to exactly one tenant

**Decision.** `users.tenant_id NOT NULL`; the same email at two institutions is two accounts. Platform staff live in a separate `platform_users` table and realm.

**Consequences.** No "which tenant am I acting in?" logic anywhere; sessions are trivially tenant-bound. A teacher at two institutions has two logins (acceptable for the target market).
