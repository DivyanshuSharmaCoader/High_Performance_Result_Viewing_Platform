# ADR 0002 — Shared schema with forced, fail-closed Row-Level Security

**Context.** Shared-schema tenancy is cheap and simple to operate but one forgotten `WHERE tenant_id = …` would leak data across institutions.

**Decision.**
1. Every tenant-owned table has `tenant_id NOT NULL`, `UNIQUE (tenant_id, id)` and composite foreign keys `(tenant_id, x_id) → parent (tenant_id, id)`.
2. `ENABLE` + `FORCE ROW LEVEL SECURITY` with policy `tenant_id = current_setting('app.tenant_id')::uuid` — **without** `missing_ok`, so a query with no tenant context raises instead of returning rows.
3. The runtime role `scorecode_app` is `NOBYPASSRLS`, owns nothing and gets explicit per-table grants; the schema is owned by `scorecode_migrator`; the platform console uses `scorecode_platform` (`BYPASSRLS`) through a separate pool.
4. Tenant context is set per transaction with `set_config('app.tenant_id', …, true)` (PgBouncer-safe).
5. Independently, the ORM adds `tenant_id = :ctx` to every statement on `TenantScoped` models (`app/core/db.py`).
6. Reads that must happen before a tenant context exists (host → tenant, job claiming, public verification) go through narrow `SECURITY DEFINER` functions.

**Verification.** `tests/integration/test_kernel.py` asserts every table with `tenant_id` has forced RLS + a `tenant_isolation` policy, that queries without context fail, that cross-tenant inserts fail (RLS and composite FK), and that the app role cannot run DDL or modify append-only tables. `tests/integration/test_isolation.py` exercises every route with swapped IDs, swapped hosts and replayed cookies.

**Consequences.** Every new table needs `enable_tenant_rls()` in its migration or CI fails. Platform-wide reporting must use the platform role.
