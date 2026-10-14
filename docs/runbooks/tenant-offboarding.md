# Tenant offboarding: an institution leaves, or asks for its data

## Export (self-service, any plan)
The owner: **Settings → Your data → Export everything** (P18.5). A ZIP of CSV files with every record,
ready in a minute or two, kept seven days, each download audited. No ticket needed. If an owner can't sign
in (left the institution), transfer ownership first (another administrator, platform console) or, on the
institution's written instruction, sign in as support and export on their behalf.

## Closing the account (P18.14)
Two approvals, then the worker erases:
1. **The owner asks:** Settings → Your data → *Close the account…* (password again, a reason, and the
   institution's address typed out). Every administrator is emailed. **Nothing changes for 30 days:**
   everyone keeps working, the data can be exported, and the owner can *Cancel closure*.
2. **ScoreCode staff approve, after the 30 days:** platform console → the institution → *Erase
   permanently…* (address typed out, reason). Before the 30 days pass, the button doesn't appear and the
   API refuses. The portal goes offline at once and everyone is signed out.
3. **The worker erases**, within minutes (its maintenance runs at start and every 6 hours; restart the
   worker to run it now): the stored files under `tenants/<id>/`, then every row of the institution in
   one transaction (`ops_erase_tenant`, which checks both approvals and the address again). The platform
   audit log records `tenant.erasure_approved` and `tenant.erased` with row and file counts.

**Kept after erasure, and why:** a tombstone row in `tenants` (status `closed`; the name and address
only); `tenant_subscriptions` (financial records, for tax law); `tenant_trials` and the hashed
`trial_claims` (so the same institution can't take a second free trial; no names or contacts); the
platform audit log. Verification codes stop resolving ("can't be checked here").

**Backups** still contain the data until they expire (nightly encrypted dumps; the backup bucket's
lifecycle rule). Say so in the confirmation to the institution, with the date the last backup holding the
data expires.

**Confirm in writing** to the owner's address once `tenant.erased` is in the platform audit log.

## Suspension (not closing)
Platform console → institution → Suspend (reason, address typed out): every session revoked, the portal
shows "temporarily unavailable", nothing deleted; Reactivate restores everything.

## One student's data (a request under the DPDP Act)
The institution is the data fiduciary and decides. ScoreCode supports it as follows, today:
- **Access:** the student sees every published result in the portal; the institution's export has the rest.
- **Correction:** administrators edit the student's details; results are corrected with a correction
  (Results → Correct results…), which publishes a new version.
- **Erasure:** not self-service yet. Published results are immutable by design, and schools usually have
  to keep academic records (open question for a lawyer: docs/legal/readiness-matrix.md). On the
  institution's written instruction, an operator archives the student (Students → archive) and records the
  request; a full per-student erasure is a V1 item.
