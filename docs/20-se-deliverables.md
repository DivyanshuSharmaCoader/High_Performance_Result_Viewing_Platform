# 20 · Software Engineering Project Deliverables

> Covers brief section **W** and §30. Maps each deliverable expected by faculty/interviewers to where it lives in this repository and when it's produced.

| # | Deliverable | Location | Status | Produced in |
|---|---|---|---|---|
| 1 | Software Requirements Specification (SRS) | [docs/SRS.md](SRS.md) | ✅ Draft v1.0 | P0 |
| 2 | Software Architecture Specification (SAS) | [docs/SAS.md](SAS.md) | ✅ Draft v1.0 | P0 |
| 3 | System design | [docs/05-system-design.md](05-system-design.md) | ✅ | P0 |
| 4 | Architecture diagrams (C4 context/container, component, deployment) | [docs/diagrams/](diagrams/README.md) | ✅ | P0 (update per phase) |
| 5 | ER diagram & data dictionary | [diagrams/er-diagram.md](diagrams/er-diagram.md), [07-database-design.md](07-database-design.md) | ✅ | P0; regenerate from schema in P2+ |
| 6 | Use-case diagram & use-case descriptions | [diagrams/use-case-diagram.md](diagrams/use-case-diagram.md), [SRS §3](SRS.md#3-use-cases) | ✅ | P0 |
| 7 | Sequence diagrams | [diagrams/sequence-diagrams.md](diagrams/sequence-diagrams.md) | ✅ | P0 |
| 8 | Class diagrams | [diagrams/class-diagrams.md](diagrams/class-diagrams.md) | ✅ | P0 |
| 9 | Collaboration (communication) diagrams | [diagrams/collaboration-diagrams.md](diagrams/collaboration-diagrams.md) | ✅ | P0 |
| 10 | Activity / flow diagrams | [diagrams/activity-diagrams.md](diagrams/activity-diagrams.md) | ✅ | P0 |
| 11 | State machine diagrams | [diagrams/state-diagrams.md](diagrams/state-diagrams.md) | ✅ | P0 |
| 12 | Data flow diagrams (DFD L0/L1) | [diagrams/data-flow-diagrams.md](diagrams/data-flow-diagrams.md) | ✅ | P0 |
| 13 | API documentation | Auto-generated OpenAPI (`/api/docs`, committed `openapi.json`) + [docs/api/README.md](api/README.md) | 🟡 Plan | P2 onward |
| 14 | Test strategy | [15-testing-strategy.md](15-testing-strategy.md) | ✅ | P0 |
| 15 | Test reports (unit/integration/E2E/security, coverage, traceability) | `docs/reports/` (CI artefacts summarised per milestone) | ⏳ | P10, P15, P17 |
| 16 | Performance benchmark report | `benchmarks/results/` ([template](../benchmarks/README.md)) | ⏳ | P10 baseline, P14 final |
| 17 | Deployment documentation | [14-deployment-and-operations.md](14-deployment-and-operations.md) + `docs/runbooks/` | ✅ design / ⏳ runbooks | P16 |
| 18 | User documentation (admin guide, faculty guide, student guide) | `docs/user-guide/` | ⏳ | P17 |
| 19 | Architecture Decision Records | [18 decision register](18-risks-and-decisions.md#3-decision-register--confirm-before-writing-production-code) → `docs/adr/` | ✅ register | P1 onward |
| 20 | Project plan & progress tracking | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), [CHECKLIST.md](CHECKLIST.md), GitHub Projects board | ✅ | P0 |
| 21 | Risk register | [18 §2](18-risks-and-decisions.md#2-risk-register) | ✅ | P0 |
| 22 | Business case | [01](01-product-definition.md), [02](02-business-model.md), [16](16-cost-model.md) | ✅ | P0 |
| 23 | Code quality evidence | CI badges, lint/type/coverage reports, import-linter contracts | ⏳ | P1 onward |
| 24 | Security evidence | Isolation suite results, ZAP report, dependency scan, ASVS checklist | ⏳ | P15 |
| 25 | Demo script & presentation | `docs/presentation/` | ⏳ | P17 |

## Mapping to SE principles (for the report)
| Principle | Evidence in ScoreCode |
|---|---|
| Requirements engineering | SRS with IDs, use cases, NFRs, traceability matrix |
| Architecture | SAS with 4+1 views, quality-attribute scenarios, ADRs |
| Modular design | Bounded-context modules with import-linter contracts |
| SOLID & patterns | [08 §3](08-backend-architecture.md#solid-concretely-good-material-for-the-se-report) |
| Database design | Normalised schema, constraints, RLS, indexes justified by queries |
| API design | REST + OpenAPI, problem+json errors, idempotency, optimistic concurrency |
| AuthN/AuthZ | Sessions, Argon2id, RBAC + ownership + state + entitlement checks |
| Testing | Pyramid + isolation + load + chaos; coverage gates on critical modules |
| CI/CD & Git workflow | Trunk-based, protected main, GitHub Actions pipeline, staged deploys |
| Observability | Structured logs, metrics, health checks, alerts, runbooks |
| Performance engineering | Hypothesis → measurement → optimisation → re-measurement, reproducible reports |
| Security engineering | Threat model, defence in depth, security test suites |
