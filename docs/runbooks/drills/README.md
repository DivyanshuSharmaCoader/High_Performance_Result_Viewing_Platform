# Restore drill log

One entry per drill: date, where it ran, the data size, the measured RTO, whether the fingerprints
matched, and anything that went wrong. CI drills come from `ops.yml` (`restore-drill` job; its step
summary is the source).

| Date | Where | Data | Backup | Restore | Fingerprints | Measured RTO | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08 21:34 UTC | CI, `ops.yml` run 37847430260 (commit 60e30bf), GitHub runner | 8,000 students, 48,000 marks, 8,000 published results; 202 fingerprint lines | 6.2 MB age-encrypted, 2 s, to a second bucket; stored object checked to be ciphertext | 5 s (download, decrypt, schema, data, constraints; FORCE RLS lifted and restored on 46 tables) | Identical: row counts, result/statistics/verification checksums, RLS flags on every table, 50 policies, triggers, grants, function bodies | **57 s** from deleting the database container and volume to the app passing the smoke test | Two earlier attempts failed and led to the three-step restore: forced RLS blocked loading the rows, then validating the foreign keys (runs 37845685780, 37846562548). RPO here is up to 24 h (nightly); production with managed PITR is about 5 min. |
