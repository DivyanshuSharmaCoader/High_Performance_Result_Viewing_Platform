# 02 · SaaS Business Model, Pricing and Viability

> Covers brief sections **G** (SaaS business model), §12–15 (plans, pricing, revenue model, viability in India).
> Technical design of plans/entitlements: [12 Entitlements](12-entitlements.md). Infrastructure economics: [16 Cost model](16-cost-model.md).

> **All prices below are proposals to test with customers, not market data.** Validate with discovery calls and a competitor teardown before publishing a price page.

---

## 1. Critique of the proposed tiers

| Proposal | Verdict | Why |
|---|---|---|
| Free up to 200 students | **Keep, but shrink to 150 and cap publications**, not features. | A 200-student coaching centre or small school could run on free forever. Free should let them *experience the full publish flow* but nudge upgrade through scale (students, history, exams per year). |
| PDF marksheets only on Basic | **Change: include basic ScoreCode-branded PDF + QR verification on Free.** | Every free marksheet that a parent shares or a verifier scans is marketing for `scorecode.in`. Removing it from free kills the best growth loop. Paid tiers get *institution-branded* templates without ScoreCode branding. |
| Bulk import only on Basic | **Change: CSV/Excel import on all tiers.** | Import is the core value proposition. Locking it makes the free tier feel broken and produces "this product is useless" word of mouth. Gate *volume* (rows/students), not the workflow. |
| Pro: custom domain + API + multi-department | **Keep, but treat multiple departments as Growth-tier** | Any school with >1 wing or any college has departments. Multiple **campuses** is the real enterprise signal. |
| Enterprise: SSO, dedicated deployment | **Keep, priced as custom contracts with setup fees.** | Dedicated deployments are expensive to operate; price must cover ops time, not just infra. |
| Monthly billing | **Annual-first.** Offer monthly only on card for Starter, at a premium. | Indian institutions budget per academic year and frequently pay by bank transfer against a GST invoice. Recurring card/UPI mandates are governed by RBI e-mandate rules (customer authentication, caps) which add friction to monthly auto-debit. Results are seasonal — monthly plans invite "subscribe in March, cancel in April" churn. |

---

## 2. Recommended plans (V1 proposal)

Pricing unit: **per institution per academic year, banded by active students**, with transparent overage. Prices are exclusive of 18% GST (SaaS is GST-taxable in India).

| | **Free** | **Starter** | **Growth** | **Pro** | **Enterprise** |
|---|---|---|---|---|---|
| Indicative price / year | ₹0 | ₹7,999 | ₹19,999 | ₹44,999 | Custom (from ~₹1.5 L + setup) |
| Active students included | 150 | 600 | 2,000 | 5,000 | Custom |
| Effective ₹/student/year at cap | — | ~₹13 | ~₹10 | ~₹9 | Negotiated |
| Overage | Hard cap | ₹15/student | ₹12/student | ₹10/student | Contract |
| Staff accounts (admin + faculty) | 5 | 15 | 60 | 200 | Custom |
| Admin seats within staff | 2 | 2 | 5 | 15 | Custom |
| Published exams / year | 6 | Unlimited | Unlimited | Unlimited | Unlimited |
| Online history retained | 1 academic year | 3 years | 7 years | Unlimited | Unlimited + migration |
| CSV/Excel import | ✓ | ✓ | ✓ | ✓ | ✓ |
| PDF marksheet + QR verification | ScoreCode-branded | Logo on template | Branded templates (choose from library) | Custom template (1 included) | Fully custom formats |
| Branding | ScoreCode theme, logo | Logo + primary colour | Full theme tokens, login page text | + remove "Powered by ScoreCode" | White-label |
| Domain | `slug.scorecode.in` | subdomain | subdomain | **Custom domain** | Custom domain(s) |
| Departments | 1 | 1 | Multiple | Multiple | Multiple |
| Campuses | 1 | 1 | 1 | 1 | Multiple |
| Notifications | In-app + email (capped) | Email | Email + scheduled | + SMS/WhatsApp add-on (pass-through cost) | Custom channels |
| Approval workflow (maker–checker) | Single-step | Single-step | Two-step | Configurable | Custom workflows |
| Analytics | Basic exam stats | Basic | Advanced (trends, subject/teacher, cohort) | Advanced + export | Custom reports |
| API access | — | — | Read-only export | Full API + webhooks | Custom APIs/integrations |
| SSO (Google Workspace/Microsoft/SAML) | — | — | — | Google/Microsoft OIDC | SAML/custom |
| Audit log access (UI) | 30 days | 1 year | Full | Full + export | Full + SIEM export |
| Support | Docs, community | Email (2 business days) | Email + chat | Priority, onboarding call | SLA, named contact |

