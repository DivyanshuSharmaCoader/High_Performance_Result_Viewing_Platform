# Backup and restore

**Alerts:** `ScoreCodeBackupStale` (page: the last success is over 26 h old), `ScoreCodeBackupNeverReported`.

**What runs (infra/backup):**
- The `backup` container dumps the database nightly at 02:30 IST (`pg_dump -Fc`, one consistent snapshot,
  as the read-only `scorecode_backup` role).
- The dump is encrypted with **age** to a public key, so the server can't decrypt its own backups.
- It is uploaded to a **second storage** (`BACKUP_S3_URI`: another provider or region than the files
  bucket), and the files bucket is synced next to it.
- Success is pushed to Prometheus.
- **RPO:** up to 24 h with nightly dumps. With managed PostgreSQL and point-in-time recovery, about
  5 min (docs/10 §12): use that first when it's available.

## Keys
- The age **private key** lives offline, in the operators' password manager or vault, never on the
  server. Keep two copies held by two people.
- Losing the private key means losing every backup. Test that it decrypts in every drill.
- To rotate: make a new key pair, set the new public key in `env/backup.env`, and keep the old private
  key until the last backup made with it expires.

## What the server's backup credentials may do
The backup job only writes (`s3 cp`, `s3 sync` without `--delete`), so the server's key needs no delete
right. **Measured 2026-10-14:** the production backup key can put, get and **delete** objects; it can't
list all buckets or read versioning or lifecycle settings. A key that can delete lets anyone who takes over
the server erase the backups too. In the AWS console (free), as the owner:
- Give the server's IAM user only `s3:PutObject` and `s3:GetObject` on `arn:aws:s3:::<backup-bucket>/*`
  and `s3:ListBucket` on `arn:aws:s3:::<backup-bucket>`. No `s3:DeleteObject`.
- Expire old backups with a **lifecycle rule** on the bucket (e.g. `prod/` after 35 days, `restore-test/`
  after 1 day), not with the server's key.
- Optional, stronger: versioning plus Object Lock in governance mode for the retention period.
- Check afterwards: `secrets-check.py --connect backup-s3` writes, reads and tries to delete one object
  under `_healthcheck/`. A refused delete is now the expected result; remove that object with the lifecycle
  rule.

## Run one now
```bash
dc run --rm backup backup.sh     # prints {"backup": "s3://…", "bytes": …, "sha256": …, "seconds": …}
```
Before every deploy, `deploy.sh` does this automatically with the running version.

## Restore
1. **Stop writes:** `dc stop api worker proxy`. Post a status update.
2. **An empty database.**
   - Self-hosted: a new volume, `dc rm -sf postgres && docker volume rm scorecode_pgdata && dc up -d
     postgres`. The init script recreates the roles. This destroys whatever is left, so do it only when
     restoring is the decision.
   - Managed: create a new database owned by `scorecode_migrator`, and create the roles
     (infra/postgres/init/01-roles.sh).
3. **Bring the private key** onto the server only for this step, as a file readable by you alone, and
   delete it afterwards:
   ```bash
   dc run --rm -e PGUSER=scorecode_migrator -e PGPASSWORD=… -e BACKUP_AGE_IDENTITY=/key/age.txt \
     -v "$PWD/restore-key:/key:ro" backup restore.sh            # the newest backup
   # or: … backup restore.sh s3://…/scorecode-20261009T210000Z.dump.age
   ```
   It restores as the database owner (no superuser needed): the schema, then the data, policies, triggers
   and constraints. Forced row-level security is lifted only for the restore, only from the tables that
   had it, and put back at the end. The drill's fingerprint checks the flags.
4. **Start:** `dc up -d --wait`. The migrations run, and are a no-op when the backup is at the same
   version.
5. **Smoke test:** `infra/ops/smoke.sh` (with `SMOKE_BASE_DOMAIN`, `SMOKE_SCHEME=https`).
6. **Tell institutions** what time the data is from, i.e. the backup's timestamp. Anything after it, such
   as marks entered or publications made, must be redone; list them from the audit log of the old
   database if it's readable.

