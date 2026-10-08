"""Background handler for the ``pdf`` queue."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.jobs import JobContext, registry
from app.modules.documents.service import MarksheetService


@registry.register("documents.render", queue="pdf", max_attempts=3)
async def render_marksheets(ctx: JobContext) -> dict[str, Any]:
    if ctx.job.tenant_id is None:
        raise RuntimeError("marksheets are tenant-scoped")
    return await MarksheetService(ctx.infra).render(
        ctx.job.tenant_id,
        uuid.UUID(ctx.job.payload["publication_id"]),
        [uuid.UUID(s) for s in ctx.job.payload["students"]],
        final_attempt=ctx.job.attempts >= ctx.job.max_attempts,
    )
