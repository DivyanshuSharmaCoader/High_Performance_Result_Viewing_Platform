# 01 · Product Definition, Problem, Market, Personas, Positioning

> Covers brief sections **A** (product definition), **B** (problem statement), **C** (target market), **D** (personas), **S** (competitive differentiation) and the positioning question (§16).
> Companion docs: [02 Business model](02-business-model.md) · [03 Core workflows](03-core-workflows.md) · [04 Feature scope](04-feature-scope.md)

---

## A. What ScoreCode is

**ScoreCode is a multi-tenant SaaS that takes an institution from "marks in a spreadsheet" to "every student has a verified, branded result in their hands" — safely, auditably, and without the website falling over on result day.**

It is deliberately **not** an ERP. It owns exactly one slice of institutional life:

```
 academic structure ─► examinations ─► marks capture/import ─► validation ─► computation
        ─► review & approval ─► publication ─► student access ─► marksheet + verification
        ─► analytics ─► long-term historical record
```

Everything outside that pipeline (fees, attendance, transport, LMS, HR, admissions…) is **out of scope**. Where an institution already has an ERP, ScoreCode should *integrate* with it (import students, export results), not compete with it.

One-line definition for a presentation:

> *"ScoreCode is examination-and-result infrastructure for educational institutions, delivered as a multi-tenant SaaS. Thapar Institute is one tenant of the platform."*

### What makes it a *platform* rather than a website
| Concern | A "result website" | ScoreCode |
|---|---|---|
| Customers | One institution, hardcoded | Any number of tenants, self-serve onboarding |
| Rules | Grading logic in code | Grading schemes as tenant data (versioned) |
| Look & feel | One theme | Data-driven branding per tenant, custom domains |
| Commercials | None | Plans, entitlements, limits, usage metering |
| Trust | "Admin uploaded it" | Approval workflow, immutable publications, audit trail, QR verification |
| Operations | Single-tenant ops | Platform admin console, per-tenant metrics |

---

## B. Problem statement

### The real problems (in order of how much a buyer will pay to solve them)

1. **Result preparation is manual, error-prone and slow.** Exam cells and class teachers collate marks from many teachers in Excel, compute totals/grades with fragile formulas, and re-type them into report-card templates. One wrong VLOOKUP propagates to hundreds of students. Errors are discovered *after* students see them.
2. **There is no controlled publish step.** Results are emailed as PDFs, pasted into WhatsApp groups, or uploaded as a single PDF of every student's marks (a privacy violation — every student sees everyone's marks). There is no "preview → approve → publish" gate and no record of who changed what.
3. **Corrections are chaotic.** After publication, a re-evaluation changes a mark; there is no versioning, the old PDF still circulates, and nobody can tell which marksheet is authoritative.
4. **Result-day outages.** When an institution *does* run a portal, it is often a shared-hosting PHP site that collapses when thousands of students refresh simultaneously.
5. **Marksheets cannot be verified.** Employers, other institutions and visa processes cannot easily check that a marksheet is genuine. Forgery of marksheets is a known problem in India.
6. **Historical results are hard to retrieve.** Older records live in archived spreadsheets or paper registers.

### Who feels the pain
- **Exam controller / academic coordinator / principal** — owns the deadline and takes the blame for errors. *This is the buyer's champion.*
- **Teachers / faculty** — waste hours on data entry and re-entry.
- **Students & parents** — wait, can't access results on result day, receive mistakes.
- **Management / owners** — reputational damage from errors and leaks; want analytics.

### Problem statement (formal, for the SRS)
> Educational institutions lack an affordable, secure and reliable system to capture, validate, compute, approve, publish, distribute and verify examination results. Existing practices rely on spreadsheets and ad-hoc distribution that cause calculation errors, privacy leaks, unverifiable documents, untraceable corrections and service outages at publication time. ScoreCode provides this capability as a shared multi-tenant service with strict per-institution isolation.

---

## C. Target market — a critical evaluation

You suspected small/mid private institutions or coaching institutes are a better start than universities. **That is mostly right, but for a different reason than performance.** The uncomfortable truth first:

> ⚠️ **The "high-performance" story is a technical differentiator, not the primary buying reason for small customers.** A 400-student school publishing a term result does not have a traffic problem — 400 students is a trivial load for any competent stack. The institutions that genuinely suffer result-day spikes (state universities, boards, large autonomous universities) are the *hardest* to sell to. Small customers buy **"report cards/marksheets become easy and error-free."** Lead with that; keep performance as proof of engineering quality and as the reason ScoreCode scales to big customers later.

