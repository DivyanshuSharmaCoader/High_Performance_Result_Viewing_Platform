# Benchmarks

Methodology: [docs/11 §4](../docs/11-performance-architecture.md#4-benchmark-plan-scientifically-valid). **Nothing in this folder is a claim until a dated result file exists for it.**

## Layout (created during Phase 10/14)
```
benchmarks/
  k6/                  scenario scripts (A–D), shared journey module
  data/                synthetic data generator config (deterministic seeds)
  results/             one Markdown file per run: YYYY-MM-DD-<scenario>-<variant>.md
```

## Result file template
Copy this into `results/YYYY-MM-DD-<scenario>-<variant>.md`:

```markdown
# <Scenario ID> — <pre-authenticated | cold-login> — <date>

## Environment
- Git commit: <sha>   · k6 script version: <sha/path>
- System under test: <provider/VM type, vCPU, RAM, disk>, region, OS, container limits
- Topology: <N api processes × M workers>, PgBouncer <yes/no>, Redis <yes/no>
- Load generator: <machine; same host or separate?>
- Config: DB pool size, Uvicorn workers, Argon2 params (t, m, p), cache settings
- Dataset: <tenants, students, publications> (generator seed)

## Scenario
- Virtual users, ramp profile, duration, think time, journey

## Results (median of N runs; spread in brackets)
| Endpoint | RPS | p50 | p95 | p99 | Errors (5xx) | 429s |
|---|---|---|---|---|---|---|

## Resources
CPU / memory per container · DB CPU · active connections · Redis hit rate · queue depth (attach graphs)

## Analysis
Bottleneck observed, evidence (EXPLAIN, profiles), what this does and does not show.

## Next action
```

## Results index
| Date | Scenario | Variant | Key result | File |
|---|---|---|---|---|
| 2026-10-06 | Argon2id cost (P3.2) | laptop, Rosetta 2 | 33.1 ms p50 per verify; 98.5 verifications/s on 4 threads | [results/2026-10-06-argon2id-cost.md](results/2026-10-06-argon2id-cost.md) |
