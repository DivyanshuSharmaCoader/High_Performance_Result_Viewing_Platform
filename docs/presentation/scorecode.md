---
marp: true
title: ScoreCode
paginate: true
theme: default
---

<!-- Export: npx @marp-team/marp-cli docs/presentation/scorecode.md --pdf (or --pptx).
     The live demo follows docs/demo/README.md. Every number on these slides is measured; sources in
     docs/reports/benchmark-report.md and docs/reports/test-report.md. -->

# ScoreCode
### Examination results as a service: capture, compute, approve, publish, verify

Multi-tenant SaaS · FastAPI + React · PostgreSQL with row-level security

---

## The problem
- Results live in spreadsheets: **calculation errors**, unclear who changed what.
- Publication day **crashes** the portal, exactly when everyone looks.
- PDFs anyone can edit: **marksheets can't be verified**.
- Every institution builds and secures its own system, or doesn't.

---

## What ScoreCode does
1. **Structure:** sessions, terms, cohorts, courses with credits.
2. **Marks:** a grid that saves as you type, or Excel/CSV imports checked row by row before anything is
   saved.
3. **Compute:** deterministic grading (SGPA, school bands, marks with ranks), with a preview and
   anomalies.
4. **Approve:** re-authentication, optional second approver, marks locked.
5. **Publish:** now or scheduled. Every student's result is frozen as an immutable snapshot.
6. **Marksheets:** PDFs with a QR code, **publicly verifiable**.

---

## One product, many institutions
- Each institution has its own address (`thapar.…`, `demoschool.…`): one build, its own name and colours.
- Plans decide features (Free, Starter, Growth, Pro), with **one** 30-day Pro trial per institution.
- The platform console sees institutions, plans and health. **Never student marks.**

*Thapar is a demo tenant: its name only, synthetic students (decision D25).*

---

## Isolation, four times over
1. **Host:** the address decides the institution before any route runs.
2. **Session:** bound to its institution; useless on another host (**401**).
3. **ORM:** every query is scoped to the session's institution.
4. **PostgreSQL row-level security, forced and fail-closed:** a query without context errors.

The isolation suite is generated from the live route table: **every** endpoint is tried with another
institution's ids and cookies.

---

## Architecture
- A **modular monolith** (FastAPI). Module boundaries are enforced by import-linter.
- **PostgreSQL** is the source of truth. It also runs the **job queue** (`SKIP LOCKED`), so there's no
  extra broker.
- **Redis** holds no truth: caches and limits degrade to per-process without it.
- **Workers:** result processing, PDF rendering in a process pool, notifications.
- **Caddy** at the edge: TLS, security headers, routing by host, load balancing across API containers.

---

## Result day, measured
1,000 students in 60 s, on one 4-vCPU machine that also runs the load generator:

| | Before | After |
|---|---|---|
| Throughput | 322–327 req/s | **573–593 req/s** |
| Failed requests | 3.3–3.6% | **0%** |
| p95 latest result (end to end) | 4.4 s | **0.24–0.28 s** |
| SQL statements per request | 6.86 | **1.65** |

How: a profile first (38.7% of CPU in the ORM). Then a read cache, transactions that start lazily,
pinging only idle connections, and route order. **About 35% less CPU per request.**

---

## Failures, on purpose
- **Redis stopped under load:** nothing visible changed.
- **PostgreSQL restarted under load:** one 10-second window of *retryable* 503s, **no 500s**, recovered
  by itself.
- **Worker killed mid-render:** 8,000 marksheets, **each exactly once**.
- **Database destroyed:** restored from an encrypted backup, fingerprints identical (including every
  RLS policy). **RTO 57 s.**
- **API stopped:** the page email arrived in **101 s**.

---

## Security
- Argon2id, a breached-password check, rate limits per *real* client address, lockout.
- **Two-step sign-in** (TOTP, recovery codes), re-authentication for approval and publication.
- **Audit log** for every state change, in the same transaction, append-only.
- **OWASP ASVS L2** checklist; Bandit, pip-audit, Trivy, gitleaks in CI; **ZAP baseline: no High**.
- **Verification:** a 128-bit code, a masked identity, a SHA-256 of the PDF.

---

## Evidence
| | |
|---|---|
| Backend tests | 515 (319 unit, 200 integration on real services) |
| Frontend tests | 80 component and unit |
| End to end | 32 Playwright on the full stack, plus the 8-step demo script |
| Coverage | 81% backend (grading engine ≥ 90% branches, gated) |
| Mutation checks | the security-critical changes broken on purpose, and caught |
| Operations | alert delivery, restore drill, deploy rehearsal with automatic rollback: all in CI |

---

## Demo
*(docs/demo/README.md: 15 minutes)*
1. Three institutions, one build.
2. A marks file with five mistakes is caught, then the fixed file is imported.
3. Publish live; the student sees SGPA and two years of history.
4. Verify the PDF by its QR code.
5. Isolation attempt: **401**.
6. Plans and limits; the platform console.

---

## What's next (V1)
- Corrections with a diff and versioned re-publication.
- Billing (Razorpay, GST invoices).
- Custom domains.
- Tenant data export and closure.
- Advanced analytics.
- API keys and webhooks.
- A real deployment, with uptime from two regions. The pipeline is ready: the release workflow, the
  hardened production compose, deploy with rollback, runbooks.

---

# Thank you
ScoreCode · `docs/` holds the design, `docs/reports/` the evidence, `docs/runbooks/` how to run it.
