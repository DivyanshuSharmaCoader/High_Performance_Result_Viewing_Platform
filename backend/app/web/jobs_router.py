"""``GET /api/v1/jobs/{id}`` — progress polling for long operations (docs/09 §8; polling, not WebSockets)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.errors import NotFound
from app.core.http import Principal, UoW, require
from app.core.jobs import get_job_status
from app.modules.identity.permissions import P

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


class JobOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    progress: dict[str, Any] | None
    result: dict[str, Any] | None
    error: str | None
    attempts: int
    created_at: datetime | None
    finished_at: datetime | None


@router.get("/{job_id}")
async def job_status(job_id: uuid.UUID, uow: UoW, principal: Principal = require(P.JOBS_VIEW)) -> JobOut:
    status = await get_job_status(uow, job_id)
    # Staff without admin rights may only follow jobs they started.
    if status is None or (not principal.has(P.IMPORTS_MANAGE) and status.created_by != principal.user_id):
        raise NotFound("Job not found")
    return JobOut(
        id=status.id,
        kind=status.kind,
        status=status.status,
        progress=status.progress,
        result=status.result,
        error=status.error,
        attempts=status.attempts,
        created_at=status.created_at,
        finished_at=status.finished_at,
    )
