# 06 · Multi-Tenant Architecture

> Covers brief section **H**, §4 (multi-tenancy), §5 (Thapar is one tenant), §26 (tenant-aware routing).
> Related: [07 Database](07-database-design.md) · [10 Security](10-security-architecture.md) · [sequence: tenant resolution](diagrams/sequence-diagrams.md#1-tenant-resolution-and-authenticated-request)

**Invariant (I-1):** *A request authenticated for tenant A can never read or modify tenant B's data — not through a URL, an ID, a cache key, a file key, a background job, a report, or a bug in one layer.*

The design achieves I-1 with **five independent layers**, so a single mistake in one layer is caught by another.

---

## 1. Tenancy model: choosing the isolation level

| Option | How it works | Pros | Cons | Verdict |
|---|---|---|---|---|
| **Database per tenant** | Each institution gets its own database | Strongest isolation; easy per-tenant backup/restore; noisy-neighbour-proof | Migrations × N; connection pools × N; cost per tenant kills a free tier; cross-tenant platform metrics are hard | ❌ for V1. ✅ for **Enterprise dedicated** deployments (same code, separate stack). |
| **Schema per tenant** | One DB, `tenant_abc.students`, … | Good isolation; per-tenant restore possible | Migrations × N schemas; catalog bloat beyond a few thousand schemas; pooling + `search_path` tricks are error-prone | ❌ — most of the cost of DB-per-tenant with fewer benefits |
| **Shared schema, `tenant_id` column** | All tenants in the same tables | One migration; cheap; simple pooling; easy platform analytics; free tier economical | Isolation depends on *every* query being correct → must be enforced by the DB, not just discipline | ✅ **Chosen**, hardened with RLS and composite FKs |

**Hybrid path:** shared-schema for Free → Pro. Enterprise customers needing physical isolation get a **silo deployment** (separate DB + app stack, same images, same migrations). The code never branches on "is this a silo"; it's just a deployment with one tenant.

---

## 2. Application-level isolation vs PostgreSQL Row-Level Security

| | Application-level only | RLS only | **Both (chosen)** |
|---|---|---|---|
| Mechanism | Every query adds `WHERE tenant_id = :ctx` (repository base class) | DB policies filter rows using a session variable | Repository adds filter **and** DB enforces policy |
| Protects against forgotten filter | ❌ | ✅ | ✅ |
| Protects against raw SQL / report queries | ❌ | ✅ | ✅ |
| Performance | Best (planner sees literal predicate) | Small overhead; planner may not use index well if policy is complex | Same as app-level — the explicit predicate keeps plans good; RLS adds a cheap check |
| Pitfalls | Human error | Superuser/owner bypass; connection-pool variable leakage; harder debugging | Must handle the pitfalls below |

### RLS implementation rules (all mandatory)
1. **Every tenant-owned table** has `tenant_id uuid NOT NULL` and:
   ```sql
   ALTER TABLE students ENABLE ROW LEVEL SECURITY;
   ALTER TABLE students FORCE ROW LEVEL SECURITY;   -- applies even to table owner
   CREATE POLICY tenant_isolation ON students
     USING      (tenant_id = current_setting('app.tenant_id')::uuid)
     WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
   ```
   `current_setting('app.tenant_id')` **without** the `missing_ok` flag raises an error if unset → a query that forgot to set tenant context *fails closed* instead of returning everything.
2. The application connects as role **`scorecode_app`**: not superuser, not table owner, `NOBYPASSRLS`. Migrations run as a separate owner role `scorecode_migrator`.
3. Tenant context is set **per transaction** with `SELECT set_config('app.tenant_id', :tid, true)` (`true` = `SET LOCAL` semantics). This is compatible with PgBouncer **transaction pooling** — the setting dies with the transaction, so it cannot leak to the next client of that connection. It is issued as the first statement of every transaction of a unit of work bound to a tenant (`app/core/db.py`, `_bind_tenant`), so the transaction, and the connection, are only taken when a statement actually runs.
4. Platform-admin cross-tenant reads use a **separate role** `scorecode_platform` (`BYPASSRLS`, read-mostly grants), a **separate connection pool**, available only inside the `platform` module, and every use is audited.
5. A **migration test** in CI asserts: every table with a `tenant_id` column has RLS enabled + forced + a policy. A new table cannot ship without isolation.

---

## 3. The five isolation layers

```
 Request ─► [L1 Tenant resolution from Host] ─► [L2 Session must belong to that tenant]
        ─► [L3 Repository: tenant-scoped queries + ownership checks]
        ─► [L4 PostgreSQL: RLS + composite foreign keys]
        ─► [L5 Side channels: cache keys, object keys, jobs, logs all carry tenant_id]
```

### L1 — Tenant resolution (edge of the app)
- Middleware reads the `Host` header (proxy is configured to pass the original host and reject unknown hosts):
  - `<slug>.scorecode.in` → look up tenant by slug.
  - Custom domain `results.abcschool.edu.in` → look up in `tenant_domains` (verified only).
  - `admin.scorecode.in` → platform realm (no tenant).
  - `verify.scorecode.in` → verification realm (tenant derived from the code, not the host).
  - `scorecode.in` / `www` → marketing & sign-up.
- Host→tenant mapping cached (in-process LRU 60 s + Redis) — it changes rarely.
- Unknown host → 404 page; suspended tenant → 403 "temporarily unavailable" page.
- Result: an immutable `TenantContext(tenant_id, slug, plan_snapshot, status)` attached to the request.

### L2 — Authentication is tenant-bound
- **Users belong to exactly one tenant** (`users.tenant_id NOT NULL`). The same email at two institutions = two separate accounts. This removes an entire class of "which tenant am I acting in?" bugs. Trade-off: a teacher working at two institutions has two logins — acceptable for this market.
- Session rows store `tenant_id`; cookies are host-only (no `Domain=` attribute) so a session cookie for `abc.scorecode.in` is **never sent** to `xyz.scorecode.in`.
- On every request: `session.tenant_id == request.tenant_context.tenant_id`, otherwise 401. Defends against stolen cookies replayed on another host.
- Platform admins live in a separate `platform_users` table and authenticate only on `admin.scorecode.in`, with mandatory TOTP 2FA.

### L3 — Application layer
- All data access goes through repositories derived from `TenantScopedRepository`, which **requires** a `TenantContext` in its constructor and adds `tenant_id = :ctx` to every statement. There is no way to construct one without context.
- Object lookups always use `(tenant_id, id)`; a missing row and a row owned by another tenant both return **404** (never 403 — do not confirm existence).
- **Ownership checks** within a tenant: faculty can only access papers they're assigned; students have **no ID parameters at all** on their API (`/me/...`).
- IDs are UUIDv7 (non-sequential) — not a security control on its own, but stops trivial enumeration and leaks of volume ("student 4,812").

### L4 — Database
- RLS as above (fails closed).
- **Composite foreign keys** make cross-tenant references impossible at the schema level:
  ```sql
  -- every tenant table:
  UNIQUE (tenant_id, id)
  -- every reference:
  FOREIGN KEY (tenant_id, student_id) REFERENCES students (tenant_id, id)
  ```
  Even a buggy service that tries to attach tenant A's mark entry to tenant B's student gets a constraint violation.
- Unique constraints are per tenant: `UNIQUE (tenant_id, enrollment_no)`, `UNIQUE (tenant_id, code)` for courses, etc.

### L5 — Side channels
| Channel | Rule |
|---|---|
| Redis keys | `t:{tenant_id}:...` built only by a helper that requires `TenantContext` |
| Object storage | `tenants/{tenant_id}/{kind}/{uuid}` — never user-supplied filenames in keys; downloads only via short-lived signed URLs issued after an authorization check |
| Background jobs | Payload always includes `tenant_id`; worker sets tenant context (incl. RLS variable) before touching data; jobs never accept a tenant from user input |
| Logs/metrics | `tenant_id` label on logs; no PII (names, marks) in logs |
| Exports/reports | Generated inside tenant context; files stored under tenant prefix |
| Search (future) | Tenant filter mandatory in index queries |
| Emails | Templates rendered with tenant context; links use tenant host |

### Verification against I-1
- Automated **tenant-isolation test suite** (see [15 Testing](15-testing-strategy.md)): for every endpoint, authenticated as a user of tenant A, attempt to access/modify resources of tenant B by ID, by host swap, and by cookie replay → must return 404/401 and leave B's data unchanged.
- DB-level test: with `app.tenant_id` set to A, `SELECT count(*) FROM <every tenant table> WHERE tenant_id = B` returns 0; inserting a row with B's id fails.

---

## 4. Tenant-aware routing

### Options compared

| | Path-based `scorecode.in/abcschool` | **Subdomain `abcschool.scorecode.in`** | Custom domain `results.abcschool.edu.in` |
|---|---|---|---|
| Cookie isolation between tenants | ❌ Same origin → cookies shared unless carefully path-scoped (fragile); XSS on one tenant's custom content could affect others | ✅ Separate origins with host-only cookies | ✅ Fully separate origin |
| Branding perception | Weak ("someone else's site") | Good | Best |
| TLS | One cert | One wildcard cert `*.scorecode.in` (DNS-01 challenge) | Per-domain cert — automated via on-demand ACME (Caddy) or a CDN's "SaaS custom hostnames" product |
| DNS work for tenant | None | None (wildcard record) | Tenant adds a CNAME; we verify ownership |
| Local development | Easiest | Easy with `*.localhost` (browsers resolve it to 127.0.0.1) or `lvh.me` | Hosts-file entries |
| Frontend routing complexity | Every route prefixed with slug | None — tenant implicit | None |
| SEO/marketing site separation | Mixed | Clean | Clean |

### Decision
**Host-based tenancy everywhere — including development and the demo.** Do *not* use path-based routing for dev/demo and subdomains for production: two resolution mechanisms means two code paths, and the dev environment would no longer test the production isolation model (cookies, origins, CORS).

| Environment | Hosts |
|---|---|
| Local dev | `thapar.localhost:8080`, `demoschool.localhost:8080`, `admin.localhost:8080`, `verify.localhost:8080` |
| Demo | `thapar.<demo-domain>`, `demoschool.<demo-domain>` with wildcard DNS + wildcard cert (e.g. on a cheap `.in`/`.app` domain) |
| Production | `<slug>.scorecode.in` (Free–Growth), custom domain (Pro+) |

### Custom domain flow (V1, Pro)
1. Tenant admin enters `results.abcschool.edu.in` → system creates `tenant_domains` row (status `pending`) with a verification token.
2. Tenant adds `CNAME results.abcschool.edu.in → custom.scorecode.in` and a `TXT _scorecode-verify.results... = <token>`.
3. Verification job confirms both → status `verified`.
4. Caddy's `on_demand_tls` calls our internal `ask` endpoint before issuing a certificate; it allows only `verified` domains (prevents attackers from making us request certs for arbitrary hosts).
5. Subdomain continues to work and redirects to the custom domain (configurable).

Alternative at scale: a CDN "custom hostnames for SaaS" product handles certs at the edge; evaluate when custom-domain count grows.

---

## 5. Per-tenant configuration and data-driven customisation

All tenant variation is **data**, read through the tenant context:

| Concern | Stored in | Read by |
|---|---|---|
| Plan & entitlements | `tenant_subscriptions`, `plan_features`, `tenant_feature_overrides` | `EntitlementService` ([12](12-entitlements.md)) |
| Branding | `tenant_branding` | `GET /api/v1/tenant/config` → CSS variables in frontend |
| Grading | `grading_schemes` (versioned) | `GradingStrategy` registry |
| Marksheet layout | `marksheet_templates` (template id + tenant parameters) | PDF renderer |
| Notification templates | `notification_templates` (tenant override of defaults) | Notification service |
| Settings (timezone, locale, approval mode, activation mode, verification disclosure) | `tenant_settings` (typed columns, not a free-form bag) | Services |

**No code path checks for a specific tenant** (`if tenant.slug == "thapar"` is forbidden; a lint/grep check in CI flags tenant slugs in code).

---

## 6. Noisy-neighbour controls
- Per-tenant rate limits on expensive endpoints (imports, exports, processing) and per-tenant job concurrency caps in the worker (one tenant's 50,000-row import cannot starve others).
- Per-tenant storage accounting (entitlement `max_storage_mb`).
- Query timeouts (`statement_timeout`) for the app role.

---

## 7. Thapar as a tenant (§5)

Thapar is created through **the same sign-up/provisioning path as any customer** (scripted via the platform admin seed command, not hand-written SQL), on an Enterprise-like plan to show off features (SGPA/CGPA grading, two-step approval, custom branding). A second and third tenant (a demo school on Free, a demo coaching institute on Growth) are seeded alongside, so the presentation can show:
1. Three different branded portals on three hosts.
2. Logging into Thapar and trying to fetch Demo School's result by ID → 404 (live isolation demo).
3. The platform admin console showing all three tenants with different plans and usage.
