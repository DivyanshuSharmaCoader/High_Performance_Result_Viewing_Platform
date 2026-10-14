# Legal readiness matrix (P18.14)

> **Not legal advice, and not a statement of compliance.** This records, for each law that may apply to
> ScoreCode, where it comes from, whether it seems to apply, what the product does today, the evidence,
> and the questions for an Indian lawyer (and a chartered accountant for tax). Sources accessed
> **2026-10-10/11**; "official" means the government text itself; "secondary" means a law firm's or
> portal's summary, to be checked against the text.

**ScoreCode's likely role.** Under the DPDP Act a school deciding why and how its students' data is
processed is the **Data Fiduciary**; ScoreCode, processing on the school's behalf, is a **Data Processor**
(s.2(k)). ScoreCode is the Fiduciary for its own customers' staff accounts and for its website visitors.
*Question L1:* confirm this split, and what changes when ScoreCode also sends students emails directly.

## 1. Digital Personal Data Protection Act, 2023 and DPDP Rules, 2025

**Commencement** (Rules, rule 1, official [MeitY text](https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf);
[PIB factsheet](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf)):
Rules 1, 2 and 17–21 (the Data Protection Board) from publication (G.S.R. 846(E), 13–14 November
2025); rule 4 (consent managers) one year after; **rules 3, 5–16, 22 and 23 (notice, consent, security,
breach, retention, children, rights) eighteen months after: about 13–14 May 2027.**

| Requirement | Source | Applies to ScoreCode? | Status in the product | Evidence | Open questions |
|---|---|---|---|---|---|
| Notice before consent; consent clear and withdrawable (s.5–6; rule 3) | Act; Rules r.3 (official) | The school (fiduciary) gives notice to students and parents; ScoreCode gives notice to staff and visitors | DRAFT [privacy notice](privacy-notice.md); a school's notice template is in the [DPA](school-dpa.md) annex | — | L2: does a school need consent for exam results at all, or is it a "legitimate use" (s.7) for education? |
| **Children's data: verifiable parental consent; no tracking or behavioural monitoring; no targeted ads** (s.9; rule 10) | Act s.9; Rules r.10, r.12, Fourth Schedule (official) | Most students are under 18 | No advertising, no profiling, no tracking. Students are activated by a per-student code the school issues (the school's own records verify the parent, r.10(1)(a)) | ADR 0006; docs/10 §2 | **L3:** Fourth Schedule Part A item 3 exempts an educational institution only for "tracking and behavioural monitoring" for its educational activities or children's safety. Is processing and publishing exam results covered, does a processor benefit from it, or must the school obtain verifiable consent? |
| Reasonable security safeguards (s.8(5); rule 6: encryption, access control, logs, backups, contracts with processors) | Act; Rules r.6 (official) | Yes, as processor through the DPA, and directly for its own data | Encryption in transit; TOTP secrets and backups encrypted; RLS between schools; access logs; encrypted backups with tested restore | [threat model](../security/threat-model.md), restore drill | L4: is encryption at rest of the database disk (provider-level) needed in addition? |
| **Breach: tell each affected person without delay; tell the Board without delay and in detail within 72 hours** (s.8(6); rule 7) | Rules r.7 (official) | The fiduciary (the school) notifies; the processor must tell the school promptly (DPA) | Runbook for incidents; DPA commits to tell the school within 24 hours of becoming aware | [security-incident.md](../runbooks/security-incident.md), [DPA](school-dpa.md) §6 | L5: what ScoreCode must do itself if a school can't be reached |
| **Retention: keep personal data, traffic data and logs of processing for at least one year** (rule 8(3)); erase when the purpose is served (s.8(7)) | Rules r.8 (official) | Yes | Records of processing kept a year (migration 0020); logs archived a year on the server in India; raw import copies deleted after 30 days; erasure of a whole institution on request after 30 days (migration 0021) | docs/10 §12, `test_retention.py`, `test_closure.py` | **L6:** does the one-year minimum apply to a processor's own logs after a school has asked for erasure? Which records must a school keep for longer (school-education rules, board bye-laws)? |
| Rights: access, correction, erasure, grievance, nominee; answer within 90 days (s.11–14; rule 14) | Act; Rules r.14 (official); PIB | The school answers; ScoreCode helps | Access: student portal + export; correction: corrections workflow; whole-institution erasure built; **per-student erasure not self-service** (published results are immutable) | [offboarding runbook](../runbooks/tenant-offboarding.md) | **L7:** may a school refuse erasure of results it must keep by law? If not, ScoreCode needs per-student erasure (V1) |
| Contact for questions (rule 9); grievance redressal (s.13) | Rules r.9 (official) | Yes, for ScoreCode's own role | DRAFT [grievance page](grievance.md) | — | — |
| Cross-border transfer (s.16) | Act | Data stays in India (VPS in Mumbai; R2 and S3 regions to be confirmed); Sentry and Brevo are outside India | Sentry receives errors scrubbed of personal data; Brevo receives the recipient's email address and the message | `test_sentry_scrub.py` | L8: is sending email addresses to a foreign email provider a transfer needing anything beyond the DPA? |
| Significant Data Fiduciary duties (s.10; rule 13) | Act; Rules | Not unless notified as one | — | — | — |
| Penalties up to ₹250 crore (Schedule; children and breach up to ₹200 crore) | Act; PIB | — | — | — | — |

