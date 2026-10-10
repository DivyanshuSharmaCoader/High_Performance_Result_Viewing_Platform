# Unit economics and proposed tiers (P18.13)

Accessed **2026-10-10**. Every input names its source; "secondary" inputs are uncertain and should be
checked at the provider before money is committed. Exchange rate assumed **₹88 = $1** (not looked up; a
±10% change moves the dollar-priced lines by ±10%). All prices exclude GST unless stated. **The tiers in §4
are a proposal, not published pricing**: publishing prices as final needs the owner's approval
(gate f) and a chartered accountant's view on GST (§6).

## 1. Cost inputs

| Item | Price | Source | Notes |
|---|---|---|---|
| Server: Hostinger KVM 2 (2 vCPU, 8 GB, 100 GB NVMe, India) | ₹799/month on a 24-month term, renews ₹1,199; monthly term ₹1,299, renews ₹2,099; + 18% GST | [hostinger.com/in/vps-hosting](https://www.hostinger.com/in/vps-hosting) (official) and the owner's cart (2026-10-09) | The one server runs everything (D27) |
| Domain `scorecode.website` | ₹189 first year | the owner's purchase at Spaceship | **Renewal not verified**: modelled at ₹2,000/year |
| Cloudflare (DNS, CDN, TLS) | ₹0 | free plan | |
| File storage: Cloudflare R2 | 10 GB-month, 1 M writes, 10 M reads free; then $0.015/GB-month; egress free | [R2 pricing](https://developers.cloudflare.com/r2/pricing/) (official) | |
| Backups: AWS S3 (Mumbai) | about ₹2.1/GB-month | [secondary](https://precisiontech.in/cloud/amazon-aws-cloud/aws-pricing/aws-pricing-in-mumbai/) | The official page didn't show regional prices to our reader. A few GB: under ₹20/month |
| Email: Brevo | Free: 300 emails/day; Starter $9/month (≈ ₹792) from 5,000 emails/month | secondary ([1](https://www.sendx.io/blog/brevo-pricing-plans-costs-alternatives-2026), [2](https://www.omnisend.com/blog/brevo-pricing/)) | The official page didn't render to our reader. **300/day is less than one 600-student school's result day** |
| Error reports: Sentry | Developer plan free: 5,000 errors/month, one user; Team $26/month | [sentry.io/pricing](https://sentry.io/pricing/) (official) | |
| CI: GitHub Actions (private repository) | 2,000 minutes/month free on GitHub Free; then $0.006/minute | [GitHub docs](https://docs.github.com/en/billing/concepts/product-billing/github-actions) (official) | A full CI run is about 40–60 minutes; batch pushes. With no payment method, Actions stop at the cap (no charge) |
| Card/UPI payments: Razorpay | 2% per transaction + 18% GST on the fee (2.36% in all); no setup or annual fee | [razorpay.com/pricing](https://razorpay.com/pricing/) (official) | A bank transfer against an invoice costs nothing |

**Usage per school (measured, not assumed):** a marksheet PDF is 20.7 KiB (P11.2). A 600-student school
with six exams a year makes about 73 MB of PDFs a year; 30 such schools, 2.1 GB: inside R2's free 10 GB
for about four years. The database for a few schools is tens of MB.

## 2. Fixed cost per year

| Server term | Email | Fixed cost / year | Starter schools to cover it |
|---|---|---|---|
| 24-month, promotional | free (in-app notices; ≤ 300 emails/day) | ₹13,314 | **2** |
| 24-month, promotional | Brevo Starter | ₹22,818 | 3 |
| 24-month, at renewal | free | ₹18,978 | 3 |
| 24-month, at renewal | Brevo Starter | ₹28,482 | **4** |
| monthly | Brevo Starter | ₹29,898 | 4 |
| monthly, at renewal | Brevo Starter | ₹41,226 | **6** |

A Starter school brings ₹7,810 after Razorpay's 2.36% (₹7,999 by bank transfer). Server, domain and email
(where paid) are the whole fixed cost; everything else is inside a free tier at this size.

## 3. Sensitivity: the owner's support time decides the margin

Twenty schools (14 Starter, 5 Growth, 1 Pro): revenue after gateway fees ₹2,50,915 a year; fixed costs
₹28,482 (renewal server, paid email). Support valued at ₹500 an hour:

| Support per school per month | Support cost / year | Margin / year |
|---|---|---|
| none | ₹0 | ₹2,22,433 |
| 15 minutes | ₹30,000 | ₹1,92,433 |
| 30 minutes | ₹60,000 | ₹1,62,433 |
| 1 hour | ₹1,20,000 | ₹1,02,433 |

Other levers, same twenty schools: Starter at −20% needs 5 schools to break even instead of 4; paying by
bank transfer instead of Razorpay saves ₹189 per Starter school; the server's renewal price adds ₹5,664 a
year over the promotional price. **The price matters less than how much hand-holding each school needs**:
self-serve onboarding, the user guides and templates are the margin.

**Capacity is not yet measured on this server.** On a 4-vCPU CI runner the read path served 573–593
requests/s for 1,000 students in 60 s with no errors (P14.3). A 600-student school's result morning is
tens of requests a second. How many schools one KVM 2 carries when several publish the same morning is
P18.11's measurement; until then, plan for a second server (or a bigger plan) before about 50 schools,
as a guess to be replaced by the number.

## 4. Proposed tiers by enrolment band (DRAFT, needs the owner's approval)

Annual, per institution, by active students. These are the catalogue's current plans
(`backend/app/modules/entitlements/catalogue.py`); nothing changes in code until the owner approves.

| Band (active students) | Plan | Price / year (+ GST) | Per student at the top of the band |
|---|---|---|---|
| up to 150 | Free | ₹0 | — |
| 151–600 | Starter | ₹7,999 | ₹13.3 |
| 601–2,000 | Growth | ₹19,999 | ₹10.0 |
| 2,001–5,000 | Pro | ₹44,999 | ₹9.0 |
| above 5,000 | Enterprise | quote | — |

For comparison: eSchoolApp, a full ERP, publishes ₹50 per student per year; Fedena starts at ₹50,000 a
year ([competitors](competitors.md)).

**Fair use (all paid plans), written so a school can predict its bill:**
- Publications: unlimited. Exams: unlimited. Corrections: free (they don't use a publication).
- Storage as in the catalogue (5, 20, 100 GB): marksheets are about 21 KB each.
- Email notices: **up to 12 per student per year** (every exam, plus corrections); beyond that,
  notices stay in the app (the bell) unless the school asks for more. In-app notices are unlimited.
- One institution per subscription (no reselling); fair use of the API on Pro (the per-session limit,
  300 requests a minute).
- **No lock-in:** the data export (P18.5) is on every plan, including Free. Closing an account gives 30
  days to export and change one's mind before the data is deleted (P18.14, docs/legal).

**Trials:** 30 days of Pro features at up to 1,000 students, once per institution (as built).

## 5. What would change these numbers

- Email: if most schools want email for every student, Brevo's next tier (or Amazon SES) is the first
  cost that grows with schools; the in-app bell is free.
- A second server for resilience doubles the server line (≈ ₹11,300–17,000/year).
- Card-heavy collection adds 2.36%; annual invoices paid by bank transfer add nothing.

## 6. Questions for a chartered accountant (not decided here)

1. GST registration: needed from the first sale (inter-state supply of services to schools in other
   states) or only above the turnover threshold? Can schools claim input credit?
2. Invoicing: GST invoice format for annual SaaS subscriptions; place of supply for schools in other
   states.
3. TDS on payments from schools (some deduct tax at source on software); how to account for it.
