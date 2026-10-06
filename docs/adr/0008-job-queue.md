# ADR 0008 — PostgreSQL job queue (in-house, SKIP LOCKED)

**Context.** Decision D8 called for a spike of Procrastinate vs. a minimal in-house queue. Requirements: transactional enqueue, retries with backoff, delayed jobs (`run_at` for scheduled publication), leases for crashed workers, per-tenant concurrency caps, and — specific to our RLS design — workers must not need cross-tenant read access through the runtime role.

**Options.**
- *Procrastinate*: mature, async, but brings its own schema/roles conventions and its own connector (psycopg) alongside our asyncpg pools; adapting its tables to forced RLS + our three-role model would mean either exempting its tables from RLS or patching its queries.
- *In-house*: ~300 lines (`app/core/jobs.py` + SQL functions) over one `jobs` table.

**Decision.** In-house queue. Enqueue is a plain INSERT in the business transaction (RLS-checked). Claiming, finishing, heartbeats and reaping are `SECURITY DEFINER` functions (`jobs_claim`, `jobs_finish`, `jobs_heartbeat`, `jobs_reap`) owned by the migrator role, so the runtime role never reads other tenants' jobs. Handlers run in a fresh unit of work bound to the job's tenant.

**Evidence.** `tests/integration/test_kernel.py`: enqueue-iff-commit, retry → dead-letter, four concurrent workers over 30 jobs run each exactly once, reaper re-queues expired leases, runtime role cannot see another tenant's job.

**Honest note.** Procrastinate was evaluated on paper, not prototyped. Revisit if queue throughput is ever measured as a bottleneck (unlikely at our volumes).
