# Redis outage

**No paging alert, by design:** Redis holds no truth (docs/11 §2.5). With Redis stopped for 60 s under
scenario B, throughput and errors didn't change (benchmarks/results/2026-10-08-failure-under-load.md).

**What degrades:**
- **Sessions, tenant configuration and the student read cache** fall back to each process's own cache
  and the database. A circuit breaker stops waiting on Redis.
- **Rate limits** become per process instead of shared: per address, the limit is multiplied by the
  number of API processes. Watch `ScoreCodeLoginFailureSpike`.
- **Withdrawing a publication** still takes effect at once in the process that did it, and within 5 s
  everywhere else.

## Check and fix
1. `dc ps redis` and `dc logs --tail 50 redis`.
2. `dc restart redis`. It starts empty (no persistence, on purpose), and caches refill on their own.
3. **Repeated evictions** (`INFO stats` → `evicted_keys` growing fast): raise `--maxmemory` in
   `compose.prod.yml` (256 MB today) if the VM has room. The policy is `allkeys-lru`, so nothing breaks
   meanwhile.
4. **If Redis has to stay down,** nothing else needs to change. The API's `/readyz` stays green, with
   `cache: local`.