### Segment scoring

Scores are qualitative judgements (1 = poor, 5 = excellent) from general knowledge of the Indian education market. **They are hypotheses to validate with ~20 customer discovery calls before committing**, not research findings.

| Segment | Sales cycle | Integration complexity (5 = low) | Willingness to pay | Support burden (5 = low) | Onboarding speed | Pain intensity | **Fit for beachhead** |
|---|---|---|---|---|---|---|---|
| Small private schools (<500) | 4 (owner/principal decides) | 5 | 1–2 (very price-sensitive) | 2 (low IT skill) | 4 | 3 (report cards twice a year) | Medium — free tier funnel |
| **Mid private schools (500–2,500)** | 3 | 4 | 3 | 3 | 3 | 4 (report cards for many classes, CBSE/ICSE formats) | **High** |
| **Coaching institutes** | 5 (owner decides in days) | 5 (simple structure: batches & tests) | 3–4 (paying is normal; results = marketing) | 3 | 5 | 4 (weekly tests, ranks, parent communication) | **High** |
| School chains / trusts | 2 | 3 | 4 | 3 | 2 | 4 | Later (needs multi-campus) |
| Autonomous / private colleges | 2–3 | 2 (credits, SGPA/CGPA, backlogs, re-evaluation) | 3–4 | 3 | 2 | 5 (they publish their own results) | V1 target — **Thapar demo proves fit** |
| Affiliated colleges | 3 | 3 | 2 | 3 | 3 | 2 (final results come from the affiliating university; only internals are local) | Low |
| Universities (state/central) | 1 (tenders, committees, 6–18 months) | 1 (legacy exam systems, ERPs) | 4–5 | 1 | 1 | 5 | **Not V1** — enterprise later |

**Important domain facts that shape this:**
- **School board results (CBSE/ICSE/state boards) are published by the boards themselves.** Schools publish *internal* results: unit tests, half-yearly, annual report cards for non-board classes. So for schools, ScoreCode is a **report-card and internal result platform**, not a board-result portal.
- **Affiliated colleges' final semester results are published by the affiliating university.** Their local need is internal/sessional marks. This makes them a weak beachhead.
- **Autonomous colleges and deemed/private universities (e.g., Thapar) publish their own results** — they have the real spike and complexity (credits, SGPA/CGPA, supplementary exams, grace marks).

### Recommendation
1. **Beachhead (first 10–30 paying customers): coaching institutes and mid-sized private schools without a strong ERP.** Fast decisions, simple structures, clear pain. Pick *one* as the marketing focus at a time; the product supports both because the domain model is generic.
   - Coaching institutes are probably the fastest path to *revenue validation* (owner buys in a meeting; weekly usage makes the product sticky; ranks and test analytics are valued).
   - Mid-sized schools are the larger, steadier market but have a strong objection: *"our ERP already prints report cards."* Target schools whose ERP report cards are poor or who use Excel.
2. **Showcase/credibility segment: autonomous colleges**, demonstrated via the Thapar demo tenant. Do not chase universities for revenue in year one.
3. **Do not target universities, boards, or government tenders** until there is a team, references, SOC2/ISO-style evidence, and an SLA you can actually honour.

### Market risks to state openly
- Indian K-12 software is crowded and **price-anchored by free or bundled ERPs**. ScoreCode must win on *experience and correctness* of the exam/result slice, not on feature count.
- Many schools want *one vendor for everything*. The counter-position is "best-in-class at results, integrates with your ERP" — this resonates with institutions unhappy with their ERP's exam module, not with institutions that have none and want everything.

---

## D. User personas

### 1. Student — "Ananya, 19, B.E. 2nd year" / "Rohan, 14, Class 9"
- **Goal:** see my result the moment it's out; download the marksheet; check my history and where I stand.
- **Context:** opens a link from a notification on a mid-range Android phone on 4G, often at the exact publication minute.
- **Frustrations:** site down at 10:00, forgotten password, PDF of the entire class instead of their own result.
- **Design implication:** mobile-first, < 3 taps to result, tiny JS bundle, session already established before result day, self-service password reset, no knowledge of SaaS concepts.
- **Note on minors:** for schools, the "student" account is often used by a **parent**. V1 treats the student account as the family's account; a separate Parent role is a V2 consideration.

