#!/bin/sh
# Runs backup.sh once a day at BACKUP_AT_UTC (HH:MM; default 21:00 UTC = 02:30 IST). A failed backup is
# logged and left to the ScoreCodeBackupStale alert (docs/runbooks/backup-and-restore.md).
at=${BACKUP_AT_UTC:-21:00}
last=""
echo "backups daily at $at UTC"
while true; do
  today=$(date -u +%F)
  if [ "$(date -u +%H:%M)" = "$at" ] && [ "$last" != "$today" ]; then
    last=$today
    backup.sh || echo "backup failed at $(date -u +%FT%TZ)" >&2
  fi
  sleep 20
done
