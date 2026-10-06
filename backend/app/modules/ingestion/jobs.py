"""Background handlers for the ``imports`` queue."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.jobs import JobContext, registry
from app.modules.ingestion.service import ImportService


def _ids(ctx: JobContext) -> tuple[uuid.UUID, uuid.UUID]:
    if ctx.job.tenant_id is None:
        raise RuntimeError("import jobs are tenant-scoped")
    return ctx.job.tenant_id, uuid.UUID(ctx.job.payload["import_id"])


@registry.register("imports.analyse", queue="imports", max_attempts=3)
async def analyse_import(ctx: JobContext) -> dict[str, Any]:
    tenant_id, import_id = _ids(ctx)
    return await ImportService(ctx.infra).run_analysis(
        tenant_id, import_id, final_attempt=ctx.job.attempts >= ctx.job.max_attempts
    )


@registry.register("imports.commit", queue="imports", max_attempts=3)
async def commit_import(ctx: JobContext) -> dict[str, Any]:
    tenant_id, import_id = _ids(ctx)
    return await ImportService(ctx.infra).run_commit(tenant_id, import_id, ctx.job.payload.get("actor_label"))
