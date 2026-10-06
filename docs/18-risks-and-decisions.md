# 18 · Critical Review, Risks, and Decisions Before Code

> Covers brief section **T** (technical risks), §36 (act as a critical CTO) and the closing ask: *"the decisions we need to make before writing the first line of production code."*

---

## 1. Critical CTO review of the idea

### What is good
- **Narrow scope.** Exam + result infrastructure is a real, recurring, painful job — and small enough to build well.
- **Multi-tenant from day one.** Retrofitting tenancy is one of the most expensive rewrites in SaaS; designing it in now is the right call.
- **Thapar as a tenant, not as the product.** Turns a college project into a credible platform demo.
- **Insistence on measured performance claims.** Rare and valuable; it will make the project more credible to faculty and interviewers than any inflated number.
- **Entitlements instead of `if plan == ...`.** Correct instinct.

### What is weak
- **The "high-performance" framing is aimed at the wrong buyer.** Small institutions don't have a traffic problem; they have an *error and effort* problem. Performance is a supporting proof point, not the headline. ([01 §C](01-product-definition.md#c-target-market--a-critical-evaluation))
- **Seasonality.** Schools publish 2–4 times a year → the product is invisible between peaks → churn risk. Coaching institutes (weekly tests) and historical access/analytics counter this.
- **Domain variety is underestimated.** CBSE-style report cards, credit-based SGPA/CGPA, supplementary exams, grace marks, relative grading, moderation, re-evaluation — each institution type has rules. Without a pluggable grading engine and constrained templates this becomes custom work for every customer.
- **"Student" in schools is actually a parent** — UX and consent implications (DPDP Act, minors).

### What is unrealistic (as originally stated)
- ">10,000 concurrent users, >5,000 RPS, 99.9% availability" as *claims*. 99.9% availability means < 44 min downtime/month — impossible to promise on a single VM, and not measured. Keep these as **targets** with measurement plans. ([11](11-performance-architecture.md))
- Selling to universities in year one (tenders, committees, existing systems).
- A full feature list for V1 that includes SSO, custom domains, campuses, API, WhatsApp, advanced analytics — that's two years of work for a small team.

### What should be removed or changed
| Remove/Change | Instead |
|---|---|
| WebSockets | Polling now, SSE later for admins only |
| System monitoring in tenant UI | Platform console only |
| Locking import and PDF behind paid plans | Gate volume, not the core workflow |
| DOB-as-password logins | Activation codes / invite links |
| Monthly-first billing | Annual-first |
| Path-based tenancy for dev/demo | Host-based everywhere (`*.localhost`) |
| Generic permissions table in V1 | Fixed roles; custom roles in Enterprise |
| "Performance & security phases at the end" | Built-in from Phase 2; dedicated phases only for *measurement* and *review* |

### What could become a moat
1. **The verification network** (`verify.scorecode.in` trusted by employers/institutions).
2. **Import intelligence** — mapping presets, error detection tuned on hundreds of real messy spreadsheets.
3. **Historical records** — years of results create natural retention (with fair export).
4. **Grading-scheme library** — pre-built, tested schemes for common Indian boards/universities.

### What is unnecessary engineering (for now)
Kubernetes, Kafka, microservices, service mesh, GraphQL, multi-region, sharding, CQRS with separate databases, event sourcing, custom permission engines, real-time dashboards for students.

### What could create security problems
- Shared-schema tenancy without RLS (one forgotten `WHERE`).
- Cookies scoped to `.scorecode.in` (would leak sessions across tenants) — must be host-only.
- Tenant-editable HTML/CSS templates (XSS/SSRF) — sandbox and constrain.
- Bulk PDF of all students' marks (privacy) — per-student documents only.
- Support staff with raw DB access — use audited support sessions.
- Custom-domain TLS issuance without verification (abusable) — `ask` endpoint.
- Spreadsheet uploads (zip bombs, formula injection in exports).
- Weak student activation (guessable credentials).

### What could make customer acquisition difficult
- Unknown brand handling sensitive data → trust gap (security page, DPA, references).
- ERP bundling ("we already have it").
- Low budgets; long payment collection.
- Onboarding effort (structures, students) — must be self-serve with templates and "copy last year".
- Language (Hindi/regional UI expectations in some segments).

---

## 2. Risk register