### 2. Faculty / Result operator — "Prof. Mehta" / "Mrs. Kaur, Class teacher"
- **Goal:** enter or upload marks for *my* subjects/sections, fix errors before the deadline, see class statistics.
- **Frustrations:** re-typing marks, not knowing whether the upload worked, formulas breaking.
- **Design implication:** spreadsheet-like grid with keyboard navigation, inline validation, downloadable pre-filled templates, clear "submitted / locked" state, sees **only assigned** papers.

### 3. Institution Admin / Exam controller — "Dr. Sharma, Controller of Examinations" / "Ms. Iyer, Academic coordinator"
- **Goal:** get results out on time without errors; control who can publish; prove what happened if challenged.
- **Frustrations:** chasing teachers for marks, discovering errors after publication, corrections, angry parents.
- **Design implication:** progress dashboard per exam (which papers are complete), import with excellent error reports, preview before publish, approval gate, scheduled publication, correction workflow with versioning, audit log.
- **Sub-persona: Institution Owner** — the payer. Cares about subscription, branding, analytics, student limits. Usually the same account as the admin in small institutions.

### 4. Platform Administrator — "ScoreCode operator (you)"
- **Goal:** onboard and support tenants, see platform health and revenue signals, act on abuse, never accidentally touch a tenant's academic data.
- **Design implication:** separate console on a separate host, separate auth realm, read-mostly views of tenant metadata, **audited** support impersonation (V1, opt-in by tenant) rather than raw DB access.

### Secondary stakeholders (not users in V1)
- **Verifier** (employer, another institution) — uses the public verification page; no account.
- **Parent** — uses the student account in V1.
- **Integrator** (ERP vendor / institution IT) — uses the API on Pro+.

---

## §16. Positioning

### Don't say
"School ERP", "college management system", "all-in-one".

### Say
> **"ScoreCode — results, done right."**
> *Examination and result infrastructure for schools, colleges and coaching institutes: import marks, catch errors before students do, publish with one click, and give every student a branded, verifiable marksheet — on a portal that stays up on result day.*

### Positioning pillars (each must be demonstrably true, not just claimed)
| Pillar | Proof the product must deliver |
|---|---|
| **Correct** | Validation engine catches bad uploads; preview + approval gate; versioned grading schemes; computation is unit/property-tested. |
| **Trustworthy** | Immutable publications, full audit trail, QR-verifiable marksheets, correction history. |
| **Fast & reliable on result day** | Published read model, CDN-served frontend, load-test report with **measured** numbers. |
| **Effortless for admins** | Excel import with field mapping and error report, scheduled publishing, notifications. |
| **Yours** | Institution branding, subdomain/custom domain, institution-controlled publication. |
| **Affordable & focused** | Free tier, per-student pricing, no ERP bloat. |

---

## S. Competitive differentiation

The Indian market has many ERPs and school-management apps that include an exam/report-card module, plus online-test platforms used by coaching institutes. Exact competitor feature sets and prices change frequently; **do a fresh competitor teardown (sign up for free tiers, request demos) before pricing**. Structural differentiators that are hard for ERPs to copy because their exam module is one of fifty:

1. **Import-first workflow.** ERPs typically assume manual entry in their own screens. ScoreCode treats "upload the Excel you already have" as a first-class flow with column mapping, row-level errors and re-upload.
2. **Publication as a controlled, versioned event.** Preview → approve (optionally by a second person) → schedule → publish → correct-with-new-version. ERPs often just flip a visibility flag.
3. **Verification network (potential moat).** Every marksheet carries a QR code to `verify.scorecode.in`. Over time, verifiers learn to trust that domain; each institution on ScoreCode makes the verification service more valuable to the next. *This is the most plausible long-term moat.*
4. **Result-day reliability as an engineering guarantee backed by published, measured load tests** — not marketing numbers.
5. **Narrow scope → better UX and lower price.** Smaller surface area means a cleaner product and lower support load.
6. **Integration-friendly.** API + export so ScoreCode can sit beside an existing ERP.

### Where the moat is *not*
- Branding/custom domains — every SaaS can do this.
- "High concurrency" in itself — cloud makes it cheap for anyone who engineers carefully.
- Analytics — easy to copy unless it becomes longitudinal and comparative (historical cohorts, multi-year trends), which requires years of data on the platform.

**Switching costs that genuinely accumulate:** historical results (years of records), issued verifiable marksheets (they must stay verifiable), configured grading schemes and report-card templates. Design data export carefully so lock-in is earned by quality, not hostage-taking — this matters for trust with institutions and for India's DPDP Act obligations.
