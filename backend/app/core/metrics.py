"""Prometheus metrics (docs/14 §Q). Exposed on ``/metrics`` — internal network only (the proxy never
routes it publicly).

With several Uvicorn workers, each process counts on its own, and a scrape reaches whichever process
answers it: counters would jump between processes and ``rate()`` would be meaningless. So ``scorecode
api --workers N`` (N > 1) turns on prometheus_client's multiprocess mode before the workers start. Each
process writes its samples to a shared directory, and ``/metrics`` reports the sum over all of them.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest, multiprocess

MULTIPROC_ENV = "PROMETHEUS_MULTIPROC_DIR"


def prepare_multiprocess(path: str) -> None:
    """Before the API's workers start: a fresh directory (samples of a previous run would be added in)."""
    shutil.rmtree(path, ignore_errors=True)
    Path(path).mkdir(mode=0o700, parents=True)
    os.environ[MULTIPROC_ENV] = path


def render() -> bytes:
    """Every process's samples when several workers share the work; this process's otherwise."""
    if os.environ.get(MULTIPROC_ENV):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        return generate_latest(registry)
    return generate_latest()


HTTP_REQUESTS = Counter(
    "scorecode_http_requests_total",
    "HTTP requests",
    ["route_class", "method", "status"],
)
HTTP_LATENCY = Histogram(
    "scorecode_http_request_duration_seconds",
    "HTTP request latency",
    ["route_class"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.15, 0.25, 0.5, 1, 2.5, 5, 10),
)
CACHE_EVENTS = Counter("scorecode_cache_events_total", "Cache hits/misses/errors", ["cache", "event"])
LOGINS = Counter("scorecode_logins_total", "Login attempts", ["realm", "outcome"])
ARGON2_WAIT = Histogram(
    "scorecode_argon2_semaphore_wait_seconds",
    "Time spent waiting for a password-hashing slot",
    buckets=(0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
JOBS = Counter("scorecode_jobs_total", "Background jobs processed", ["queue", "kind", "outcome"])
JOB_DURATION = Histogram(
    "scorecode_job_duration_seconds",
    "Background job duration",
    ["queue", "kind"],
    buckets=(0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
RATE_LIMITED = Counter("scorecode_rate_limited_total", "Requests rejected by rate limiting", ["bucket"])
SIGNUP_TRAPPED = Counter(
    "scorecode_signup_honeypot_total", "Sign-ups dropped because the hidden form field was filled"
)
DB_POOL_EXHAUSTED = Counter(
    "scorecode_db_pool_exhausted_total", "Requests answered 503 because no database connection came free"
)
DB_UNAVAILABLE = Counter(
    "scorecode_db_unavailable_total", "Requests answered 503 because the database was unreachable"
)
BREACH_CHECKS = Counter("scorecode_breached_password_checks_total", "Breached-password lookups", ["outcome"])
WORKER_ACTIVE = Gauge("scorecode_worker_active_jobs", "Jobs currently executing in this worker")
# Exported by every worker every 15 s from jobs_stats() (the same totals from each; alert on max()).
JOBS_BY_STATUS = Gauge(
    "scorecode_jobs_in_state",
    "Jobs by queue and status (queued = due now, not scheduled)",
    ["queue", "status"],
)
EMAILS = Counter("scorecode_emails_total", "Emails handed to the SMTP provider", ["outcome"])
# Institutions at or above 90% of a plan limit (students, staff, storage...): set by a maintenance task.
TENANTS_NEAR_LIMIT = Gauge(
    "scorecode_tenants_near_limit",
    "Institutions using at least 90% of a plan limit",
    ["limit"],
    multiprocess_mode="max",
)
PURGED = Counter("scorecode_purged_rows_total", "Rows removed by the retention purge", ["table"])
MAINTENANCE_LAST = Gauge(
    "scorecode_maintenance_last_success_timestamp_seconds", "When the retention purge last completed"
)
JOBS_OLDEST = Gauge(
    "scorecode_jobs_oldest_seconds", "Age of the oldest job in that queue and status", ["queue", "status"]
)


def route_class(path: str) -> str:
    """Low-cardinality grouping of routes for RED metrics."""
    if path.startswith("/api/v1/me/results"):
        return "student_read"
    if path.startswith(("/api/v1/auth/login", "/api/v1/platform/auth/login")):
        return "login"
    if path.startswith(("/api/v1/verify", "/v/")):
        return "verify"
    if path.startswith("/api/v1/platform"):
        return "platform"
    if path.startswith("/api/v1/tenant/config"):
        return "config"
    if path.startswith("/api/v1/me"):
        return "me"
    if path.startswith("/api/v1"):
        return "admin"
    return "other"