| ID | Risk | Type | Likelihood | Impact | Mitigation | Owner/phase |
|---|---|---|---|---|---|---|
| R1 | Cross-tenant data leak | Security | Low (with design) | **Critical** | 5 isolation layers, RLS fail-closed, isolation test suite as merge gate | P2 onward |
| R2 | Wrong results published (grading bug / bad import) | Correctness | Medium | **Critical** | Pure grading engine + property tests, validation, preview/anomalies, approval gate, correction workflow | P7–P10 |
| R3 | Outage during a publication | Performance/Ops | Medium | High | Read model, pre-rendered PDFs, load tests, pre-scaling, scheduled publication alerts | P10, P14 |
| R4 | Login stampede on result day | Performance | High | Medium | Pre-activation, long student sessions, bounded Argon2, 429 + retry UX | P3, P14 |
| R5 | Scope creep into ERP | Product | High | High | Scope rules in [04](04-feature-scope.md); paid customisation | All |
| R6 | Grading diversity → custom work per customer | Product/Tech | High | Medium | Strategy-based grading, scheme library, Enterprise pricing for custom algorithms | P7, V1 |
| R7 | DPDP / minors' data compliance gaps | Legal | Medium | High | Legal review before school launches; DPA; consent support; minimisation; Indian hosting | Pre-launch |
| R8 | Data loss | Ops | Low | **Critical** | Managed PITR, off-site dumps, monthly restore drills | P16 |
| R9 | Single-developer bus factor | Org | High | High | Docs (this folder), ADRs, checklists, tests, IaC | All |
| R10 | Low willingness to pay / churn after season | Business | Medium | High | Annual billing, coaching segment, analytics/history value | GTM |
| R11 | Email deliverability (results emails in spam) | Ops | Medium | Medium | SPF/DKIM/DMARC, reputable provider, in-app notifications | P12 |
| R12 | Excel quirks break imports | Product | High | Medium | Golden corpus of messy files, mapping presets, annotated error reports | P8 |
| R13 | RLS performance or pooling pitfalls | Tech | Low | Medium | Simple policies, explicit predicates, `SET LOCAL`, benchmark | P2, P14 |
| R14 | PDF rendering too slow | Tech | Medium | Medium | Pre-render; ReportLab fallback; separate worker pool | P11, P14 |
| R15 | Abuse of free tier (spam tenants, phishing pages via branding) | Security | Medium | Medium | Email verification, limited branding on Free, platform suspend, reserved slugs | P4 |

---

## 3. Decision register — confirm before writing production code

Status: **Proposed** = my recommendation, awaiting your confirmation. Once confirmed, mark **Accepted** and (optionally) expand into an ADR under `docs/adr/`.

| ID | Decision | Recommendation | Status |
|---|---|---|---|
| D1 | Architecture style | Modular monolith, one image with `api`/`worker` modes | Proposed |
| D2 | Tenancy model | Shared DB/schema, `tenant_id` + composite FKs + RLS (FORCE, fail-closed) | Proposed |
| D3 | User identity scope | Users belong to exactly one tenant | Proposed |
| D4 | Tenant routing | Host-based everywhere; `*.localhost` in dev; custom domains (Pro, V1) via Caddy on-demand TLS | Proposed |
| D5 | Auth | Opaque server-side sessions, `__Host-` cookies, Argon2id, TOTP for platform & owners | Proposed |
| D6 | Student onboarding | Activation codes / invite links; no DOB passwords | Proposed |
| D7 | Primary keys | UUIDv7 generated in app | Proposed |
| D8 | Job queue | PostgreSQL-backed (Procrastinate or in-house SKIP LOCKED) | Proposed — spike both in Phase 1 |
| D9 | Redis | Optional/degradable; required in small production | Proposed |
| D10 | Read model | Immutable `published_results` snapshots + versioned publications | Proposed |
| D11 | PDF engine | WeasyPrint, pre-rendered on approval | Proposed — validate speed in Phase 11 |
| D12 | Real-time | Polling; SSE later; no WebSockets | Proposed |
| D13 | Frontend | Vite + React + TS SPA; separate platform console app; server-rendered verify page | Proposed |
| D14 | Grading in MVP | Percentage bands + marks-only + **credit/SGPA** (for Thapar) | Proposed |
| D15 | Scheduled publication in MVP | Yes (demo story) | Proposed |
| D16 | Approval mode in MVP | Single-step; maker–checker in V1 | Proposed |
| D17 | Billing in MVP | Manual (platform admin sets plan); Razorpay in V1 | Proposed |
| D18 | Beachhead segment | Coaching institutes + mid-size private schools; colleges as showcase | Proposed — validate with discovery calls |
| D19 | Hosting region | India (e.g. AWS ap-south-1 or equivalent Indian region) | Proposed |
| D20 | Demo hosting | Single VM + docker compose + Cloudflare | Proposed |
| D21 | Repo layout | Monorepo: `backend/`, `frontend/` (pnpm workspace), `infra/`, `docs/`, `benchmarks/` | Proposed |
| D22 | Package managers | `uv` (Python), `pnpm` (JS) | Proposed |
| D23 | Domain names | Register `scorecode.in` (or available alternative) + a demo domain; check trademark conflicts for "ScoreCode" | **Needs your action** |
| D24 | Licence | Proprietary (all rights reserved) while the repo is public for the college project? Or keep repo private and share with faculty. | **Needs your decision** |
| D25 | Thapar branding/data | Use only public information and synthetic student data; get permission before using Thapar's logo/name publicly beyond the academic demo | **Needs your action** |

### Questions for you (short answers are enough)
1. Is the repository going to be **public** (portfolio) or **private**? (affects D24 and secret hygiene)
2. Team size for development — solo, or with project partners? (affects phase durations in the plan)
3. Deadline for the college presentation? (decides how much of V1 to pull into the demo)
4. Do you want Hindi UI in V1, or English only?
