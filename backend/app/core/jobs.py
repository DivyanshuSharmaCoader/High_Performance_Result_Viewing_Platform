"""PostgreSQL-backed job queue (decision D8, ADR 0008; docs/08 §6).

* **Transactional enqueue** — ``enqueue()`` inserts into ``jobs`` inside the caller's unit of work, so
  a job exists if and only if the business transaction commits.
* **Claiming** uses ``FOR UPDATE SKIP LOCKED`` inside the ``jobs_claim()`` SECURITY DEFINER function, so
  the runtime role never needs to read other tenants' job rows.
* **Leases** — a claimed job holds a lease; a crashed worker's jobs are re-queued by ``jobs_reap()``.
* **Retries** with exponential backoff; after ``max_attempts`` a job is dead-lettered (``dead``).
* Every handler runs inside a fresh unit of work bound to the job's tenant (RLS context set first).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from app.core.errors import DomainError
from app.core.ids import uuid7
from app.core.logging import get_logger
from app.core.metrics import JOB_DURATION, JOBS, JOBS_BY_STATUS, JOBS_OLDEST, WORKER_ACTIVE

if TYPE_CHECKING:
    from app.core.container import Infra
    from app.core.db import UnitOfWork

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Job:
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    queue: str
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


@dataclass
class JobContext:
    job: Job
    infra: Infra

    async def set_progress(self, uow: UnitOfWork, **progress: Any) -> None:
        await uow.session.execute(
            text("UPDATE jobs SET progress = CAST(:p AS jsonb), updated_at = now() WHERE id = :id"),
            {"p": _json(progress), "id": self.job.id},
        )


Handler = Callable[[JobContext], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True, slots=True)
class JobSpec:
    kind: str
    queue: str
    handler: Handler
    max_attempts: int


class JobRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, JobSpec] = {}

    def register(self, kind: str, *, queue: str, max_attempts: int = 5) -> Callable[[Handler], Handler]:
        def deco(fn: Handler) -> Handler:
            if kind in self._specs and self._specs[kind].handler is not fn:
                raise ValueError(f"job kind {kind!r} registered twice")
            self._specs[kind] = JobSpec(kind, queue, fn, max_attempts)
            return fn

        return deco

    def spec(self, kind: str) -> JobSpec:
        try:
            return self._specs[kind]
        except KeyError:
            raise LookupError(f"no handler for job kind {kind!r}") from None

    def kinds(self) -> list[str]:
        return sorted(self._specs)


registry = JobRegistry()


def _json(value: Any) -> str:
    import json

    return json.dumps(value, default=str)


async def enqueue(
    uow: UnitOfWork,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    run_at: datetime | None = None,
    dedupe_key: str | None = None,
    created_by: uuid.UUID | None = None,
    tenant_scoped: bool = True,
) -> uuid.UUID:
    """Insert a job in the caller's transaction. Tenant jobs always carry the UoW's tenant id."""
    spec = registry.spec(kind)
    tenant_id = uow.require_tenant() if tenant_scoped else None
    job_id = uuid7()
    params = {
        "id": job_id,
        "tenant_id": tenant_id,
        "queue": spec.queue,
        "kind": kind,
        "payload": _json(payload or {}),
        "max_attempts": spec.max_attempts,
        "dedupe_key": dedupe_key,
        "created_by": created_by,
        "run_at": run_at,
    }
    result = await uow.session.execute(
        text(
            """
            INSERT INTO jobs (id, tenant_id, queue, kind, payload, status, max_attempts, dedupe_key,
                              created_by, run_at)
            VALUES (:id, :tenant_id, :queue, :kind, CAST(:payload AS jsonb), 'queued', :max_attempts,
                    :dedupe_key, :created_by, COALESCE(:run_at, now()))
            ON CONFLICT (dedupe_key) WHERE dedupe_key IS NOT NULL AND status IN ('queued', 'running')
            DO NOTHING
            RETURNING id
            """
        ),
        params,
    )
    inserted = result.scalar_one_or_none()
    if inserted is None:  # an identical job is already pending — return it
        existing = await uow.session.execute(
            text("SELECT id FROM jobs WHERE dedupe_key = :k AND status IN ('queued','running')"),
            {"k": dedupe_key},
        )
        return uuid.UUID(str(existing.scalar_one()))
    return job_id


def backoff_seconds(attempt: int) -> int:
    return int(min(600, 5 * (2 ** max(0, attempt - 1))))


class Worker:
    def __init__(
        self,
        infra: Infra,
        queues: list[str],
        *,
        concurrency: int = 4,
        poll_interval_s: float = 1.0,
        lease_s: int = 120,
        tenant_concurrency_cap: int = 2,
    ) -> None:
        self.infra = infra
        self.queues = queues
        self.concurrency = concurrency
        self.poll_interval_s = poll_interval_s
        self.lease_s = lease_s
        self.tenant_cap = tenant_concurrency_cap
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid7().hex[:8]}"
        self._stop = asyncio.Event()
        self._tasks: set[asyncio.Task[None]] = set()
        self._sem = asyncio.Semaphore(concurrency)

    def stop(self) -> None:
        self._stop.set()

    async def _claim(self, limit: int) -> list[Job]:
        async with self.infra.db.uow() as uow:
            rows = (
                await uow.session.execute(
                    text(
                        "SELECT id, tenant_id, queue, kind, payload, attempts, max_attempts "
                        "FROM jobs_claim(:queues, :worker, :limit, :lease, :cap)"
                    ),
                    {
                        "queues": self.queues,
                        "worker": self.worker_id,
                        "limit": limit,
                        "lease": self.lease_s,
                        "cap": self.tenant_cap,
                    },
                )
            ).all()
        return [
            Job(r.id, r.tenant_id, r.queue, r.kind, dict(r.payload or {}), r.attempts, r.max_attempts)
            for r in rows
        ]

    async def _finish(
        self,
        job: Job,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        retry_in_s: int | None = None,
    ) -> None:
        async with self.infra.db.uow() as uow:
            await uow.session.execute(
                text("SELECT jobs_finish(:id, :worker, :status, CAST(:result AS jsonb), :error, :retry)"),
                {
                    "id": job.id,
                    "worker": self.worker_id,
                    "status": status,
                    "result": _json(result) if result is not None else None,
                    "error": (error or "")[:2000] or None,
                    "retry": retry_in_s,
                },
            )

    async def _heartbeat(self, job: Job) -> None:
        while True:
            await asyncio.sleep(max(5, self.lease_s // 3))
            try:
                async with self.infra.db.uow() as uow:
                    await uow.session.execute(
                        text("SELECT jobs_heartbeat(:id, :worker, :lease)"),
                        {"id": job.id, "worker": self.worker_id, "lease": self.lease_s},
                    )
            except Exception:
                log.warning("job_heartbeat_failed", job_id=str(job.id))

    async def execute(self, job: Job) -> None:
        spec = registry.spec(job.kind)
        started = time.perf_counter()
        hb = asyncio.create_task(self._heartbeat(job))
        WORKER_ACTIVE.inc()
        log_ctx = {"job_id": str(job.id), "job_kind": job.kind, "queue": job.queue, "attempt": job.attempts}
        if job.tenant_id:
            log_ctx["tenant_id"] = str(job.tenant_id)
        try:
            result = await spec.handler(JobContext(job=job, infra=self.infra))
        except DomainError as exc:
            # Business rule failures are not transient: fail without retrying.
            JOBS.labels(job.queue, job.kind, "failed").inc()
            log.warning("job_failed", error_code=exc.code, **log_ctx)
            await self._finish(job, "failed", error=f"{exc.code}: {exc.detail}")
        except Exception as exc:
            retryable = job.attempts < job.max_attempts
            outcome = "retry" if retryable else "dead"
            JOBS.labels(job.queue, job.kind, outcome).inc()
            log.exception("job_error", error_code=type(exc).__name__, **log_ctx)
            await self._finish(
                job,
                "queued" if retryable else "dead",
                error=f"{type(exc).__name__}: {exc}",
                retry_in_s=backoff_seconds(job.attempts) if retryable else None,
            )
        else:
            JOBS.labels(job.queue, job.kind, "succeeded").inc()
            await self._finish(job, "succeeded", result=result)
            log.info("job_succeeded", duration_ms=round((time.perf_counter() - started) * 1000), **log_ctx)
        finally:
            hb.cancel()
            WORKER_ACTIVE.dec()
            JOB_DURATION.labels(job.queue, job.kind).observe(time.perf_counter() - started)

    async def _run_one(self, job: Job) -> None:
        try:
            await self.execute(job)
        finally:
            self._sem.release()

    async def reap(self) -> int:
        async with self.infra.db.uow() as uow:
            n = (await uow.session.execute(text("SELECT jobs_reap()"))).scalar_one()
        return int(n or 0)

    async def export_stats(self) -> None:
        """Queue backlog, running and dead jobs as gauges (docs/14 §Q alerts). Statuses with no jobs
        report 0, so a queue that drained doesn't keep its last value."""
        async with self.infra.db.uow() as uow:
            rows = (await uow.session.execute(text("SELECT * FROM jobs_stats()"))).all()
        seen = {(r.queue, r.status): (r.jobs, r.oldest_s) for r in rows}
        for queue in {*self.queues, *(q for q, _ in seen)}:
            for status in ("queued", "running", "dead"):
                jobs, oldest = seen.get((queue, status), (0, 0.0))
                JOBS_BY_STATUS.labels(queue, status).set(jobs)
                JOBS_OLDEST.labels(queue, status).set(oldest)

    async def run_forever(self) -> None:
        log.info("worker_started", queue=",".join(self.queues))
        last_reap = last_stats = 0.0
        while not self._stop.is_set():
            try:
                if time.monotonic() - last_reap > 30:
                    await self.reap()
                    last_reap = time.monotonic()
                if time.monotonic() - last_stats > 15:
                    await self.export_stats()
                    last_stats = time.monotonic()
                free = self.concurrency - len(self._tasks)
                jobs = await self._claim(max(1, free)) if free > 0 else []
            except Exception:
                log.exception("worker_claim_failed")
                jobs = []
            for job in jobs:
                await self._sem.acquire()
                task = asyncio.create_task(self._run_one(job))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            if not jobs:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval_s)
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=self.lease_s)
        log.info("worker_stopped")

    async def drain(self, *, max_jobs: int = 10_000, include_future: bool = False) -> int:
        """Run queued jobs until the queue is empty (tests, CLI). Returns jobs executed."""
        done = 0
        while done < max_jobs:
            if include_future:
                async with self.infra.db.uow() as uow:
                    await uow.session.execute(text("SELECT jobs_make_due(:queues)"), {"queues": self.queues})
            jobs = await self._claim(1)
            if not jobs:
                return done
            for job in jobs:
                await self.execute(job)
                done += 1
        return done


