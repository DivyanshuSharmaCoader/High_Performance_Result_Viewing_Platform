"""Background handler for data exports (P18.5)."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.jobs import JobContext, registry
from app.modules.exports.service import ExportService


@registry.register("exports.build", queue="maintenance", max_attempts=3)
async def build_export(ctx: JobContext) -> dict[str, Any]:
    if ctx.job.tenant_id is None:
        raise RuntimeError("exports are tenant-scoped")
    return await ExportService(ctx.infra).build(ctx.job.tenant_id, uuid.UUID(ctx.job.payload["export_id"]))
