"""Measure Argon2id cost with the configured parameters (P3.2, docs/11 §3).

Usage: uv run python scripts/measure_argon2.py [--n 60]
Reports single-hash latency percentiles and multi-thread throughput on this machine.
"""

from __future__ import annotations

import argparse
import os
import platform
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from argon2 import PasswordHasher

from app.core.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=60)
    args = parser.parse_args()
    s = Settings()
    ph = PasswordHasher(time_cost=s.argon2_time_cost, memory_cost=s.argon2_memory_kib, parallelism=s.argon2_parallelism)
    stored = ph.hash("benchmark-password-123")
    for _ in range(5):  # warm-up
        ph.verify(stored, "benchmark-password-123")
    samples = []
    for _ in range(args.n):
        t0 = time.perf_counter()
        ph.verify(stored, "benchmark-password-123")
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    q = statistics.quantiles(samples, n=100)
    print(f"machine: {platform.machine()} {platform.processor() or ''} cpus={os.cpu_count()} python={platform.python_version()}")
    print(f"params: t={s.argon2_time_cost} m={s.argon2_memory_kib}KiB p={s.argon2_parallelism}")
    print(f"single verify ms (n={args.n}): p50={q[49]:.1f} p95={q[94]:.1f} max={samples[-1]:.1f}")
    for workers in (1, 2, 4, 8):
        total = 40 * workers
        t0 = time.perf_counter()
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(lambda _: ph.verify(stored, "benchmark-password-123"), range(total)))
        elapsed = time.perf_counter() - t0
        print(f"threads={workers}: {total / elapsed:.1f} verifications/s")


if __name__ == "__main__":
    main()
