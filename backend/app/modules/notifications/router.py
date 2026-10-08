"""The signed-in person's inbox and notification preferences (P12.1, P12.3).

Personal data: always ``no-store``. Every query is limited to the session's own user, so a notification id
from someone else is simply "not found".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict

from app.core.http import InfraDep, Principal, UoW, require
from app.modules.notifications.service import Notifier

router = APIRouter(prefix="/api/v1/me", tags=["notifications"])
NO_STORE = "private, no-store"


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: Literal["result_published", "result_revised"]
    title: str
    body: str
    link: str | None
    created_at: datetime
    read: bool


class InboxOut(BaseModel):
    items: list[NotificationOut]
    unread: int
    next_before: datetime | None


class UnreadOut(BaseModel):
    unread: int


class ReadAllOut(BaseModel):
    updated: int


class OkOut(BaseModel):
    ok: bool = True


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_results: bool


class PreferencesOut(BaseModel):
    email_results: bool


@router.get("/notifications")
async def my_notifications(
    response: Response,
    uow: UoW,
    before: datetime | None = None,
    limit: int = Query(20, ge=1, le=50),
    principal: Principal = require(),
) -> InboxOut:
    response.headers["Cache-Control"] = NO_STORE
    items, unread = await Notifier.inbox(uow, principal, before=before, limit=limit)
    return InboxOut(
        items=[
            NotificationOut(
                id=n.id,
                kind=n.kind,
                title=n.title,
                body=n.body,
                link=n.link,
                created_at=n.created_at,
                read=n.read_at is not None,
            )
            for n in items
        ],
        unread=unread,
        next_before=items[-1].created_at if len(items) == limit else None,
    )


@router.get("/notifications/unread-count")
async def my_unread_count(response: Response, uow: UoW, principal: Principal = require()) -> UnreadOut:
    response.headers["Cache-Control"] = NO_STORE
    return UnreadOut(unread=await Notifier.unread(uow, principal))


@router.post("/notifications/read-all")
async def read_all(uow: UoW, principal: Principal = require()) -> ReadAllOut:
    return ReadAllOut(updated=await Notifier.mark_all_read(uow, principal))


@router.post("/notifications/{notification_id}/read")
async def read_one(notification_id: uuid.UUID, uow: UoW, principal: Principal = require()) -> OkOut:
    await Notifier.mark_read(uow, principal, notification_id)
    return OkOut()


@router.get("/preferences")
async def my_preferences(response: Response, uow: UoW, principal: Principal = require()) -> PreferencesOut:
    response.headers["Cache-Control"] = NO_STORE
    return PreferencesOut(email_results=await Notifier.email_preference(uow, principal))


@router.put("/preferences")
async def set_preferences(
    body: PreferencesIn, uow: UoW, infra: InfraDep, principal: Principal = require()
) -> PreferencesOut:
    return PreferencesOut(
        email_results=await Notifier.set_email_preference(uow, principal, body.email_results)
    )
