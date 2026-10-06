# 17 · Recommended Technology Stack (with justification)

> Covers brief section **U**, §10 ("for every major component explain why, problem, alternatives, choice, complexity"), §27 and the comparisons demanded in §36.

"High-level" here means **mature, widely-used, horizontally scalable technologies** — not the most fashionable ones. Every component must earn its place.

---

## 1. Stack at a glance

| Layer | Technology | Version policy |
|---|---|---|
| Frontend | React 18/19 + TypeScript (strict) + Vite, React Router, TanStack Query, react-hook-form + zod, Tailwind CSS + Radix UI | latest stable |
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + asyncpg, Alembic, Uvicorn | latest stable |
| Database | PostgreSQL 16+ (RLS, JSONB, partitioning, pg_trgm, pg_stat_statements) | managed in prod |
| Background jobs | PostgreSQL-backed queue (Procrastinate, or minimal in-house `SKIP LOCKED` queue) | |
| Cache / rate limit | Redis 7 (optional dependency, never source of truth) | |
| Object storage | S3 API (AWS S3 Mumbai / Cloudflare R2; MinIO in dev) | |
| PDF | WeasyPrint (HTML/CSS → PDF) + `qrcode`/`segno` | |
| Spreadsheet I/O | openpyxl (read-only mode), Python `csv`, `charset-normalizer` | |
| Auth crypto | argon2-cffi (Argon2id), `secrets`, `cryptography` (AES-GCM), pyotp (TOTP) | |
| Email | Amazon SES / Postmark / Resend via provider adapter; Mailpit in dev | |
| Reverse proxy | Caddy (automatic TLS, on-demand TLS for custom domains) | |
| Edge | Cloudflare (DNS, CDN, WAF, DDoS) | |
| Containers | Docker, docker compose (dev/demo) | |
| CI/CD | GitHub Actions, GHCR | |
| IaC | Terraform/OpenTofu (from small prod) | |
| Observability | structlog, Prometheus client, Grafana, Sentry, OpenTelemetry (staged), uptime monitor | |
| Testing | pytest, Hypothesis, httpx, Testcontainers, factory_boy, Schemathesis, Vitest, RTL, Playwright, axe-core, k6, Toxiproxy | |
| Code quality | ruff, mypy, import-linter, ESLint, Prettier, pre-commit, Bandit/semgrep, gitleaks, pip-audit, Trivy | |
| Package mgmt | `uv` (Python), `pnpm` (JS workspaces) | |

---

## 2. Component justifications

### React + TypeScript + Vite (frontend)
- **Why needed / problem:** rich, stateful admin UIs (marks grid, import review, exam workspace) plus a fast student SPA; one design system for four experiences.
- **Alternatives:** Vue/Svelte (fine, smaller ecosystem for data grids), Next.js (SSR not needed, adds Node runtime), server-rendered templates + HTMX (great for simple pages, weaker for the marks grid).
- **Chosen because:** ecosystem (TanStack, Radix), hiring/recruiter value, static deploy to CDN.
- **Complexity:** client-side state & bundle discipline → code splitting and bundle budgets.

### FastAPI (backend framework)
- **Why:** typed request/response models, automatic OpenAPI (feeds the TS client and API docs), async I/O, dependency injection for tenant/auth/entitlements.
- **Alternatives:** Django + DRF (batteries included: admin, ORM, auth — strong option; weaker async story, heavier for a pure API), Node/NestJS, Go.
- **Chosen because:** the brief's preference, team familiarity, OpenAPI-first contract, async fit for I/O-bound read spikes.
- **Complexity:** FastAPI gives less structure than Django — we add it ourselves (module layout, import-linter, UoW). Need to be careful with blocking calls in async code.

### PostgreSQL (primary database)
- **Why:** relational, integrity-critical data with constraints; RLS for tenant isolation; JSONB for flexible-but-validated shapes; partitioning; mature managed offerings in India.
- **Alternatives:** MySQL (no RLS; fine otherwise), MongoDB (weaker relational integrity — wrong fit for academic records), CockroachDB/Yugabyte (distributed SQL — unnecessary complexity and cost at this scale).
- **Chosen because:** correctness + isolation features + it also runs the job queue.
- **Complexity:** RLS pitfalls (owner bypass, pool leakage) → handled by role design and `SET LOCAL`.

### SQLAlchemy 2.0 + Alembic
- **Why:** composable SQL with bound parameters, async support, explicit transactions, migrations.
- **Alternatives:** raw asyncpg (fast, verbose, easy to forget tenant filters), SQLModel (thin layer over SQLAlchemy — fine but adds little), Tortoise/Prisma-py (less mature).
- **Complexity:** ORM learning curve; we use Core-style queries on hot paths.

