# Development-environment latency investigation — 2026-10-06

**Not a benchmark of ScoreCode's capacity.** This records what was measured on a developer laptop while
investigating slow requests during end-to-end runs, so later benchmarks (Phase 14, on a dedicated Linux VM)
are not compared against these numbers by mistake.

## Environment
- Apple M2 (8 cores), macOS 15.3, Docker Desktop VM: 8 vCPU, 7.7 GiB; containers are linux/arm64.
- Host-run Python 3.12 is an x86_64 build under Rosetta 2.
- Stack: `docker compose --profile app` (Caddy → API with 2 Uvicorn workers → Postgres 16, Redis 7) at commit after `58ceb2b`+.
- Load: `httpx` client on the same laptop; Playwright (Chromium) running concurrently in some runs.

## Measurements
| What | Result |
|---|---|
| `GET /api/v1/tenant/config` via Caddy in Docker, 1 client, 200 requests | p50 4.3–4.8 ms, p95 5.7–8.3 ms, max 377–466 ms |
| Same, 20 concurrent clients, 400 requests | p50 70–85 ms, p95 277–341 ms, max 444–670 ms |
| Same endpoint, server-side duration from API logs (616 requests) | p50 1.9 ms, p95 34.8 ms, max 1,561 ms |
| Host-run API (1 process, Rosetta), 20 concurrent, 1,000 requests | p50 82–95 ms, p95 273–388 ms |
| `redis-cli --intrinsic-latency 10` inside the VM, otherwise idle | max scheduling stall 51 ms |
| py-spy sampling of the API main thread during E2E (216 samples) | event loop idle (waiting) in 92% of samples |
| `pg_stat_activity` sampling during E2E | 4 transactions from API **and** worker processes simultaneously "idle in transaction" (waiting on the client) for 5–9 s; one `COMMIT` waiting 3.7 s on WALSync |
| Argon2id in 4 threads vs. event-loop ticker (GIL check) | loop lag max 19–30 ms → the GIL is released during hashing |

## Analysis
1. **Real bug found and fixed:** on a session-cache miss a request held two pooled DB connections at once
   (request transaction + authentication lookup). With concurrency equal to the pool size this deadlocks until
   the pool timeout. Reproduced with a pool of 1 (`QueuePool limit … timed out`), fixed in `app/core/http.py`,
   regression test `tests/integration/test_connection_usage.py`.
2. **Multi-second stalls are environmental:** simultaneous multi-second pauses across separate processes and
   containers, an idle main thread, and VM-level scheduling stalls point to the Docker Desktop VM being paused
   or starved while the laptop also runs browsers — not to lock contention or blocking code.
3. **Known inefficiency (not yet optimised, Phase 14):** every API request opens a DB transaction
   (`BEGIN`, `set_config`, `COMMIT`) even when served entirely from cache, e.g. `/tenant/config`.

## What this does not show
Throughput or latency on production-like hardware. No capacity claim should be derived from this file.

## Next action
Phase 14: repeat on a dedicated Linux VM with the load generator on a separate machine; evaluate lazy
transaction start (begin + `set_config` on first query).
