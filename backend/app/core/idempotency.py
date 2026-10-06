"""Idempotency keys for retried state-changing POSTs (docs/08 §5).

Required on import commit, result processing and publication. The key row is inserted in the *same*
transaction as the work, so:

* a retry after success replays the stored response (no duplicate side effects);
* a concurrent duplicate blocks on the key's primary-key lock until the first commits, then replays;
* reusing a key with a different request body is rejected (422);
* if the work fails and rolls back, the key disappears with it and the request can be retried.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.clock import utcnow
from app.core.db import UnitOfWork
from app.core.errors import IdempotencyMismatch, ValidationFailed
from app.core.tables import IdempotencyKey

KEY_RE = re.compile(r"^[A-Za-z0-9_\-:.]{8,128}$")
TTL = timedelta(hours=24)


def request_fingerprint(method: str, path: str, body: Any) -> bytes:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{method} {path}\n{canonical}".encode()).digest()


async def idempotent[M: BaseModel](
    uow: UnitOfWork,
    request: Request,
    body: Any,
    work: Callable[[], Awaitable[M]],
    *,
    status_code: int = 200,
) -> M | JSONResponse:
    key = request.headers.get("idempotency-key", "")
    if not KEY_RE.match(key):
        raise ValidationFailed(
            "Send an Idempotency-Key header (8–128 letters, digits, '-', '_', ':' or '.') so this action "
            "is safe to retry.",
            field="Idempotency-Key",
        )
    tenant_id = uow.require_tenant()
    fingerprint = request_fingerprint(request.method, request.url.path, body)
    inserted = (
        await uow.session.execute(
            insert(IdempotencyKey)
            .values(tenant_id=tenant_id, key=key, request_hash=fingerprint, expires_at=utcnow() + TTL)
            .on_conflict_do_nothing(index_elements=["tenant_id", "key"])
            .returning(IdempotencyKey.key)
        )
    ).scalar_one_or_none()
    if inserted is None:
        existing = (
            await uow.session.scalars(
                select(IdempotencyKey).where(IdempotencyKey.tenant_id == tenant_id, IdempotencyKey.key == key)
            )
        ).one()
        if existing.request_hash != fingerprint:
            raise IdempotencyMismatch()
        if existing.response_status is not None:
            return JSONResponse(
                existing.response_body,
                status_code=existing.response_status,
                headers={"Idempotent-Replayed": "true"},
            )
        # Unreachable in practice: the conflicting row is only visible once its transaction committed,
        # and it always commits together with its stored response.
        raise IdempotencyMismatch("This request is already being processed. Retry in a moment.")
    result = await work()
    stored = (
        await uow.session.scalars(
            select(IdempotencyKey).where(IdempotencyKey.tenant_id == tenant_id, IdempotencyKey.key == key)
        )
    ).one()
    stored.response_status = status_code
    stored.response_body = result.model_dump(mode="json")
    return result
