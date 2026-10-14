"""Processes for laying out marksheets (P14.3).

WeasyPrint's layout is CPU-bound Python: threads in one process share one core (the GIL), so a worker
renders about 5 marksheets a second however many jobs run (benchmarks/results/2026-10-08-marksheet-
render.md). A small pool of *processes* uses the other cores. Processes are started with ``spawn``, not
``fork``: forking a process that runs an event loop and threads can copy held locks into the child.

``SCORECODE_PDF_PROCESSES=0`` lays out in a thread instead (tests, and machines with one core).

Each process is replaced after ``TASKS_PER_PROCESS`` marksheets. WeasyPrint keeps what it allocated (font
and style caches, fragments) for as long as its process lives: a worker held 2.3 GB at rest after 8,000
marksheets, which, beside a second stack on the same 8 GB server without swap, starved the machine
(benchmarks/results/2026-10-14-result-day-vps.md). Starting a fresh process takes a moment, once per 200.
"""

from __future__ import annotations

import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor

TASKS_PER_PROCESS = 200

_pool: ProcessPoolExecutor | None = None
_lock = threading.Lock()


def pool(processes: int) -> ProcessPoolExecutor:
    global _pool
    with _lock:
        if _pool is None:
            _pool = ProcessPoolExecutor(
                max_workers=processes,
                mp_context=multiprocessing.get_context("spawn"),
                max_tasks_per_child=TASKS_PER_PROCESS,
            )
        return _pool


def shutdown() -> None:
    global _pool
    with _lock:
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
            _pool = None
