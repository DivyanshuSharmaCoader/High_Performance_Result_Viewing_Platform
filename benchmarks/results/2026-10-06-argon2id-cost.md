# Argon2id cost — developer laptop — 2026-10-06

Measured for P3.2 (docs/10 §2 asks for ~50–100 ms per hash on the *production* CPU; this is a laptop baseline, not production).

## Environment
- Git commit: measured on the working tree after `58ceb2b` (script `backend/scripts/measure_argon2.py`)
- Machine: Apple M2, 8 cores, macOS 15.3. **Python 3.12.13 is an x86_64 build running under Rosetta 2**, so absolute numbers are pessimistic compared with native arm64 or a server x86 CPU.
- Library: argon2-cffi 25.1.0
- Parameters (defaults in `app/core/config.py`): `time_cost=2`, `memory_cost=19456 KiB` (19 MiB), `parallelism=1` — the OWASP 2023 baseline for Argon2id.

## Results (single run, 60 timed verifications after 5 warm-up)
| Metric | Value |
|---|---|
| Single verification p50 | 33.1 ms |
| Single verification p95 | 35.4 ms |
| Max | 40.2 ms |
| Throughput, 1 thread | 28.4 verifications/s |
| Throughput, 2 threads | 53.5 /s |
| Throughput, 4 threads | 98.5 /s |
| Throughput, 8 threads | 152.4 /s |

## Analysis
- ~33 ms per hash is below the 50–100 ms band suggested in docs/10. We keep the OWASP baseline for now; **raising `time_cost` is a decision for Phase 14** after measuring on the target production CPU, because it directly lowers login throughput on result day (docs/11 §3).
- Memory per concurrent hash is ~19 MiB, so `SCORECODE_ARGON2_MAX_CONCURRENCY=4` per API process bounds hashing memory to ~76 MiB per process.
- Scaling to 8 threads is sub-linear (152/s vs 8 × 28/s), consistent with 4 performance + 4 efficiency cores and emulation overhead.

## Next action
Re-run on the demo/production VM (Phase 16) and record ms/hash there; adjust `SCORECODE_ARGON2_TIME_COST` only with a before/after login-throughput measurement.
