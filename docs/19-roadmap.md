# 19 · Development Roadmap

> Covers brief section **V** and §29 (development strategy). Step-by-step tasks: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Tick-box progress: [CHECKLIST.md](CHECKLIST.md).

## 1. What changed from the proposed sequence (and why)

| Original | Revised | Reason |
|---|---|---|
| Subscription/entitlements at Phase 12 | **Skeleton in Phase 4** (plans, features, limit checks), billing UI later | Student creation (Phase 6) already needs `max_students`; retrofitting limit checks into every create path is error-prone. |
| Branding at Phase 13 | **Basic branding in Phase 4**, advanced in V1 | Tenant-aware theming touches app bootstrap; cheap to do early, expensive to retrofit. |
| Audit logging not listed | **Audit infrastructure in Phase 2** | Every write module must emit audit events from its first commit. |
| Security hardening at Phase 15 | Security **built into every phase**; Phase 15 is a *review + test* phase | Isolation and authz can't be bolted on. |
| Performance engineering at Phase 14, testing at 16 | **Baseline load test as soon as the read path exists (Phase 10)**, optimisation only after measurement (Phase 14) | Measure → optimise → re-measure. |
| Student import inside "student management" and marks import later | **Generic import framework built in Phase 6 with students**, reused for marks in Phase 8 | Build once, validate the framework on simpler data first. |
| Testing/CI at the end | **CI from Phase 1; tests in every phase's definition of done** | Brief §31: "testing should not be an afterthought". |
| Thapar demo last | **Thapar seed tenant created in Phase 4 and grown each phase** | Keeps the demo always runnable; final phase is polish + presentation. |

## 2. Phase sequence (dependency-aware)

```
P0 Product & architecture (this docs set)               ✓
P1 Repo, tooling, CI, compose, walking skeleton
P2 Platform kernel: DB conventions, tenancy, RLS, audit, errors, logging
P3 Identity: auth, sessions, RBAC, invites, platform auth
P4 Onboarding, plans & entitlements (skeleton), basic branding, platform console v0, seed tenants
P5 Academic structure
P6 Directory + generic import framework (students)
P7 Examinations & grading engine
P8 Marks entry grid + marks import
P9 Result processing, preview, approval
P10 Publication, read model, student portal  ──► first baseline load test
P11 Marksheet PDFs + verification
P12 Notifications
P13 Analytics (basic) + audit viewer
P14 Performance engineering (measure → optimise → re-measure)
P15 Security review & failure testing
P16 Deployment: demo/production, backups, monitoring, runbooks
P17 Thapar + demo tenants polish, documentation, presentation   ══► MVP COMPLETE
P18+ V1: maker-checker, corrections, custom domains, billing, advanced branding/analytics, API
```

Dependencies (critical path in bold): **P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8 → P9 → P10 → P11** → P14 → P16 → P17. P12 and P13 can run in parallel with P11 if there are two developers; P15 runs alongside P14.

## 3. Milestones (demoable outcomes)

| Milestone | After phase | Demo |
|---|---|---|
| **M1 Walking skeleton** | P1 | `docker compose up` → health check green, CI green, empty app deployed |
| **M2 Secure multi-tenant core** | P3 | Two tenants on two subdomains; login; cross-tenant access blocked (tests + live) |
| **M3 Self-serve SaaS** | P4 | Sign up → tenant created with Free plan, branded portal, platform console lists it |
| **M4 Results pipeline** | P9 | Import students & marks with errors → fix → process → preview → approve |
| **M5 Result day** | P10–P11 | Publish → student sees result → downloads marksheet → QR verifies; first measured load test |
| **M6 MVP** | P17 | Full story on deployed demo with Thapar + Demo School + Demo Coaching, benchmark report, test reports |

## 4. Time estimate (indicative)

Assuming one developer working part-time alongside studies (~15–20 h/week). **These are planning guesses, not commitments**; replace with your measured velocity after P2.

| Phases | Estimate |
|---|---|
| P1–P2 | 2–3 weeks |
| P3–P4 | 3–4 weeks |
| P5–P7 | 3–4 weeks |
| P8–P9 | 3–4 weeks |
| P10–P11 | 3 weeks |
| P12–P13 | 2 weeks |
| P14–P16 | 3–4 weeks |
| P17 | 1–2 weeks |
| **MVP total** | **~20–26 weeks** part-time (roughly halves with two full-time developers) |

If the college deadline is earlier, cut in this order: advanced analytics → notifications by email (keep in-app) → scheduled publication → staff invites (admin-only operation) — **never** cut tenant isolation, audit, tests, or the import validation.

## 5. Beyond MVP
- **V1 (commercial launch):** maker–checker, corrections & versioning UI, custom domains, Razorpay billing, full branding, template library, advanced analytics, data export, support sessions, API keys & webhooks, SSE, audit hash chain.
- **V2:** parents, SMS/WhatsApp, SSO, template editor, signed QR payloads, transcripts, re-evaluation workflow, question-level analytics.
- **Enterprise:** campuses, SAML/SCIM, custom grading plugins, custom workflows, silo deployments, SLA.
