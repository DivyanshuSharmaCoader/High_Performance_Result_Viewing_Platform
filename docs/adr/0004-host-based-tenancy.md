# ADR 0004 — Host-based tenancy everywhere

**Decision.** The tenant is derived only from the `Host` header: `<slug>.<base>` (or a verified custom domain) → tenant; `admin.<base>` → platform; `verify.<base>` → verification; `<base>`/`www` → marketing. Development uses `*.localhost`, so dev exercises the production isolation model (separate origins, host-only cookies). The base domain is configuration (`SCORECODE_BASE_DOMAIN`); no domain is hard-coded.

**Consequences.** One frontend build serves all tenants; caches/localStorage never mix because each tenant is its own origin.
