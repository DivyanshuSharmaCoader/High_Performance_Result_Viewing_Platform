"""Cursor (keyset) pagination (docs/08 §5): ``?cursor=…&limit=50`` (max 200) → ``{items, next_cursor}``.

Cursors are opaque base64 JSON of the last row's sort key; keyset pagination stays fast on large tables
and is stable under concurrent inserts (unlike OFFSET).
"""

from __future__ import annotations

import base64
import json
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.core.errors import ValidationFailed

T = TypeVar("T")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    total: int | None = None


def encode_cursor(values: list[Any]) -> str:
    raw = json.dumps(values, default=str, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> list[Any] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValidationFailed("Invalid cursor.", field="cursor") from exc
    if not isinstance(value, list):
        raise ValidationFailed("Invalid cursor.", field="cursor")
    return value


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, limit))
