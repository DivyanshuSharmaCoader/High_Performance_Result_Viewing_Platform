# 04 · Feature Breakdown — MVP, V1, V2, Enterprise

> Covers brief section **F** and §34 (MVP). Each feature maps to modules in [08 Backend](08-backend-architecture.md) and to phases in the [Implementation plan](IMPLEMENTATION_PLAN.md).

**Scoping rule:** a feature is in the MVP only if the end-to-end story *"institution signs up → publishes a result → student downloads a verifiable marksheet"* breaks without it, or if it is a security/tenancy foundation that is expensive to retrofit.

---

## MVP — "one institution can publish a real result, safely"

| Area | Feature | Notes |
|---|---|---|
| **Tenancy** | Tenant creation, subdomain routing, tenant context, RLS isolation | Foundation — never retrofitted |
| **Identity** | Email+password login (Argon2id), sessions (HttpOnly cookie), logout, password reset, staff invites, student activation codes | |
| **RBAC** | Fixed roles: `institution_owner`, `institution_admin`, `faculty`, `student`; platform realm: `platform_admin` | Permissions in code |
| **Onboarding** | Self-serve sign-up, email verification, setup checklist | |
| **Entitlements** | Plans + features + limits tables, `max_students`, `max_staff`, feature flags checked through one service; Free + one paid plan seeded | Billing is manual |
| **Branding (basic)** | Institution name, logo, primary colour | Data-driven theme |
| **Academic structure** | Sessions/terms, programs, cohorts, courses (departments optional) | CRUD + CSV |
| **Directory** | Students (CRUD + import), staff, faculty→paper assignment | |
| **Examinations** | Exams, papers with components, cohorts | |
| **Grading** | Percentage-band grading scheme + marks-only scheme; versioned | Strategy pattern from day 1 |
| **Marks entry** | Grid entry with validation and optimistic locking | |
| **Import** | CSV/XLSX marks import: upload, map, validate, error report, commit | Core differentiator |
| **Processing** | Compute results, preview, anomaly list | |
| **Approval & publish** | Single-step approve, publish now, withdraw | Immutable snapshots |
| **Student portal** | Dashboard, result detail, history, profile | Mobile-first |
| **Marksheet** | Default PDF template with QR, pre-rendered on approval | |
| **Verification** | Public verify page (masked) | |
| **Notifications** | In-app + email on publish | |
| **Analytics (basic)** | Per-exam stats snapshot | |
| **Audit** | Append-only audit log for all writes; admin audit viewer (basic) | Foundation |
| **Platform admin** | Tenants list, tenant detail, suspend, change plan, health page | |
| **Ops** | Docker compose, CI, health checks, structured logs, metrics endpoint, backups, Sentry | |
| **Quality** | Unit, integration, tenant-isolation, E2E smoke, first load test with measured report | |

### Explicitly NOT in the MVP
Custom domains, online payment checkout, SMS/WhatsApp, SSE/WebSockets, two-step approval, scheduled publication *(see note)*, SGPA/CGPA *(see note)*, ranks, parent role, API keys, SSO, multiple campuses, custom templates, advanced analytics, mobile app.

> **Note — two items to pull into MVP if the Thapar demo needs them:** *credit-based SGPA grading* (Thapar is a credit system) and *scheduled publication* (the "10:00 AM publish" demo). Both are small given the strategy-pattern grading engine and the job queue. Recommendation: **include both in MVP** because the demo story depends on them — they are listed in the plan as MVP items.

---

## V1 — "commercially launchable"

- Two-step (maker–checker) approval
- Scheduled publication (if not already in MVP)
- Correction workflow with versioned re-publication and diff view
- Credit-based grading (SGPA/CGPA), grace marks rules, supplementary exams
- Ranks (coaching), percentile
- Branding: full theme tokens, login page content, favicon, footer; "Powered by ScoreCode" removal on Pro
- Custom domains (Pro) with automatic TLS
- Template library for marksheets (3–5 layouts) + logo/signature images
- Advanced analytics (trends, subject comparison)
- Notification templates per tenant; email digests
- Billing: Razorpay checkout, GST invoices, plan self-upgrade
- Data export (full tenant ZIP)
- Support sessions (audited impersonation) for platform admin
- API keys + read-only REST API, webhooks on `publication.published`
- Department-level admins (scoped admin role)
- SSE for import/processing progress (replaces polling if measurements show polling cost)
- Audit log hash chain (tamper evidence) and export

## V2 — "growth"

- Parent accounts linked to students
- SMS / WhatsApp notifications (pass-through billing, DLT onboarding)
- Google Workspace / Microsoft SSO for staff and students
- Custom marksheet template editor (constrained HTML/CSS)
- Signed verification payloads (Ed25519) for offline/QR-only verification
- Transcript generation (multi-term consolidated)
- Re-evaluation request workflow (student-initiated, fee optional)
- Question-level marks & item analysis (coaching)
- OMR/scanner output import adapters
- Integrations: common ERP export formats, DigiLocker/Academic Bank of Credits investigation (only if customers ask and regulatory path is clear)
- Native-feeling PWA with offline result cache

## Enterprise (contract-driven, built only when paid for)

- Multiple campuses with campus-scoped admins
- SAML SSO, SCIM provisioning
- Custom grading algorithms (relative grading etc.) as plugins
- Custom workflows (multi-level approvals, moderation boards)
- Bulk historical migration tooling + service
- Dedicated deployment (separate stack, same code) and data residency guarantees
- SLA, priority support, audit exports to SIEM
- Custom roles/permissions (DB-defined)

---

## What should be removed or pushed back from the original idea

| Item | Recommendation | Reason |
|---|---|---|
| WebSockets for students | **Remove** | Students don't need live push; holding thousands of sockets during the spike costs memory and adds failure modes for zero user value. Notifications + a refresh are enough. |
| "System monitoring" page in the tenant/student UI (old frontend) | **Move** to platform admin only | Tenants don't need infrastructure graphs; it leaks platform internals. |
| Real-time "statistics" for students | **Replace** with static per-publication stats snapshot | Computed once at publish, cached forever. |
| Fully customisable everything | **Constrain** to tokens/templates | Unlimited customisation = unbounded support. |
| Generic `permissions` table in V1 | **Defer** | Fixed roles with code-defined permission sets are simpler and safer; DB-defined custom roles are an Enterprise feature. |
| Microservices/Kafka/K8s | **Remove** | No requirement justifies them at this stage (see [17 Tech stack](17-tech-stack.md)). |
| Monthly plans for everyone | **Annual-first** | See [02 Business model](02-business-model.md). |
