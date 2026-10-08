# Tenant offboarding: an institution leaves, or asks for its data

## What exists today (MVP)
- **Suspend** (platform console → institution → Suspend, or `POST /api/v1/platform/tenants/{id}/suspend`):
  - Every session is revoked at once.
  - The portal shows "unavailable" on the institution's address.
  - Nothing is deleted. Reactivation restores everything.
- **Verification after leaving:** codes from a suspended or departed institution answer "Can't be
  checked here", with no student details.

## Not built yet (V1 backlog: "Tenant data export & closure")
Self-service export and automatic deletion. Until then, by an operator, on request, with the
institution's written instruction:

**Export.** One institution's rows, as CSV files, from a superuser `psql` session. For each table with
`tenant_id`:
```sql
\copy (SELECT * FROM students WHERE tenant_id = '…') TO 'students.csv' CSV HEADER
```
- Start with the tables the institution cares about: `students`, `exams`, `papers`, `mark_entries`,
  `publications`, `published_results`, `exam_statistics`, `verification_records`.
- Include the marksheet PDFs: `aws s3 sync s3://<files bucket>/tenants/<tenant id>/ ./files/`.
- Encrypt the bundle (age, to a key the institution gives you) before sending it.

**Deletion.** Not automated, and deliberately careful:
1. Suspend first.
2. Agree the date in writing.
3. Keep the export.
4. Delete the files prefix (`tenants/<id>/`) from object storage.
5. Delete the rows table by table, children first, as postgres in one transaction.
6. Record it in the platform audit log.

Backups still contain the data until they expire (nightly dumps; set retention accordingly, e.g. 35
days). Say so in the deletion confirmation.

Write the procedure's outcome in the incident or ticket. The first real request should become the V1
feature's specification.
