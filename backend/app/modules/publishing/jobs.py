"""Background handler for the ``publishing`` queue."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.jobs import JobContext, registry
from app.modules.publishing.service import PublishingService


@registry.register("publishing.go_live", queue="publishing", max_attempts=5)
async def go_live(ctx: JobContext) -> dict[str, Any]:
    if ctx.job.tenant_id is None:
        raise RuntimeError("publishing is tenant-scoped")
    return await PublishingService(ctx.infra).go_live(
        ctx.job.tenant_id, uuid.UUID(ctx.job.payload["publication_id"])
    )