**Why "active students" as the meter:** it is what the customer understands, it correlates with value and with cost (storage, PDFs, notifications), and it's easy to count. *Active* = not archived/graduated, so historical data does not penalise the customer.

**Why these price points (logic, not data):**
- Small Indian schools and coaching institutes commonly evaluate software at a per-student-per-year figure in the tens of rupees. ScoreCode covers *one slice* of what an ERP covers, so it must sit at the low end of that range per student — hence ~₹9–13/student/year.
- Growth and Pro bands are where the money is: a 1,500-student school paying ₹20k/year is a meaningful but approvable expense for a principal; Pro targets colleges and large coaching chains.
- Enterprise is priced on *effort* (integrations, custom formats, SLA), not on students.

**Validate before launch:** run 15–20 discovery calls; ask "what did you pay for your last software purchase of this kind?" and "who approves it?" rather than "would you pay ₹X?".

---

### 2.1 Free tier and trial against the market (researched 2026-10-08)

We read the vendors' own pricing pages on 2026-10-08. Prices and limits change often, so treat this as a dated snapshot, not a claim about today.

| Vendor | Free tier (as published) | Trial of paid plans |
|---|---|---|
| ScholaBook (school ERP, India) | Free forever, **up to 100 students** | not stated |
| OurSchoolSoftware (school ERP) | Free forever, **up to 100 students**, single campus | 3 days |
| Zoho Classes | Free for teachers, **up to 100 students** | length not stated |
| ReportCards.ai (report cards) | Free: 3 subjects, 4 classes, 3 report cards per class | 7 days |
| ThinkWave (gradebook/SIS) | Free gradebook that doesn't expire (no cap stated on the page) | 30 days |
| Fedena (school ERP) | none | 14 days |
| Classe365 (SIS) | none | 15 days |
| iVake (education ERP) | none | 30 days, no card |
| eSkooly, OpenEduCat Community | Advertised as free with no limits (eSkooly's page refused automated access; OpenEduCat is self-hosted open source) | — |

Sources: [ScholaBook](https://scholabook.com/pricing), [OurSchoolSoftware](https://ourschoolsoftware.com/), [Zoho Classes](https://www.zoho.com/classes/pricing.html), [ReportCards.ai](https://www.reportcards.ai/), [ThinkWave](https://www.thinkwave.com/), [Fedena](https://fedena.com/pricing-and-plans), [Classe365](https://www.classe365.com/pricing), [iVake](https://www.ivake.com/erp-software-published-pricing).

**What we chose.** Free stays at **150 students**: 50% more than the 100-student cap that every capped hosted free tier we found uses. It also gets **5 staff, 2 admin seats and 6 exam publications a year**, so a school can publish two unit tests, mid-terms and finals each year. Every workflow is included; growth is gated by scale. We don't try to beat "unlimited free". Those offers are self-hosted open source or ad-supported, and a hosted results service that has to stay up on result day can't fund that.

The **trial is 30 days of Pro** (docs/12 §6). That matches the longest trials we found, and it needs no card. It is capped at 1,000 students. Custom domain and API access are held back during an unpaid month: the first needs DNS work and certificates, and the second invites bulk scraping. Each institution gets one trial, ever.

## 3. Revenue streams — what exists in V1

| Stream | V1? | Notes |
|---|---|---|
| Annual subscriptions (banded) | **Yes** | Core revenue. |
| Student-band upgrades / overage | **Yes** | Automatic via entitlement limits; overage invoiced at renewal or prompts upgrade. |
| Onboarding/setup fee | **Yes, optional** | Flat fee (e.g. ₹5k–25k) for "we configure your structure and import your data". Waived for Starter self-serve. |
| Historical data migration | **Yes, quoted** | Per-project; high value for colleges. Requires a migration tool you'll build anyway (the importer). |
| Custom marksheet template | **Yes, quoted** | Per-template fee. Templates are HTML/CSS so the work is bounded. |
| SMS/WhatsApp notifications | Add-on (V1.x) | **Pass-through cost + margin.** Never bundle unlimited SMS — costs scale with usage. India requires DLT registration for commercial SMS, which is onboarding friction. |
| Custom domain | Included in Pro | Do not sell separately in V1 — adds pricing complexity for little revenue. |
| Premium support/SLA | Enterprise only | Don't sell an SLA you can't staff. |
| Dedicated infrastructure | Enterprise only (V2+) | Same codebase deployed in a separate stack; charge infra cost × 2–3 + ops fee. |
| API/integrations | Pro (standard API); Enterprise (custom) | |

**Keep V1 commercially simple:** 4 public plans + Enterprise, annual billing, one optional setup fee, quoted custom work. Nothing else.

---

## 4. Customisation as revenue (not as scope creep)

Rule: **configuration is in the plan; customisation is a paid project; forks are never allowed.**

| Type | Example | How it's delivered | Charged? |
|---|---|---|---|
| Configuration | Grading bands, logo, colours, exam components | Tenant settings UI | Included |
| Template customisation | Institution's own marksheet layout | New HTML/CSS template stored as tenant data | Per template |
| Extension point | A new grading algorithm (e.g. relative grading) | New `GradingStrategy` plugin in the main codebase, enabled via entitlement | Project fee; may become a product feature for everyone |
| Integration | Push results to institution's ERP | Webhooks/API + adapter | Project fee + annual maintenance |
| Fork | "Change the code just for us" | **Never.** One codebase, everything else is config, data or plugin. | — |

---

## 5. Is this a viable business in India? (critical view)

### Unit economics sketch (illustrative, to be replaced by real numbers)
- Infra for the first ~50 small tenants fits on a small production footprint (see [16 Cost model](16-cost-model.md)); marginal infra cost per small tenant is low (storage, PDFs, email).
- **The dominant cost is not infrastructure — it's sales and support time.** A ₹8k/year customer that needs three hours of hand-holding per term is unprofitable.
- Therefore viability depends on: **self-serve onboarding quality**, **import UX** (fewer support tickets), and **documentation**.

### Reasons it *can* work
- Real, recurring pain every term; clear buyer (exam controller/principal).
- Narrow product → small team can build it well.
- Low marginal cost; free tier can drive organic adoption via shared marksheets and verification.
- Upsell path is natural (students grow, branding, domains).

### Reasons it might *not* work
- Price anchoring to "free with our ERP".
- Seasonal usage (2–4 peaks/year for schools) → low perceived value between peaks → churn risk. *Mitigation:* coaching institutes (weekly tests), historical access, analytics.
- Low willingness to pay in small schools; long collection cycles.
- Trust barrier: institutions are wary of putting student data with a new vendor. *Mitigation:* security page, DPDP-aligned data processing agreement, Indian data residency, audit logs, export anytime.

### Verdict
**Viable as a focused, low-cost SaaS if — and only if — onboarding and import are self-serve and excellent.** It is unlikely to be viable as a high-touch, sales-led product at these price points. Universities can make it lucrative later, but only after the product, team and references exist.

### Go-to-market for the first 12 months (suggested)
1. Ship MVP; onboard Thapar demo + 2–3 friendly institutions (free) as design partners.
2. Target coaching institutes and mid-size schools in one city/region; founder-led sales.
3. Publish a public, honest load-test report and a security page — credibility for an unknown brand.
4. Track: activation (first publication within 14 days), paid conversion, support hours per tenant, NPS from admins.