## 2. Information Technology Act, 2000 and rules

| Requirement | Source | Applies? | Status | Open questions |
|---|---|---|---|---|
| Reasonable security practices for sensitive personal data, e.g. passwords (s.43A; SPDI Rules 2011) | IT Act s.43A; [SPDI Rules 2011](https://www.meity.gov.in/writereaddata/files/GSR313E_10511%281%29_0.pdf) (official link not re-checked) | Passwords are "sensitive personal data"; s.43A is replaced by the DPDP Act when its provisions commence (DPDP s.44) | Passwords hashed with Argon2id; never stored or logged in clear | L9: until May 2027, does ScoreCode need an SPDI-style privacy policy and an ISO 27001-like documented programme? |
| Intermediary due diligence: publish rules, privacy policy, grievance officer, act on complaints (s.79; Intermediary Guidelines 2021) | IT Act s.79; [Rules 2021](https://www.meity.gov.in/writereaddata/files/Intermediary_Guidelines_and_Digital_Media_Ethics_Code_Rules-2021.pdf) (not re-checked) | Possibly: ScoreCode stores and shows content on schools' behalf | DRAFT [acceptable use](acceptable-use.md) and [grievance](grievance.md) | L10: is a results platform an intermediary? If so, grievance officer timelines (24 hours to acknowledge, 15 days to resolve) |
| **CERT-In directions (28 April 2022, in force 27 June 2022): report incidents within 6 hours; keep logs of ICT systems 180 days within India; synchronise clocks with NIC or NPL NTP** | [CERT-In directions](https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf) (official) | "Service providers, intermediaries, data centres, body corporate and Government organisations": ScoreCode once incorporated; possibly before | Logs archived 365 days on the server in Mumbai (`scorecode-ctl archive-logs`); NTP set to NIC and NPL servers (`bootstrap.sh`); incident runbook to report to incident@cert-in.org.in within 6 hours | release rehearsal checks the timer and NTP file | L11: does the directions' "body corporate" include an individual operating before incorporation? |

## 3. Consumer protection

| Requirement | Source | Applies? | Status | Open questions |
|---|---|---|---|---|
| Consumer Protection Act 2019; E-Commerce Rules 2020: seller details, grievance officer, refund and cancellation policy, no dark patterns | [Act](https://PRSINDIA.org/files/bills_acts/bills_parliament/2021/Consumer%20Protection%20Act%202019.pdf) (secondary host); [commentary](https://trilegal.com/knowledge-repository/consumer-protection-e-commerce-rules-2020/) (secondary) | Unclear for B2B: schools buy for their operations ("commercial purpose" exclusion), but courts read it narrowly (NIC v. Harsolia Motors, 2023, per secondary sources); small private tutors may be consumers | DRAFT [refund and cancellation](refund-and-cancellation.md); pricing transparent, annual, cancel any time, no auto-renewal surprise | L12: do the E-Commerce Rules apply to selling SaaS to schools and coaching centres? |
| Guidelines for prevention of dark patterns (2023) | CCPA guidelines (not re-checked) | as above | No pre-ticked boxes, no confirm-shaming, closure in the product with no fee | — |

## 4. Tax: GST and invoicing

| Requirement | Source | Applies? | Status | Open questions (for a CA) |
|---|---|---|---|---|
| Registration above ₹20 lakh aggregate turnover (CGST s.22); inter-state supply of services exempt from compulsory registration below it (Notification 10/2017-Integrated Tax, as amended 3/2019) | CGST Act; [notification summary](https://gstzen.in/a/integrated-tax-notification-102017-seeks-to-exempt-persons-making-inter-state-supplies-of-taxable-services-from-registration-under-section-232.html) (secondary) | Yes, once selling | Not registered yet (no sales) | T1: register voluntarily from the first sale so schools can claim input credit? T2: place of supply for schools in other states |
| Tax invoice contents (CGST Rules, rule 46) | CGST Rules (not re-checked) | Yes, when registered | Billing is manual today (D17); no invoices generated by the product | T3: invoice format for annual subscriptions paid in advance; credit notes on refunds |
| Books and records kept 72 months (CGST s.36) | CGST Act (not re-checked) | Yes | `tenant_subscriptions` are kept after an institution's erasure | — |
| TDS deducted by some schools on software payments | Income-tax Act (not re-checked) | Possibly | — | T4 |

## 5. Children, schools and education regulation

| Item | Status | Open questions |
|---|---|---|
| School boards' and state rules on keeping academic records (CBSE affiliation bye-laws, state school-education rules) | Not researched | L13: how long must a school keep marks and results, and can a processor delete them on the school's instruction before that? |
| Publishing results with names (merit lists) | ScoreCode shows each student only their own result; class statistics are aggregates | L14: is a "topper list" lawful for children under DPDP s.9? (Not a feature.) |

## 6. What is DRAFT and needs review before a paid launch (gate f)
[Terms of service](terms-of-service.md) · [Privacy notice](privacy-notice.md) ·
[School data processing agreement](school-dpa.md) · [Refund and cancellation](refund-and-cancellation.md) ·
[Acceptable use](acceptable-use.md) · [Grievance contact](grievance.md). Each is marked DRAFT; none is
published in the product until the owner approves it after legal review.
