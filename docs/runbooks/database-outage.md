# Database outage

**Alerts:** `ScoreCodePostgresDown` and `ScoreCodeDatabaseUnreachableFromAPI` (page),
`ScoreCodeDatabaseConnectionsHigh` (warn).
**Users see:** quick `503 service-unavailable` answers with `Retry-After: 5`, never hangs or 500s
(P14.5). The apps retry on their own. Sign-in and every read need the database, so the whole product
waits. Redis-cached sessions don't make reads possible.

## Check
1. **Is it up?** Self-hosted: `dc ps postgres` and `dc logs --tail 100 postgres`. Managed: the provider's
   console (status, failover events, storage).
2. **Out of disk?** (`No space left on device`.) Self-hosted: `df -h` on the VM. The usual causes are
   Docker logs (capped at 5 × 20 MB per container in `compose.prod.yml`), old images (`docker image prune`),
   or WAL growth.
3. **Connections exhausted?** `ScoreCodeDatabaseConnectionsHigh`, or `remaining connection slots are
   reserved`. Every API process opens up to 15 (pool 10 + overflow 5), the worker 15, and the platform pool
   3 + 5. Two API workers plus a worker is about 60 of the 200 allowed. More means a leak or extra
   replicas: check `SELECT application_name, state, count(*) FROM pg_stat_activity GROUP BY 1, 2`.
4. **Slow, not down?** `SELECT pid, now() - query_start, state, left(query, 80) FROM pg_stat_activity
   WHERE state <> 'idle' ORDER BY 2 DESC`. The app role's `statement_timeout` is 15 s, and idle
   transactions are cut at 60 s.

## Fix
- **Restart (self-hosted):** `dc restart postgres`. Measured under load on 2026-10-08/09: one 10-second
  window of 503s, then the pool recovers by itself, because dead connections are replaced at their next
  use. No app restart is needed.
- **Disk full:** free space first (logs, images). Don't delete anything under the data volume.
- **Corruption or lost data:** stop writes (`dc stop api worker`), then follow
  [backup-and-restore.md](backup-and-restore.md). Managed: restore to a point in time from the provider's
  console into a new instance, then point `SCORECODE_DATABASE_URL_*` at it.
- **Managed failover:** the endpoint stays the same. Expect up to about a minute of 503s; nothing to do
  unless it lasts longer.

## Never
- Run `ALTER TABLE … NO FORCE ROW LEVEL SECURITY` outside a restore. It removes a tenant-isolation layer.
- Connect the app with the migrator or superuser credentials to "get it working".
