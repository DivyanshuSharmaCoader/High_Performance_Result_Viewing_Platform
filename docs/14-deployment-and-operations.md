# 14 · Deployment, CI/CD and Observability

> Covers brief sections **N** (deployment architecture), **P** (CI/CD) and **Q** (monitoring/observability).
> Diagram: [deployment diagrams](diagrams/deployment-diagram.md). Costs per stage: [16 Cost model](16-cost-model.md).

---

## N. Deployment architecture by stage

All stages run **the same container images** built once in CI. Differences are only in topology and configuration.

### N1. Development (laptop)
```
docker compose up
 ├─ proxy     (Caddy)  → *.localhost:8080 routing: /api → api, / → vite dev server
 ├─ api       (FastAPI, --reload, mounted source)
 ├─ worker    (same image, worker mode, autoreload)
 ├─ web       (Vite dev servers: tenant, platform)
 ├─ postgres  (16, with init script creating roles: migrator, app, platform)
 ├─ redis     (optional profile — app must work without it)
 ├─ minio     (S3-compatible object storage)
 └─ mailpit   (catches all outgoing email, web UI)
```
- Hosts: `thapar.localhost:8080`, `demoschool.localhost:8080`, `admin.localhost:8080`, `verify.localhost:8080` — no hosts-file edits needed in modern browsers.
- `make seed` creates demo tenants through the provisioning service (not raw SQL).
- `make test`, `make lint`, `make e2e` mirror CI.

### N2. Demo (college presentation, ~₹1–3k/month)
Single VM in an Indian region (2 vCPU / 4 GB is a reasonable starting point; measure), docker compose:
```
Internet → Cloudflare (DNS, CDN, TLS edge, DDoS) → VM: Caddy (wildcard cert via DNS-01)
   → api ×2 processes, worker ×1, postgres, redis, minio (or Cloudflare R2), backups cron → R2/S3
```
- Wildcard DNS `*.demo-domain` → VM.
- Nightly `pg_dump` to object storage + VM snapshot weekly.
- Honest limitation: single point of failure; fine for demo, **not** for paying customers.

### N3. Small production (first paying tenants)
```
Cloudflare (DNS/CDN/WAF) ──► Load balancer / Caddy pair
                                 ├─ App VM/containers ×2 (api) — different zones
                                 └─ Worker ×1–2
Managed PostgreSQL (HA standby, PITR, Indian region)
Managed Redis (small) — or self-hosted on app VM initially (holds no truth)
Object storage (S3 ap-south-1 or Cloudflare R2) — private buckets, versioning on PDFs
Email: SES (ap-south-1) or Postmark/Resend
Static frontends: Cloudflare Pages / S3 + CloudFront
Monitoring: Grafana Cloud free/low tier or self-hosted Prometheus+Grafana on a tiny VM; Sentry; uptime checks
```
- Zero-downtime deploys: rolling restart behind LB; migrations expand-first.
- Managed DB is worth its premium here: backups, PITR, failover and patching are the riskiest ops work for a tiny team.

### N4. Growing production
- Container platform with autoscaling and scheduled pre-scaling (e.g. AWS ECS Fargate, or Kubernetes **only if the team already operates it**).
- PgBouncer (or RDS Proxy), read replica for analytics/exports, separate worker pools per queue (PDF workers on CPU-optimised instances).
- Possibly extract `documents` (PDF) and `verification` as separate deployables from the same codebase.
- WAF rules, bot management for login endpoints.
- Status page; on-call rotation.
- Enterprise silo deployments via the same IaC (Terraform/OpenTofu module parameterised per silo).

### Managed vs self-hosted database
| | Self-hosted PG on VM | Managed PG (RDS / DO / Azure / Cloud SQL) |
|---|---|---|
| Cost | Lowest | ~1.5–3× compute cost |
| Backups/PITR | You build & test | Built-in |
| HA failover | Hard (Patroni etc.) | Checkbox |
| Upgrades/patching | You | Managed |
| **Recommendation** | Demo/dev | **Small production onward** |

