# Software Architecture Specification — ScoreCode

| | |
|---|---|
| Document | Software Architecture Specification (SAS) |
| Version | 1.0 (draft, Phase 0) |
| Date | 2026-10-06 |
| Structure | ISO/IEC/IEEE 42010 concepts (stakeholders, concerns, viewpoints) organised with the **4+1 view model** and arc42-style sections |
| Requirements | [SRS](SRS.md) |

> Note on naming: the brief asked for a "SAS file". It is interpreted here as the **Software Architecture Specification** — the companion to the SRS that describes *how* the requirements are met. This document is the architectural entry point; it summarises and links to the detailed design documents rather than duplicating them.

---

## 1. Introduction and goals

### 1.1 Purpose
Describe ScoreCode's architecture for developers, reviewers (faculty, interviewers) and future team members: the structures, the decisions behind them, and how they satisfy the quality goals.

### 1.2 Quality goals (ranked)
1. **Correctness** of computed and published results.
2. **Security** of personal and academic data.
3. **Tenant isolation** (invariant I-1: no cross-tenant access).
4. **Maintainability** by a small team.
5. **Simplicity** of operations.
6. **Performance** on result day.
7. **Scalability** with tenant growth.
8. **Cost efficiency** for small customers.

### 1.3 Stakeholders and concerns
| Stakeholder | Concerns | Addressed in |
|---|---|---|
| Students | Fast, available, private results | §6 runtime view, [11](11-performance-architecture.md) |
| Institution admins/owners | Correct results, control, audit, branding, price | [03](03-core-workflows.md), [10 §9](10-security-architecture.md#9-audit-logging-20), [02](02-business-model.md) |
| Faculty | Easy marks entry/import | [13](13-result-ingestion.md) |
| Platform operator | Isolation, operability, cost, metrics | [06](06-multi-tenancy.md), [14](14-deployment-and-operations.md), [16](16-cost-model.md) |
| Developers | Clear modules, testability | [08](08-backend-architecture.md), [15](15-testing-strategy.md) |
| Faculty evaluators / interviewers | SE rigour, traceability | [20](20-se-deliverables.md), [SRS §7](SRS.md#7-traceability-matrix) |
| Regulators (indirect) | DPDP compliance, data residency | [10 §11](10-security-architecture.md#11-privacy--compliance-india) |

---

## 2. Constraints
Technical: Python/FastAPI backend, React/TypeScript frontend, PostgreSQL primary store, Docker deployment, India hosting. Organisational: 1–3 developers, university timeline, low budget. Conventions: no unmeasured performance claims; documentation in Markdown + Mermaid in the repository.

---

## 3. Context and scope
- Business context: [component-diagram §1](diagrams/component-diagram.md#1-system-context-c4-level-1).
- External interfaces: browsers (HTTPS), email provider, object storage, payment provider (V1), ERP integrations (V1 REST/webhooks), DNS/CDN.

---

## 4. Solution strategy

| Goal | Strategy |
|---|---|
| Correctness | Pure grading engine (strategy pattern), validation-first imports, state machines, approval gate, immutable versioned publications, DB constraints |
| Security & isolation | Five isolation layers incl. PostgreSQL RLS (fail-closed) and composite FKs; opaque tenant-bound sessions; append-only audit |
| Maintainability & simplicity | Modular monolith with enforced boundaries; one image, two modes; PostgreSQL also hosts the job queue |
| Performance | CQRS-lite: heavy work on write path, immutable snapshot read model; CDN static; pre-rendered PDFs; login spike controls |
| Scalability | Stateless API/workers; horizontal scaling; PgBouncer; read replica; silo deployments for Enterprise |
| Cost | Shared infrastructure for all non-Enterprise tenants; optional Redis; free-tier limits |

---

## 5. Logical view (4+1: logical)
- Domain model: [class diagrams §1](diagrams/class-diagrams.md#1-core-domain-model-simplified).
- Key patterns: [Strategy (grading)](diagrams/class-diagrams.md#2-grading-engine--strategy-pattern-openclosed-principle), [Template Method (imports)](diagrams/class-diagrams.md#3-import-pipeline--template-method--profiles), [Repository / UoW / DI](diagrams/class-diagrams.md#4-application-layer--services-repositories-dependency-inversion).
- State machines: [state diagrams](diagrams/state-diagrams.md).
- Data model: [ER diagrams](diagrams/er-diagram.md), [07 Database](07-database-design.md).

## 6. Process / runtime view (4+1: process)
- API processes (async, stateless) and worker processes (job queues: `imports`, `processing`, `pdf`, `publishing`, `notifications`, `maintenance`, `exports`).
- Concurrency control: DB transactions with tenant context; optimistic locking on mark entries; row locks for entitlement counters; idempotency keys for critical POSTs; job leases.
- Key scenarios: [sequence diagrams](diagrams/sequence-diagrams.md) — tenant resolution, login, import, processing/approval, publication, student read, verification, correction; [collaboration diagrams](diagrams/collaboration-diagrams.md).

## 7. Development view (4+1: development)
Repository layout (monorepo):
```
backend/
  app/
    core/            shared kernel (db, tenant ctx, cache, jobs, config, errors, logging)
    modules/
      platform/ tenancy/ identity/ entitlements/ branding/ academics/ directory/
      examinations/ grading/ marks/ ingestion/ results/ publishing/ documents/
      verification/ notifications/ analytics/ audit/ files/
    main.py          api entrypoint        worker.py   worker entrypoint
  migrations/        Alembic
  tests/             unit/ integration/ isolation/ security/
frontend/
  apps/ tenant/ platform/ site/
  packages/ ui/ api-client/ config/
infra/               docker compose, Caddyfile, terraform (later)
benchmarks/          k6 scripts, results/
docs/                this documentation set
```
Module rules: [08 §2](08-backend-architecture.md#boundary-rules-enforced-in-ci-with-import-linter). Component view: [component diagram §3](diagrams/component-diagram.md#3-backend-component-diagram-modules).

## 8. Physical / deployment view (4+1: physical)
[Deployment diagrams](diagrams/deployment-diagram.md) for development, demo, small production, growing production and Enterprise silo; operations in [14](14-deployment-and-operations.md).

## 9. Scenarios (4+1: +1)
Use cases: [use-case diagram](diagrams/use-case-diagram.md), [SRS §3](SRS.md#3-use-cases). The architecture is validated against these quality-attribute scenarios:

| ID | Quality | Stimulus | Environment | Response | Measure |
|---|---|---|---|---|---|
| QAS-1 | Isolation | Tenant A user requests tenant B's result by ID | Normal operation | 404; no data returned; attempt logged | Isolation suite 100% pass |
| QAS-2 | Isolation | Developer forgets tenant filter in a new query | Code change | Query fails (RLS, no context) or returns only own rows | DB isolation tests |
| QAS-3 | Performance | 1,000 students open results within 60 s of publication | Small production | Results served without errors | p95/p99 + error rate recorded (targets NFR-3, NFR-7) |
| QAS-4 | Availability | Redis fails during publication | Small production | Requests continue via DB; alerts fire | Error rate unchanged within tolerance; latency recorded |
| QAS-5 | Correctness | Admin uploads file with shifted rows | Marks entry | Name-mismatch warnings & total mismatch flagged before commit | Golden-file tests |
| QAS-6 | Auditability | Admin changes a mark after re-evaluation | Correction | New version; diff; audit shows who/what/when/from→to | Audit tests |
| QAS-7 | Modifiability | Customer needs relative grading | Development | New strategy class; no changes to existing strategies or callers | Lines changed outside `grading/` = 0 |
| QAS-8 | Recoverability | Primary DB lost | Small production | Restore from PITR/backup | RTO/RPO from drill |
| QAS-9 | Security | Credential-stuffing on student logins | Internet | Rate-limited, accounts protected, alerts | Rate-limit tests, alert fired |
| QAS-10 | Cost | 50 new Free tenants sign up | Small production | No new infrastructure needed | Infra bill unchanged within noise |

## 10. Cross-cutting concepts
| Concept | Reference |
|---|---|
| Multi-tenancy | [06](06-multi-tenancy.md) |
| Security (authn, authz, CSRF, uploads, secrets, verification) | [10](10-security-architecture.md) |
| Entitlements | [12](12-entitlements.md) |
| Audit | [10 §9](10-security-architecture.md#9-audit-logging-20) |
| Error handling & logging | [08 §9](08-backend-architecture.md#9-error-handling--logging) |
| Caching | [11 §2.5](11-performance-architecture.md#25-caching-redis--where-it-is-and-isnt-justified) |
| Background jobs & events | [08 §6](08-backend-architecture.md#6-background-jobs) |
| Branding / theming | [09 §5–6](09-frontend-architecture.md#5-design-system) |
| Observability | [14 Q](14-deployment-and-operations.md#q-monitoring--observability) |
| Testing | [15](15-testing-strategy.md) |

## 11. Architecture decisions
Decision register D1–D25 with status: [18 §3](18-risks-and-decisions.md#3-decision-register--confirm-before-writing-production-code). Technology justifications and rejected alternatives: [17](17-tech-stack.md). Accepted decisions are recorded as ADRs in `docs/adr/NNNN-title.md` (format: Context · Decision · Consequences · Alternatives).

## 12. Risks and technical debt
Risk register: [18 §2](18-risks-and-decisions.md#2-risk-register). Known deliberate simplifications (to revisit): fixed roles (no custom roles), polling instead of SSE, manual billing in MVP, single region, no field-level encryption of marks.

## 13. Glossary
See [SRS §1.3](SRS.md#13-definitions).