## Drill (monthly; and `ops.yml` weekly on CI)
The `restore-drill` job runs the whole procedure against 8,000 students:
1. Fingerprint the database.
2. Back up.
3. Destroy the database container and volume.
4. Restore onto a fresh server.
5. Compare fingerprints: row counts, checksums of results, statistics and verification records, and the
   RLS flags, policies, triggers and grants.
6. Start the app and smoke test.

It reports the **measured RTO**. Copy each result into the drill log: [drills/](drills/).

## Restore test on the production server (monthly, and after any change to backups)
A real restore of the newest production backup that never brings the age private key to the server:

```bash
infra/ops/with-secrets.sh run -- uv run --project backend python infra/ops/restore-test.py ~/path/to/backup-age-key.txt
```

1. It downloads the newest encrypted dump from `prod/db/` to a temporary folder on the Mac.
2. `age` decrypts it there, with the key file named on the command line. The plaintext is streamed over SSH
   and never written to the Mac's disk.
3. `sudo scorecode-ctl restore-test` on the server restores it into a throwaway database with **no
   network**, using `restore.sh` as the backup image runs it.
4. It prints how many fingerprint lines match the live database, and the lines that differ (table names,
   row counts and checksums, never rows). Rows written since the backup was taken (sessions, jobs) are
   expected to differ.
5. The scratch database and the plaintext are removed, also on failure.

The release rehearsal (`release.yml`) runs the same path on every change to the deploy files, with its own
key. Record each production result in [drills/](drills/).

## Cost and retention (checked 2026-10-14; the owner's rule: no extra spending without approval)
**Bucket, as verified from the objects' own `x-amz-expiration` (the backup key may not read the rules):**
`prod/` expires 35 days after upload (rule `scorecode-prod-retention-35d`); `restore-test/` and
`_healthcheck/` 1 day (`scorecode-restore-test-1d`, `scorecode-healthcheck-1d`). Versioning is on;
the owner set noncurrent versions of `prod/` to go after 1 day. The server's key may put, get and list,
and **may not delete** (`AccessDenied` under all three prefixes): only the lifecycle rules remove data.

**Prices** (AWS price list, S3 Standard, ap-southeast-2): storage $0.025 per GB-month; PUT/COPY/POST/LIST
$0.0055 per 1,000; GET $0.0044 per 10,000; data in free; data out to the internet, 100 GB a month free.

| What | Today (measured) | 10 institutions × 2,000 students (estimate) |
|---|---|---|
| Nightly database dump | 0.3 MB | about 20–60 MB |
| Dumps kept (35 days + 1 day noncurrent) | about 11 MB | about 0.7–2.2 GB |
| Files mirror (`prod/files/`, one copy, re-uploaded as it expires every 35 days) | 0 | about 1–2 GB of marksheet PDFs |
| Requests a month | about 100 | about 20,000 PUTs (re-uploads) |
| **Monthly cost** | **under $0.01** | **about $0.10–$0.20**, before any free tier or credits |

**Free allowance:** an account from before 15 July 2025 has 12 months of 5 GB S3 Standard, 20,000 GETs and
2,000 PUTs a month free; a newer account has Free Tier credits instead (up to $200, 6 months). Either way,
today's usage costs nothing.

**Safeguards:** `ScoreCodeBackupStorageHigh` emails ALERT_EMAIL_TO when the backups pass 4 GB (80% of the
5 GB allowance), before anything is billed. **Owner, once, in the AWS console:** Billing → Budgets → a
$1 monthly cost budget with an email alert (two budgets are free), and Billing preferences → "Receive Free
Tier usage alerts". The backup key can't do either, by design.

**If the allowance is ever reached:** stop and decide; do not let it bill silently. Options, cheapest
first: shorten `prod/` retention (e.g. 21 days; the restore point before each release still exists),
skip the files mirror for institutions whose PDFs can be re-rendered from the database, or accept about
$0.025 per GB-month.
