"""Telling students their results are out (docs/03 W11; P12.1–P12.3).

* ``publication_live`` (job, ``notifications`` queue) runs once a publication is visible: "publish now", or
  a scheduled one going live. It writes one inbox row per student with an account (idempotent through
  ``dedupe_key``). If the institution emails on publish, the plan includes it and the student hasn't opted
  out, it also queues a delivery and send jobs in batches.
* ``send_batch`` (job) sends a batch over the mail adapter at a bounded rate. Each delivery is retried by
  the job; after the last attempt it's ``failed``. The address is read from the account at send time.
* Emails carry a link, never marks (docs/03 W11).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

import anyio
from sqlalchemy import Table, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import NotFound
from app.core.http import Principal
from app.core.ids import uuid7
from app.core.jobs import enqueue
from app.core.logging import get_logger
from app.modules.branding.models import TenantBranding
from app.modules.directory.models import Student
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EntitlementService
from app.modules.examinations.models import Examination
from app.modules.identity.models import User
from app.modules.notifications import budget
from app.modules.notifications.emails import render
from app.modules.notifications.models import Notification, NotificationDelivery
from app.modules.publishing.changes import changed_students
from app.modules.publishing.models import Publication, PublishedResult
from app.modules.tenancy.models import Tenant, TenantSettings

log = get_logger("scorecode.notifications")

EMAIL_BATCH = 50
INSERT_CHUNK = 1000
NOTIFICATIONS = cast(Table, Notification.__table__)
DELIVERIES = cast(Table, NotificationDelivery.__table__)


def publication_key(publication_id: uuid.UUID) -> str:
    return f"publication:{publication_id}"


@dataclass(frozen=True)
class DeliveryCounts:
    queued: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0


class Notifier:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    # ---- fan-out --------------------------------------------------------------------------------
    @staticmethod
    async def schedule_publication(uow: UnitOfWork, publication_id: uuid.UUID) -> None:
        """Called in the transaction that makes a publication live."""
        await enqueue(
            uow,
            "notifications.publication_live",
            {"publication_id": str(publication_id)},
            dedupe_key=f"notify:{publication_id}",
        )

    async def publication_live(self, tenant_id: uuid.UUID, publication_id: uuid.UUID) -> dict[str, Any]:
        async with self.infra.db.uow(tenant_id) as uow:
            row = (
                await uow.session.execute(
                    select(Publication, Examination.name)
                    .join(Examination, Examination.id == Publication.exam_id)
                    .where(Publication.id == publication_id)
                )
            ).one()
            pub, exam_name = row
            if pub.status != "published":
                return {"skipped": pub.status}  # withdrawn (or replaced) before we got here
            revised = pub.version > 1
            query = (
                select(User.id, User.email, User.notify_email)
                .join(Student, Student.user_id == User.id)
                .join(
                    PublishedResult,
                    (PublishedResult.student_id == Student.id)
                    & (PublishedResult.publication_id == publication_id),
                )
                .where(User.status == "active")
            )
            if pub.supersedes_id is not None:
                # A correction replacing a live version: tell only the students whose result changed.
                changed = await changed_students(uow, publication_id, pub.supersedes_id)
                query = query.where(Student.id.in_(changed))
            recipients = (await uow.session.execute(query)).all()
            link = f"/me/results/{publication_id}"
            title = (
                f"Your {exam_name} result was revised" if revised else f"{exam_name} results are available"
            )
            body = (
                "Your institution issued a revised result. Open it to see the latest version."
                if revised
                else "Your result and marksheet are ready."
            )
            key = publication_key(publication_id)
            rows = [
                {
                    "id": uuid7(),
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "publication_id": publication_id,
                    "kind": "result_revised" if revised else "result_published",
                    "title": title[:200],
                    "body": body,
                    "link": link,
                    "dedupe_key": key,
                }
                for user_id, _, _ in recipients
            ]
            for i in range(0, len(rows), INSERT_CHUNK):
                await uow.session.execute(
                    pg_insert(NOTIFICATIONS).values(rows[i : i + INSERT_CHUNK]).on_conflict_do_nothing()
                )
            emails = await self._emails_wanted(uow)
            queued = 0
            if emails:
                notified = dict(
                    (
                        await uow.session.execute(
                            select(Notification.user_id, Notification.id).where(
                                Notification.publication_id == publication_id
                            )
                        )
                    ).all()
                )
                wanted = [
                    {"id": uuid7(), "tenant_id": tenant_id, "notification_id": notified[u], "user_id": u}
                    for u, email, opted_in in recipients
                    if email and opted_in and u in notified
                ]
                for i in range(0, len(wanted), INSERT_CHUNK):
                    await uow.session.execute(
                        pg_insert(DELIVERIES).values(wanted[i : i + INSERT_CHUNK]).on_conflict_do_nothing()
                    )
                pending = list(
                    (
                        await uow.session.scalars(
                            select(NotificationDelivery.id)
                            .join(Notification, Notification.id == NotificationDelivery.notification_id)
                            .where(
                                Notification.publication_id == publication_id,
                                NotificationDelivery.status == "queued",
                            )
                            .order_by(NotificationDelivery.id)
                        )
                    ).all()
                )
                for i in range(0, len(pending), EMAIL_BATCH):
                    await enqueue(
                        uow,
                        "notifications.send_batch",
                        {"deliveries": [str(d) for d in pending[i : i + EMAIL_BATCH]]},
                        dedupe_key=f"emails:{publication_id}:{i // EMAIL_BATCH}",
                    )
                queued = len(pending)
        return {"notified": len(rows), "emails_queued": queued}

    async def _emails_wanted(self, uow: UnitOfWork) -> bool:
        settings = (await uow.session.scalars(select(TenantSettings.publish_notify_email))).one()
        if not settings:
            return False
        ent = await EntitlementService(self.infra).effective(uow, fresh=True)
        return ent.has(F.EMAIL_NOTIFICATIONS)

    async def send_batch(
        self, tenant_id: uuid.UUID, delivery_ids: Sequence[uuid.UUID], *, final_attempt: bool
    ) -> dict[str, Any]:
        async with self.infra.db.uow(tenant_id) as uow:
            work = (
                await uow.session.execute(
                    select(
                        NotificationDelivery.id,
                        Notification,
                        Examination.name,
                        User.email,
                        User.notify_email,
                        User.status,
                    )
                    .join(Notification, Notification.id == NotificationDelivery.notification_id)
                    .join(Publication, Publication.id == Notification.publication_id)
                    .join(Examination, Examination.id == Publication.exam_id)
                    .join(User, User.id == NotificationDelivery.user_id)
                    .where(
                        NotificationDelivery.id.in_(delivery_ids),
                        NotificationDelivery.status.in_(("queued", "failed")),
                    )
                    .order_by(NotificationDelivery.id)
                )
            ).all()
            context = await self._context(uow)
        sent = failed = skipped = 0
        gap = 1 / max(self.infra.settings.mail_rate_per_second, 0.1)
        for n, (delivery_id, note, exam_name, email, opted_in, status) in enumerate(work):
            if not email or not opted_in or status != "active":
                await self._mark(tenant_id, delivery_id, status="skipped")
                skipped += 1
                continue
            until = await budget.take(self.infra, bulk=True)
            if until is not None:
                # The day's email budget is spent: the rest stay queued (the publish screen shows them as
                # waiting) and a new batch picks them up when the budget frees up. Students see their
                # results in the portal meanwhile; only the email waits.
                rest = [str(w[0]) for w in work[n:]]
                if until - note.created_at > timedelta(hours=self.infra.settings.mail_notice_max_delay_hours):
                    # A notice days late helps no one: these are skipped, recorded as such.
                    for w in work[n:]:
                        await self._mark(tenant_id, w[0], status="skipped", error="daily-limit")
                    log.warning("notification_emails_skipped_daily_limit", skipped=len(rest))
                    return {"sent": sent, "failed": failed, "skipped": skipped + len(rest)}
                async with self.infra.db.uow(tenant_id) as uow:
                    await enqueue(uow, "notifications.send_batch", {"deliveries": rest}, run_at=until)
                log.warning("notification_emails_deferred_daily_limit", deferred=len(rest))
                return {"sent": sent, "failed": failed, "skipped": skipped, "deferred": len(rest),
                        "deferred_until": until.isoformat()}  # fmt: skip
            if n:
                await anyio.sleep(gap)
            template = note.kind  # the inbox kind names its email template
            params = {
                **context,
                "to": email,
                "exam_name": exam_name,
                "action_url": f"{context['origin']}{note.link}",
            }
            try:
                message_id = await self.infra.mailer.send(render(template, params))
            except Exception as exc:
                failed += 1
                log.warning("notification_email_failed", error_code=type(exc).__name__)
                await self._mark(
                    tenant_id,
                    delivery_id,
                    status="failed" if final_attempt else "queued",
                    error=type(exc).__name__,
                )
                continue
            await self._mark(tenant_id, delivery_id, status="sent", message_id=message_id)
            sent += 1
        if failed and not final_attempt:
            raise RuntimeError(f"{failed} of {len(work)} emails failed; the job will retry them")
        return {"sent": sent, "failed": failed, "skipped": skipped}

    async def _context(self, uow: UnitOfWork) -> dict[str, Any]:
        slug = (await uow.session.scalars(select(Tenant.slug))).one()
        brand = (await uow.session.scalars(select(TenantBranding))).one_or_none()
        settings = (await uow.session.scalars(select(TenantSettings.official_name))).one()
        return {
            "institution": brand.display_name if brand else settings,
            "brand_color": brand.primary_color if brand else "#2952cc",
            "origin": self.infra.settings.tenant_origin(slug),
        }

    async def _mark(
        self,
        tenant_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        status: str,
        error: str | None = None,
        message_id: str | None = None,
    ) -> None:
        async with self.infra.db.uow(tenant_id) as uow:
            await uow.session.execute(
                update(NotificationDelivery)
                .where(NotificationDelivery.id == delivery_id)
                .values(
                    status=status,
                    attempts=NotificationDelivery.attempts + (0 if status == "skipped" else 1),
                    last_error=error,
                    provider_message_id=message_id,
                    sent_at=utcnow() if status == "sent" else None,
                )
            )

    @staticmethod
    async def delivery_counts(
        uow: UnitOfWork, publication_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, DeliveryCounts]:
        counts: dict[uuid.UUID, dict[str, int]] = {}
        for pid, status, n in (
            await uow.session.execute(
                select(Notification.publication_id, NotificationDelivery.status, func.count())
                .join(Notification, Notification.id == NotificationDelivery.notification_id)
                .where(Notification.publication_id.in_(list(publication_ids)))
                .group_by(Notification.publication_id, NotificationDelivery.status)
            )
        ).all():
            if pid is not None:
                counts.setdefault(pid, {})[status] = n
        return {pid: DeliveryCounts(**c) for pid, c in counts.items()}

    # ---- the inbox ------------------------------------------------------------------------------
    @staticmethod
    async def inbox(
        uow: UnitOfWork, principal: Principal, *, before: datetime | None, limit: int
    ) -> tuple[list[Notification], int]:
        query = select(Notification).where(Notification.user_id == principal.user_id)
        if before is not None:
            query = query.where(Notification.created_at < before)
        items = list(
            (await uow.session.scalars(query.order_by(Notification.created_at.desc()).limit(limit))).all()
        )
        return items, await Notifier.unread(uow, principal)

    @staticmethod
    async def unread(uow: UnitOfWork, principal: Principal) -> int:
        return (
            await uow.session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == principal.user_id, Notification.read_at.is_(None))
            )
        ) or 0

    @staticmethod
    async def mark_read(uow: UnitOfWork, principal: Principal, notification_id: uuid.UUID) -> None:
        result = await uow.session.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == principal.user_id)
            .values(read_at=func.coalesce(Notification.read_at, utcnow()))
            .returning(Notification.id)
        )
        if result.first() is None:
            raise NotFound("Notification not found")

    @staticmethod
    async def mark_all_read(uow: UnitOfWork, principal: Principal) -> int:
        result = await uow.session.execute(
            update(Notification)
            .where(Notification.user_id == principal.user_id, Notification.read_at.is_(None))
            .values(read_at=utcnow())
            .returning(Notification.id)
        )
        return len(result.all())

    # ---- preferences ----------------------------------------------------------------------------
    @staticmethod
    async def set_email_preference(uow: UnitOfWork, principal: Principal, enabled: bool) -> bool:
        await uow.session.execute(
            update(User).where(User.id == principal.user_id).values(notify_email=enabled)
        )
        return enabled

    @staticmethod
    async def email_preference(uow: UnitOfWork, principal: Principal) -> bool:
        return bool(
            (await uow.session.scalars(select(User.notify_email).where(User.id == principal.user_id))).one()
        )
