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
