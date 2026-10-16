# Runbooks (P16.6)

What to do when something breaks, written before it breaks. Each alert in
[infra/monitoring/alerts.yml](../../infra/monitoring/alerts.yml) names the runbook it needs.

| Runbook | When |
|---|---|
| [api-down.md](api-down.md) | ScoreCodeAPIDown, ScoreCodeAPIInstanceDown; users see "can't reach ScoreCode" |
| [database-outage.md](database-outage.md) | ScoreCodePostgresDown, ScoreCodeDatabaseUnreachableFromAPI, connections high; ScoreCodeDiskFillingUp (free space first: old releases in /opt/scorecode/releases, `docker image prune` of unused versions, log archive) |
| [redis-outage.md](redis-outage.md) | Redis down or evicting (no alert pages: the product keeps working) |
| [stuck-publication.md](stuck-publication.md) | ScoreCodeScheduledPublicationLate, ScoreCodeQueueFallingBehind, ScoreCodeDeadJobs, ScoreCodeWorkerDown |
| [result-day.md](result-day.md) | Before and during a big publication; ScoreCodeHigh5xxRate, slow reads, pool exhaustion; ScoreCodeMemoryLow (fewer PDF processes: `PDF_PROCESSES=1`) |
| [backup-and-restore.md](backup-and-restore.md) | ScoreCodeBackupStale; restoring after data loss; the monthly drill |
| [deploy-and-rollback.md](deploy-and-rollback.md) | Installing a server, releasing, rolling back |
| [security-incident.md](security-incident.md) | Credential stuffing, a leaked secret, a suspected cross-tenant exposure; ScoreCodeEmailFailures (a revoked or wrong SMTP key: `secrets-check.py --connect smtp`) |
| (no runbook: a sales call) | ScoreCodeTenantsNearLimit: an institution uses 90% of a plan limit; offer the next plan before a limit stops it |
| [tenant-offboarding.md](tenant-offboarding.md) | An institution leaves, or asks for its data |
| [incident-template.md](incident-template.md) | Status updates, messages to institutions, the post-incident review |
| [credentials.md](credentials.md) | What deployment needs from the owner, the one secrets file, and how it's used without being seen |

## Ground rules
- **Severity.** `page`: students or institutions are affected now, so act within 15 minutes. `warn`: act
  within the working day.
- **First, communicate.** Open an incident note (template) when a page fires, and post the first status
  update within 15 minutes, even if it's only "investigating".
- **Change one thing at a time**, and write it in the incident note with the time (UTC and IST).
- **Never** edit published results, audit logs or verification records by hand. They are evidence, and
  triggers refuse it anyway. Corrections go through re-publication.
- **Where things are** (demo VM, `compose.prod.yml`):
  - The server lives at `/opt/scorecode`.
  - Logs: `docker compose -f compose.prod.yml --env-file env/deploy.env logs -f api worker proxy`.
  - Grafana dashboard: "ScoreCode overview". Prometheus is on `:9090` inside the VM (SSH tunnel).
  - Deep health: the platform console, or `GET /api/v1/platform/health/deep` (platform sign-in).
- Below, `dc` means
  `SCORECODE_VERSION=$(cat .deployed-version) docker compose -f compose.prod.yml --env-file env/deploy.env`.

## Verification
- [complete-platform-verification.md](complete-platform-verification.md): every feature, step by step, with copy-paste commands and expected results.
- [acceptance-checklist.md](acceptance-checklist.md): one row per test, with its status and evidence.
