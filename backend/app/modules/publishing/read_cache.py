"""Caching the student read path (P14.3; docs/11 §2.5).

Measured first: under scenario B the API is CPU-bound, and 38% of its CPU went to SQLAlchemy and asyncpg
loading the same immutable rows again and again (py-spy, benchmarks/results/2026-10-09-*). What is cached,
and why each is safe:

==========================  =====================================  ===============================================
key (always per tenant)     value                                  why it can be cached
==========================  =====================================  ===============================================
``stu:{user}``              the session's student id               a user is linked to a student once, never relinked
``live``                    published publications, newest first   changes on publish/go-live/withdraw: deleted after
                                                                   commit, and lives only 5 s anywhere else, so a
                                                                   withdrawal reaches every process within 5 s
``snap:{pub}:{student}``    the student's snapshot payload         ``published_results`` is immutable (trigger)
``stats:{pub}``             the statistics snapshot                ``exam_statistics`` is immutable (trigger)
``stats-level``             what students may see of statistics    a setting; 30 s staleness is acceptable
==========================  =====================================  ===============================================

Keys always begin with the tenant id, and student keys include the student id taken from the session, so
nothing can be read across tenants or students. ``SCORECODE_STUDENT_READ_CACHE=false`` turns it all off
(for before/after measurements and as an escape hatch).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.core.container import Infra
from app.core.db import UnitOfWork
from app.modules.directory.models import Student
from app.modules.publishing.models import ExamStatistics, Publication, PublishedResult
from app.modules.tenancy.models import TenantSettings

LIVE_TTL_S = 5
IMMUTABLE_TTL_S = 3600
IMMUTABLE_LOCAL_TTL_S = 60
STUDENT_TTL_S = 300
LEVEL_TTL_S = 30
ABSENT = {"absent": True}  # this student isn't in that publication (also immutable)


@dataclass(frozen=True)
class LivePublication:
    """What the student read path needs of a publication (the ORM row is not cached)."""

    id: uuid.UUID
    exam_id: uuid.UUID
    version: int
    published_at: datetime


def _key(tenant_id: uuid.UUID, *parts: object) -> str:
    return ":".join(["t", str(tenant_id), "reads", *(str(p) for p in parts)])


class StudentReads:
    def __init__(self, infra: Infra) -> None:
        self.cache = infra.cache
        self.enabled = infra.settings.student_read_cache

    async def student_id(self, uow: UnitOfWork, user_id: uuid.UUID) -> uuid.UUID | None:
        key = _key(uow.require_tenant(), "stu", user_id)
        hit = await self.cache.get(key, local_ttl_s=STUDENT_TTL_S) if self.enabled else None
        if hit is not None:
            return uuid.UUID(hit)
        sid = (await uow.session.scalars(select(Student.id).where(Student.user_id == user_id))).one_or_none()
        if sid is not None and self.enabled:
            await self.cache.set(key, str(sid), STUDENT_TTL_S, local_ttl_s=STUDENT_TTL_S)
        return sid

    async def live(self, uow: UnitOfWork) -> list[LivePublication]:
        key = _key(uow.require_tenant(), "live")
        hit = await self.cache.get(key, local_ttl_s=LIVE_TTL_S) if self.enabled else None
        if hit is None:
            rows = (
                await uow.session.execute(
                    select(Publication.id, Publication.exam_id, Publication.version, Publication.published_at)
                    .where(Publication.status == "published")
                    .order_by(Publication.published_at.desc(), Publication.id)
                )
            ).all()
            hit = [
                {"id": str(i), "exam_id": str(e), "version": v, "published_at": p.isoformat()}
                for i, e, v, p in rows
                if p is not None  # always set once published (check constraint)
            ]
            if self.enabled:
                await self.cache.set(key, hit, LIVE_TTL_S, local_ttl_s=LIVE_TTL_S)
        return [
            LivePublication(
                uuid.UUID(r["id"]),
                uuid.UUID(r["exam_id"]),
                r["version"],
                datetime.fromisoformat(r["published_at"]),
            )
            for r in hit
        ]

    async def payload(
        self, uow: UnitOfWork, publication_id: uuid.UUID, student_id: uuid.UUID
    ) -> dict[str, Any] | None:
        key = _key(uow.require_tenant(), "snap", publication_id, student_id)
        hit = await self.cache.get(key, local_ttl_s=IMMUTABLE_LOCAL_TTL_S) if self.enabled else None
        if hit is None:
            row = (
                await uow.session.scalars(
                    select(PublishedResult.payload).where(
                        PublishedResult.publication_id == publication_id,
                        PublishedResult.student_id == student_id,
                    )
                )
            ).one_or_none()
            hit = row if row is not None else ABSENT
            if self.enabled:
                await self.cache.set(key, hit, IMMUTABLE_TTL_S, local_ttl_s=IMMUTABLE_LOCAL_TTL_S)
        return None if hit == ABSENT else dict(hit)

    async def stats(self, uow: UnitOfWork, publication_id: uuid.UUID) -> dict[str, Any] | None:
        key = _key(uow.require_tenant(), "stats", publication_id)
        hit = await self.cache.get(key, local_ttl_s=IMMUTABLE_LOCAL_TTL_S) if self.enabled else None
        if hit is None:
            row = (
                await uow.session.scalars(
                    select(ExamStatistics.stats).where(ExamStatistics.publication_id == publication_id)
                )
            ).one_or_none()
            hit = row if row is not None else ABSENT
            if self.enabled:
                await self.cache.set(key, hit, IMMUTABLE_TTL_S, local_ttl_s=IMMUTABLE_LOCAL_TTL_S)
        return None if hit == ABSENT else dict(hit)

    async def stats_level(self, uow: UnitOfWork) -> str:
        key = _key(uow.require_tenant(), "stats-level")
        hit = await self.cache.get(key, local_ttl_s=LEVEL_TTL_S) if self.enabled else None
        if hit is None:
            hit = (await uow.session.scalars(select(TenantSettings.student_stats))).one()
            if self.enabled:
                await self.cache.set(key, hit, LEVEL_TTL_S, local_ttl_s=LEVEL_TTL_S)
        return str(hit)

    def forget_live(self, uow: UnitOfWork) -> None:
        """After the transaction that changes which publications are live commits."""
        key = _key(uow.require_tenant(), "live")
        uow.after_commit(lambda: self.cache.delete(key))

    def forget_stats_level(self, uow: UnitOfWork) -> None:
        """After the institution changes what students may see of statistics."""
        key = _key(uow.require_tenant(), "stats-level")
        uow.after_commit(lambda: self.cache.delete(key))
