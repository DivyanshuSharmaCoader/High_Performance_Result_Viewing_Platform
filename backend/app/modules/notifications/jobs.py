"""Background handlers for the ``notifications`` queue (fan-out and email batches)."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.jobs import JobContext, registry
from app.modules.notifications.service import Notifier


@registry.register("notifications.publication_live", queue="notifications", max_attempts=5)
async def publication_live(ctx: JobContext) -> dict[str, Any]:
    if ctx.job.tenant_id is None:
        raise RuntimeError("notifications are tenant-scoped")
    return await Notifier(ctx.infra).publication_live(
        ctx.job.tenant_id, uuid.UUID(ctx.job.payload["publication_id"])
    )


@registry.register("notifications.send_batch", queue="notifications", max_attempts=5)
async def send_batch(ctx: JobContext) -> dict[str, Any]:
    if ctx.job.tenant_id is None:
        raise RuntimeError("notifications are tenant-scoped")
    return await Notifier(ctx.infra).send_batch(
        ctx.job.tenant_id,
        [uuid.UUID(d) for d in ctx.job.payload["deliveries"]],
        final_attempt=ctx.job.attempts >= ctx.job.max_attempts,
    )
