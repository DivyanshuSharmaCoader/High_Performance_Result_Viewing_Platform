"""Worker entrypoint: consumes the PostgreSQL job queue (same image as the API, ``worker`` mode)."""

from __future__ import annotations

import asyncio
import signal

from prometheus_client import start_http_server

from app.core.config import get_settings
from app.core.container import Infra
from app.core.jobs import Worker
from app.core.logging import configure_logging, get_logger
from app.jobs_registry import load_job_handlers

log = get_logger("scorecode.worker")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, "scorecode-worker")
    load_job_handlers()
    infra = Infra.build(settings, app_name="scorecode-worker")
    worker = Worker(
        infra,
        settings.queues,
        concurrency=settings.worker_concurrency,
        poll_interval_s=settings.worker_poll_interval_s,
        lease_s=settings.job_lease_s,
    )
    if settings.metrics_enabled:
        start_http_server(9100)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop)
    try:
        await worker.run_forever()
    finally:
        await infra.close()