def run_at_in(seconds: float) -> datetime:
    from app.core.clock import utcnow

    return utcnow() + timedelta(seconds=seconds)


@dataclass
class JobStatus:
    id: uuid.UUID
    kind: str
    status: str
    progress: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    attempts: int = 0
    created_at: datetime | None = None
    finished_at: datetime | None = None
    created_by: uuid.UUID | None = None
    extra: dict[str, Any] = field(default_factory=dict)


async def get_job_status(uow: UnitOfWork, job_id: uuid.UUID) -> JobStatus | None:
    """Read a job (RLS restricts it to the current tenant)."""
    row = (
        await uow.session.execute(
            text(
                "SELECT id, kind, status, progress, result, last_error, attempts, created_at, finished_at, "
                "created_by FROM jobs WHERE id = :id AND tenant_id = :tid"
            ),
            {"id": job_id, "tid": uow.require_tenant()},
        )
    ).one_or_none()
    if row is None:
        return None
    # Never expose internal exception text to clients: only the domain error code prefix.
    error = row.last_error.split(":", 1)[0] if row.last_error and row.status in ("failed", "dead") else None
    return JobStatus(
        id=row.id,
        kind=row.kind,
        status=row.status,
        progress=row.progress,
        result=row.result,
        error=error,
        attempts=row.attempts,
        created_at=row.created_at,
        finished_at=row.finished_at,
        created_by=row.created_by,
    )
