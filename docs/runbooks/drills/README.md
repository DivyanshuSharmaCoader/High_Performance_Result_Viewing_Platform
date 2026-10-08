# Restore drill log

One entry per drill: date, where it ran, the data size, the measured RTO, whether the fingerprints
matched, and anything that went wrong. CI drills come from `ops.yml` (`restore-drill` job; its step
summary is the source).

| Date | Where | Data | Backup | Restore | Fingerprints | Measured RTO | Notes |
|---|---|---|---|---|---|---|---|