### Infrastructure as code
- Demo: a documented `docker-compose.prod.yml` + bootstrap script (Ansible optional).
- Small prod onward: Terraform/OpenTofu for cloud resources; secrets in the cloud secret manager.

---

## P. CI/CD pipeline (GitHub Actions)

### Git workflow
- **Trunk-based**: short-lived feature branches → PR → `main`. Branch protection: required checks, 1 review (self-review checklist when solo), linear history (squash merge).
- Conventional Commits (`feat:`, `fix:`, `docs:`…) → automated changelog.
- Releases: tag `vX.Y.Z` → production deploy with manual approval.

### Pipeline
```
on PR:
  ├─ lint-backend      ruff (lint+format), mypy --strict (core, grading, services), import-linter (module boundaries)
  ├─ lint-frontend     eslint, prettier --check, tsc --noEmit
  ├─ test-backend-unit pytest -m "not integration" (fast, no services)
  ├─ test-backend-int  pytest -m integration with service containers: postgres, redis, minio
  │                    includes: RLS coverage test, tenant isolation suite, migration up/down check,
  │                    OpenAPI schema diff vs committed openapi.json
  ├─ test-frontend     vitest + coverage; bundle size budget check
  ├─ security          gitleaks, pip-audit, pnpm audit (high+), bandit/semgrep, trivy fs
  ├─ build-images      docker buildx (api/worker image, frontend static bundles), trivy image scan
  └─ e2e               docker compose up (built images) → seed → Playwright smoke (publish flow, isolation demo)
on merge to main:
  ├─ all of the above
  ├─ push images to registry (GHCR) tagged with git SHA
  └─ deploy to STAGING (automatic) → smoke tests → ZAP baseline scan (weekly/nightly)
on tag v*:
  └─ deploy to PRODUCTION (manual approval) → run migrations (expand) → rolling deploy → smoke → notify
nightly:
  └─ k6 scenario A against staging (performance regression signal), dependency update PRs (Dependabot/Renovate)
```

Quality gates: coverage thresholds on `grading`, `entitlements`, `identity`, `publishing` (e.g. ≥ 90% lines/branches — these are where bugs are expensive); overall coverage tracked, not gated aggressively.

### Database migrations in CD
- Alembic migration runs as a one-off job **before** new app version starts; only backward-compatible (expand) migrations in the same release; destructive (contract) migrations ship one release later.
- CI test: `upgrade head` from empty DB, and `upgrade` from previous release's schema with sample data.

---

## Q. Monitoring & observability

### Logs
- JSON logs via `structlog` → stdout → collected (Docker log driver → Loki/Grafana Cloud, or Better Stack/Axiom on free tiers).
- Fields: `ts, level, request_id, tenant_id, user_id(opaque), route, method, status, duration_ms, job_id`.
- PII scrubbing processor; tests assert that marks/names/tokens never appear in logs.
- Retention: 14–30 days hot (cost control); audit log is separate and in the DB.

