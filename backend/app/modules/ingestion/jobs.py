"""Background handlers for the ``imports`` queue."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from app.core.container import Infra
from app.core.jobs import JobContext, maintenance_task, registry
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


# Retention (docs/10 §12): an uploaded spreadsheet holds student data or marks. Its stored object goes
# 30 days after every import that used it ended, like the staging rows (ops_purge). The file row stays,
# marked purged, because imports reference it.
_STALE_UPLOADS = text(
    """
    SELECT f.id, f.object_key FROM files f
     WHERE f.kind = 'import' AND f.purged_at IS NULL
       AND EXISTS (SELECT 1 FROM import_jobs j WHERE j.file_id = f.id)
       AND NOT EXISTS (
           SELECT 1 FROM import_jobs j
            WHERE j.file_id = f.id
              AND (j.status NOT IN ('committed', 'failed', 'cancelled') OR j.updated_at >= now() - interval '30 days'))
    """
)


@maintenance_task
async def purge_import_files(infra: Infra) -> dict[str, int]:
    removed = 0
    async with infra.db.uow() as uow:
        tenant_ids = (await uow.session.scalars(text("SELECT * FROM ops_tenant_ids()"))).all()
    for tenant_id in tenant_ids:
        async with infra.db.uow(tenant_id) as uow:
            for row in (await uow.session.execute(_STALE_UPLOADS)).all():
                await infra.storage.delete(row.object_key)  # idempotent: a retry after a failure is fine
                await uow.session.execute(
                    text("UPDATE files SET purged_at = now() WHERE id = :id"), {"id": row.id}
                )
                removed += 1
    return {"import_files": removed}
