# Data processing agreement (institution ↔ ScoreCode)

> **DRAFT — requires legal review before use.** Not in force. `[Bracketed]` items are for the parties.

Between **[Institution]** (the *Data Fiduciary*) and **[ScoreCode's legal name]** (the *Data Processor*),
under the Digital Personal Data Protection Act, 2023 and the DPDP Rules, 2025 (when in force).

1. **Subject and purpose.** The Processor processes the personal data the Institution puts into ScoreCode
   (students, guardians, staff, marks and results) only to provide the ScoreCode service as the Institution
   instructs through the product's settings and actions, and for nothing else.
2. **The Institution's duties.** It has a lawful basis for the data, gives students and parents the notice
   the law requires (template in Annex A), obtains verifiable parental consent where required, and keeps
   its administrators' accounts secure.
3. **Confidentiality.** People at the Processor with access are bound to confidentiality and access the
   data only to run, support or secure the service; support access is logged in the platform audit log.
4. **Security (rule 6).** At least: encryption in transit; hashed passwords and encrypted second factors;
   separation of each institution's data enforced in the database; access control by role; logs of
   access and changes kept one year; encrypted backups, restore tested; vulnerability scanning in every
   release. Details: ScoreCode's threat model, available on request.
5. **Sub-processors.** Listed in Annex B. The Processor tells the Institution [30] days before adding or
   replacing one; the Institution may object and end the agreement.
6. **Breaches.** The Processor tells the Institution's owner **without undue delay and within 24 hours**
   of becoming aware of a breach affecting its data, with what is known (nature, extent, time, likely
   impact, measures), and helps the Institution notify the Board and affected people (rule 7) and CERT-In
   where required.
7. **Rights of data principals.** The Processor gives the Institution the means to answer requests: each
   student's access to their own results; correction of details and results (corrections); a full export
   of the Institution's data; and closure with erasure of the account. It answers the Institution's
   requests for help within [7] days.
8. **Retention and deletion.** Records of processing are kept one year (rule 8(3)). At the end of the
   agreement, or when the Institution closes its account, the Processor erases the Institution's data 30
   days after the request, except: billing records the law requires; a record that the Institution
   existed; hashed records preventing repeated free trials; encrypted backups, which expire within
   [35] days. The Processor confirms erasure in writing.
9. **Location.** Data is stored in India ([Hostinger Mumbai; R2 region; S3 Mumbai]). Error reports (with
   personal data removed) and email delivery may be processed outside India by the sub-processors listed.
10. **Audit.** The Processor answers reasonable written questions about its security and provides its
    test and scan reports once a year on request.
11. **Liability.** [Counsel to align with the terms of service.]

**Annex A — notice to students and parents (template for the Institution).** [To draft: what is processed,
why, who sees it, how long, rights, contact, complaints to the Board.]

**Annex B — sub-processors.** Hostinger (hosting, India); Cloudflare (network, file storage); Amazon Web
Services (encrypted backups, Mumbai); Brevo (email delivery); Sentry (error reports, scrubbed);
GitHub (software build and release; no customer data).
