# Result day

A big publication is the product's peak: up to about 1,000 students arriving within minutes (docs/11,
scenario B).

**What was measured** (GitHub runner, 4 vCPU, with the load generator on the same machine):
- After the P14.3 optimisations: 573–593 req/s at 1,000 users, with 0 errors and p95 240–281 ms.
- Before them: 322–327 req/s with 3.3–3.6% errors (benchmarks/results/2026-10-09-read-path.md).

## The day before
- [ ] Ask the institution for the publication time and size (students, papers), and whether it's
      scheduled.
- [ ] `scorecode jobs stats`: no dead jobs, no backlog.
- [ ] The last backup is under 24 h old (Grafana: "hours since the last successful backup").
- [ ] Disk under 70% on the VM (or the managed database's storage).
- [ ] On a single small VM, consider `API_WORKERS=3` or `4` if the VM has the cores (one worker per vCPU
      at most, leaving one for the database). Then `dc up -d api`.
- [ ] Nobody deploys on result day. Agree a freeze.

## During
- **Watch** the "ScoreCode overview" dashboard: requests/s, the 5xx share, student-read p95 (target
  150 ms) and the database pool panel.
- **`503 overloaded`** (`ScoreCodeDatabasePoolExhausted`) means the API is saturated and requests waited
  more than 5 s for a database connection. The apps retry with backoff, so students eventually get their
  result. In order of effect:
  1. **More API processes:** `API_WORKERS`, or a second API container with `dc up -d --scale api=2 api`.
     Caddy finds the new one within 5 s.
  2. **More vCPU** for the VM: a restart of the VM, so plan it before, not during.
  3. Don't raise the pool size: the database isn't the bottleneck. It was at about 50% of one vCPU at
     saturation.
- **Database unreachable** (`ScoreCodeDatabaseUnreachableFromAPI`): go to
  [database-outage.md](database-outage.md). Students get retryable 503s, not wrong data.
- **Marksheets slow:** expected, see [stuck-publication.md](stuck-publication.md).

## After
- Write down the peak req/s, p95 and any 503 windows from the dashboard, in the institution's notes. It
  is the best capacity data there is.
- Return `API_WORKERS` and the replica count to normal.