### Metrics (Prometheus format, `/metrics` on an internal port)
| Category | Metrics |
|---|---|
| HTTP (RED) | request rate, error rate, duration histogram by route class (`student_read`, `login`, `admin`, `verify`) |
| Business | logins/min, publications/day, marksheet downloads, imports processed, active tenants |
| DB | pool in-use/idle/waits, query duration, `pg_stat_database`, connections, replication lag |
| Redis | hit/miss by cache name, latency, errors, circuit-breaker state |
| Jobs | queue depth per queue, job latency, failures, dead letters |
| Runtime | CPU, memory, event-loop lag, Argon2 semaphore wait time |
The platform admin console reads a curated subset (via Prometheus API or the app's own aggregates) — this satisfies the "system health/cache metrics" requirement without exposing raw infra to tenants.

### Tracing
- OpenTelemetry instrumentation (FastAPI, SQLAlchemy, httpx, Redis) **off by default in MVP**, enabled in staging/load tests to find bottlenecks; production sampling (e.g. 5%) in V1. Justification: with a monolith, logs + metrics + `pg_stat_statements` answer most questions; tracing pays off during performance work.

### Errors
- Sentry (or GlitchTip self-hosted) for backend and frontend, with `tenant_id`/`request_id` tags and PII scrubbing.

### Health checks
| Endpoint | Checks | Used by |
|---|---|---|
| `GET /livez` | process alive | container restart |
| `GET /readyz` | DB reachable (simple query, short timeout); migrations at expected head | load balancer |
| `GET /api/v1/platform/health/deep` (authenticated) | DB, Redis, object store, email provider, queue depth, last backup age | platform console |
Redis failure → `readyz` stays **green** (degraded mode), reported in deep health.

### Alerts (start small, actionable only)
| Alert | Condition (initial — tune) | Severity |
|---|---|---|
| API error rate | 5xx > 1% for 5 min | page |
| Student read latency | p95 > target for 10 min | page during publication windows |
| DB | CPU > 80% 10 min; connections > 80%; storage > 80% | warn/page |
| Jobs | queue depth growing 15 min; dead letters > 0 | warn |
| Scheduled publication | publication job not completed within 2 min of scheduled time | **page** |
| Backups | last successful backup > 26 h; restore drill failed | page |
| TLS | cert expiry < 14 days | warn |
| Uptime | external check fails 2× from 2 regions | page |
| Security | spike in login failures; RLS policy violation errors (should be zero) | warn/page |

### Runbooks
`docs/runbooks/` (created during Phase 16): DB restore, Redis outage, stuck publication, rollback deploy, tenant data export/deletion, incident communication template.

---

## R. Email deliverability (P12.2)

Results emails only help if they reach the inbox. They go from one sending domain, for example
`mail.scorecode.in`, through a provider's SMTP relay (Amazon SES or Postmark; the adapter is plain SMTP,
`SCORECODE_SMTP_*`).

| Record | Where | Value (example) | Why |
|---|---|---|---|
| **SPF** | TXT on `mail.scorecode.in` | `v=spf1 include:amazonses.com -all` (or Postmark's `include:spf.mtasv.net`) | Only the provider may send for the domain |
| **DKIM** | CNAME/TXT records the provider issues (2048-bit) | e.g. three `*._domainkey.mail.scorecode.in` CNAMEs for SES Easy DKIM | Messages are signed; receivers can tell tampering |
| **DMARC** | TXT on `_dmarc.scorecode.in` | Start `v=DMARC1; p=none; rua=mailto:dmarc@scorecode.in; adkim=s; aspf=s`. Move to `p=quarantine`, then `p=reject`, once reports are clean for 2–4 weeks | Tells receivers to reject spoofed "ScoreCode" mail; the reports show who sends as us |
| **Return-Path / MAIL FROM** | The provider's custom MAIL FROM subdomain (`bounce.mail.scorecode.in`) | MX and SPF the provider gives | SPF alignment for DMARC |

**Sender.**
- `SCORECODE_MAIL_FROM`, e.g. `"Thapar Results via ScoreCode" <results@mail.scorecode.in>`.
- Institution replies go in `Reply-To` (the tenant's support email). Never send *From* an institution's
  own domain: we can't sign for it.

**Volume.**
- `SCORECODE_MAIL_RATE_PER_SECOND` (default 10 per job) keeps each batch under the provider's sending
  rate. A tenant runs at most 2 jobs at once, so the ceiling is 20 emails/s, or about 7 minutes for 8,000
  students. That is arithmetic, not a measurement; it gets measured with the provider in Phase 16.
- Raise the provider's quota before the first large result day (SES starts in a sandbox).

**Content.**
- Plain, short, a link to the tenant host and no marks: docs/03 W11 and a test.
- Both a text and an HTML part.

**Bounces and complaints (not built yet; Phase 16).**
- The provider's webhook (SES via SNS, or Postmark) should mark the address undeliverable so it's
  skipped.
- Until then, failed sends are retried and then recorded as `failed` in `notification_deliveries`, and
  administrators see the count on the publication.

**Checks before launch.**
- Send to Gmail, Outlook and a college Google Workspace inbox, and confirm `spf=pass dkim=pass
  dmarc=pass` in the headers.
- Check the domain on Google Postmaster Tools.

