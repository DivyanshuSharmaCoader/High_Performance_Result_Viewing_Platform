"""Prometheus metrics (docs/14 §Q). Exposed on ``/metrics`` — internal network only (the proxy never
routes it publicly)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

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
WORKER_ACTIVE = Gauge("scorecode_worker_active_jobs", "Jobs currently executing in this worker")


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
