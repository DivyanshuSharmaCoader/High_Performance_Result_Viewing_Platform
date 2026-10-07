"""Background handler for the ``processing`` queue."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.jobs import JobContext, registry
from app.modules.results.service import ResultsService


@registry.register("results.process", queue="processing", max_attempts=3)
async def process_results(ctx: JobContext) -> dict[str, Any]:
    if ctx.job.tenant_id is None:
        raise RuntimeError("result processing is tenant-scoped")
    return await ResultsService(ctx.infra).execute(
        ctx.job.tenant_id,
        uuid.UUID(ctx.job.payload["run_id"]),
        final_attempt=ctx.job.attempts >= ctx.job.max_attempts,
    )