### PostgreSQL-backed job queue
- **Why:** imports, processing, PDFs, notifications, scheduled publications.
- **Alternatives:** Celery + Redis/RabbitMQ, arq/RQ (Redis), cloud queues (SQS).
- **Chosen because:** transactional enqueue, no extra critical infrastructure. Comparison table in [08 §6](08-backend-architecture.md#6-background-jobs).
- **Complexity:** polling/LISTEN load on DB (negligible at our volume); revisit if queue throughput is measured as a bottleneck.

### Redis (justified, optional)
- **Why:** cross-node rate limiting, session/config/entitlement caches, optional hot result cache.
- **Alternatives:** no Redis (in-process caches + DB rate limits) — viable for single-node MVP; Memcached (no atomic scripts for rate limiting).
- **Chosen because:** small, cheap, well-understood; only introduced as a *degradable* dependency.
- **Complexity:** one more service; cache-correctness discipline (versioned/immutable keys).

### Object storage (S3-compatible)
- **Why:** PDFs, logos, uploads, exports — binary data must not bloat Postgres.
- **Alternatives:** local disk (breaks horizontal scaling), Postgres `bytea` (backup bloat).
- **Chosen:** S3 API so we can switch providers; R2 avoids egress fees; MinIO in dev.

### WeasyPrint for marksheets
- **Why:** marksheet templates as HTML/CSS → tenants' branding and custom templates are just templates.
- **Alternatives:** ReportLab (faster, code-drawn layouts — harder to customise), headless Chromium (excellent fidelity, heavy memory/CPU, larger attack surface), wkhtmltopdf (unmaintained).
- **Complexity:** CPU-heavy → runs only in workers, pre-rendered on approval. If benchmarks show it's too slow, ReportLab for the default template is the fallback.

### Caddy (reverse proxy)
- **Why:** automatic HTTPS, wildcard certs via DNS challenge, **on-demand TLS** for custom domains with an `ask` endpoint.
- **Alternatives:** Nginx + certbot (manual cert orchestration for custom domains), Traefik (good, more config surface), cloud LB + CDN custom hostnames (good at scale).
- **Complexity:** small; replace/augment with cloud LB in growing production.

### Cloudflare (edge)
- **Why:** free CDN for SPA assets, DNS, DDoS protection, WAF rules for login abuse.
- **Alternatives:** CloudFront, Fastly, no CDN.
- **Complexity:** another vendor; keep origin locked to Cloudflare IPs.

### Docker / docker compose
- **Why:** identical environments dev→prod, reproducible builds.
- **Not Kubernetes (yet):** K8s solves orchestration problems we don't have at 1–4 nodes and costs real ops time. Revisit when running >10 services/nodes or when a container platform with autoscaling is required and the team knows K8s; managed container services (ECS/Fargate, Cloud Run-style) are the simpler next step.

---

## 3. Head-to-head decisions requested in the brief (§36)

| Choice | Recommendation | Short reason (details link) |
|---|---|---|
| **PostgreSQL RLS vs app-level isolation** | **Both** (app filters + RLS fail-closed) | Defence in depth — [06 §2](06-multi-tenancy.md#2-application-level-isolation-vs-postgresql-row-level-security) |
| **JWT vs secure sessions** | **Opaque server-side sessions** in `__Host-` HttpOnly cookies; API keys for integrations | Revocation, tenant binding, XSS resistance — [10 §2](10-security-architecture.md#2-authentication) |
| **WebSockets vs SSE vs polling** | **Polling (MVP) → SSE if measured need; no WebSockets** | Only admins need progress — [11 §2.9](11-performance-architecture.md#29-real-time-updates-websockets-vs-sse-vs-polling) |
| **Single DB vs DB-per-tenant** | **Single shared DB**; silo deployments for Enterprise | Cost & ops — [06 §1](06-multi-tenancy.md#1-tenancy-model-choosing-the-isolation-level) |
| **Path vs subdomain routing** | **Host-based (subdomain) everywhere**, custom domain on Pro | Origin isolation for cookies — [06 §4](06-multi-tenancy.md#4-tenant-aware-routing) |
| **Modular monolith vs microservices** | **Modular monolith** | Transactions, team size — [08 §1](08-backend-architecture.md#1-style-modular-monolith) |
| **Redis vs no Redis** | **Optional, degradable Redis** from small production | Shared rate limits & caches; never truth — [11 §2.5](11-performance-architecture.md#25-caching-redis--where-it-is-and-isnt-justified) |
| **Managed vs self-hosted DB** | **Self-hosted for demo; managed from first paying customer** | Backups/PITR/failover — [14](14-deployment-and-operations.md#managed-vs-self-hosted-database) |
| **Celery vs Postgres queue** | **Postgres queue** | Transactional enqueue — [08 §6](08-backend-architecture.md#6-background-jobs) |
| **SPA vs SSR** | **SPA on CDN** (+ server-rendered verify page) | Result-day cost — [09 §1](09-frontend-architecture.md#1-applications-and-why-they-are-split-this-way) |

## 4. Deliberately NOT used (and when they might be)
| Technology | Why not now | Would reconsider when |
|---|---|---|
| Kafka / event bus | No high-volume event streams; in-process events + DB queue suffice | Multiple independently deployed services need durable event streams |
| Kubernetes | Ops overhead > benefit at this size | >10 nodes, multiple services, team with K8s skills |
| Microservices | Distributed transactions, duplicated isolation logic | A module has a clearly different scaling/isolation profile (PDF, verification) |
| Service mesh | Nothing to mesh | Many services with mTLS needs |
| GraphQL | REST + OpenAPI fits CRUD + workflows; GraphQL complicates authz & caching | Many third-party clients with diverse data needs |
| Elasticsearch | `pg_trgm` covers name search | Full-text search across large document sets |
| NoSQL primary DB | Integrity-critical relational data | — |
| WebSockets | No bi-directional real-time need | Live collaborative marks entry (unlikely) |
