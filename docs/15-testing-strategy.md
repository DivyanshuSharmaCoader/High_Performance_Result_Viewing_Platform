# 15 · Testing Strategy

> Covers brief section **O**, §31 (testing) and §32 (benchmarking). Test evidence for the SE project goes in `docs/reports/` (test reports) and `benchmarks/results/` (performance).

## 1. Test pyramid & tools

| Layer | Scope | Tools | Where it runs |
|---|---|---|---|
| Unit | Pure logic: grading strategies, state machines, validation rules, entitlement resolution, permission maps, verification code format, CSV injection escaping | pytest, Hypothesis (property-based), Vitest + RTL (frontend) | every PR, seconds |
| Integration | API + PostgreSQL + Redis + object store: repositories, RLS, transactions, jobs, imports end-to-end, cache behaviour | pytest + httpx `AsyncClient`, service containers / Testcontainers, factory_boy | every PR, minutes |
| Contract | OpenAPI schema stability; frontend types compile against schema; schema fuzzing | `openapi.json` diff, Schemathesis | every PR |
| End-to-end | Real browsers through major journeys | Playwright (+ axe-core) | every PR (smoke) / nightly (full) |
| Security | Tenant isolation, authz matrix, auth flows, upload attacks, headers, dependency & static scans, DAST | pytest suites, ZAP baseline, Bandit/semgrep, pip-audit, gitleaks, Trivy | PR + nightly |
| Load | Publication spike scenarios A–D | k6 | on demand + nightly small scenario |
| Failure/chaos | DB/Redis/worker/network failures, partial failures | docker compose kill/pause, Toxiproxy | per phase milestone |

---

## 2. Unit tests — what matters most
- **Grading** (highest bug cost): golden tables per scheme (incl. a Thapar-style credit/SGPA scheme, CBSE-style percentage bands, coaching marks-only), edge cases (absent, exempt, withheld, grace, rounding at band boundaries like 89.995), and properties: monotonicity, determinism, bounds, idempotent re-run.
- **State machines**: every legal transition allowed, every illegal one rejected (exam, paper submission, import job, publication).
- **Validation rules**: each rule code in [13 §4](13-result-ingestion.md#4-validation-rules) has positive and negative tests.
- **Entitlements**: resolution table tests.
- **Permissions**: role × permission matrix snapshot test (changes must be deliberate).

## 3. Integration tests
- Repository + RLS: queries without tenant context fail; with context see only own rows.
- Transactions: publish is atomic (inject failure mid-way → no partial snapshot).
- Imports: upload → validate → commit with real files; duplicate detection; concurrent commits.
- Jobs: retry/idempotency (run the same job twice → same state).
- Cache: Redis down → requests still succeed (degraded) ; versioned keys refresh after config change.
- Entitlement race: parallel imports competing for last seats.

## 4. Security tests (first-class suites, not afterthoughts)

### 4.1 Tenant isolation suite (must be 100% green to merge)
Generated from the route table so new endpoints are covered automatically:
```
for each route R with path params:
   as user(tenant A, role with permission for R):
       call R with IDs belonging to tenant B           → expect 404, B unchanged
   call R on host B with session cookie from host A   → expect 401
   call R with forged tenant_id in body/query          → ignored or 422; never acts on B
DB layer: for each tenant table T:
   with app.tenant_id = A: SELECT ... WHERE tenant_id = B → 0 rows; INSERT with tenant_id B → error
   without app.tenant_id: any query → error (fail closed)
Side channels: cache keys and object keys built in tests contain tenant id; signed URL for A's PDF cannot be produced by B's session.
```

### 4.2 Authorization matrix
For every route × role (owner, admin, faculty-assigned, faculty-unassigned, student, anonymous) → expected allow/deny table, checked automatically. Student-specific: student X can't read student Y's result in the same tenant.

### 4.3 Other security tests
Auth (lockout, timing-safe comparisons, session rotation, logout everywhere), CSRF enforcement, security headers present, mass-assignment rejected (`extra="forbid"`), upload attacks (zip bomb, oversize, wrong magic bytes, SVG with script, formula cells), CSV-injection-safe exports, verification enumeration rate limits, log scrubbing, secrets not in images.

## 5. Load & performance testing
Plan and validity rules in [11 §4](11-performance-architecture.md#4-benchmark-plan-scientifically-valid). Deliverable per run: `benchmarks/results/YYYY-MM-DD-<scenario>.md` with environment, dataset, script SHA, p50/p95/p99, RPS, error rates, resource graphs, bottleneck analysis, and the next action.

## 6. Failure testing
| Experiment | Method | Expected (pass criteria) |
|---|---|---|
| Database unavailable | `docker compose stop postgres` during load | API returns 503 problem responses quickly (no hanging), readiness fails, recovers automatically on restart, no data corruption |
| Redis unavailable | stop redis | student reads still succeed (higher latency OK), rate limiter degrades to local, alerts fire |
| Worker crash mid-import/processing/PDF | `kill -9` worker | job re-run by another worker, final state identical, no duplicate marks/notifications |
| Network latency/loss to DB | Toxiproxy latency 200 ms / 5% loss | timeouts respected, no pool exhaustion cascade |
| Invalid uploads | corpus of broken files | clear errors, nothing committed |
| Partial failure during publish | exception injected after N snapshots | transaction rolled back, publication not visible, retry succeeds |
| Email provider failure | mock returns 500 | retries with backoff, in-app notifications unaffected |
| Object store failure | stop minio | result view OK, download shows retry message |

## 7. E2E journeys (Playwright)
1. Sign-up → verify email → onboarding checklist.
2. Admin: structure → import students → create exam → faculty enters marks → import marks with errors → fix → process → approve → publish.
3. Student: activate → login → view result → download marksheet → history.
4. Verifier: scan code → verified page; after correction → superseded.
5. Isolation demo: Thapar student tries Demo School resource → 404.
6. Plan limit: Free tenant imports 151st student → limit error with upgrade prompt.
7. Platform admin: suspend tenant → tenant portal shows unavailable page.

## 8. Test data
- Factories for every entity; a deterministic synthetic data generator (`scripts/seed_synthetic.py --tenants 3 --students 8000 --seed 42`) used by E2E, load tests and demos.
- Never use real student data in non-production environments.

## 9. Traceability
Each SRS requirement ID (`FR-xx`, `NFR-xx`) maps to test IDs in the [SRS traceability matrix](SRS.md#7-traceability-matrix); test reports list pass/fail per requirement — strong evidence for the SE evaluation.
