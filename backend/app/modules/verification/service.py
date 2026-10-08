"""Public verification of issued marksheets (docs/03 W13, docs/10 §10; P11.4–P11.5).

A lookup goes in two steps. A SECURITY DEFINER function maps the code to its tenant, and nothing else. The
record is then read under that tenant's row-level security, like any other request. What a verifier
learns is the institution, the exam, the issue date, the document hash and the status, with the student
masked. Marks are never shown.

Status (derived; see ``models``):

=================  ===========================================================
``valid``          the publication is live and the record isn't revoked
``superseded``     a revised result was published (date of the revision)
``withdrawn``      the institution withdrew the results (date)
``revoked``        this one record was revoked (date; the reason stays private)
not found          unknown code, or a publication that never went live
=================  ===========================================================
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, text, update

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import InvalidState, NotFound
from app.core.http import Principal
from app.modules.audit.service import Actor, record
from app.modules.documents.models import MarksheetDocument
from app.modules.identity.service import AuthService
from app.modules.publishing.models import Publication, PublishedResult
from app.modules.tenancy.models import Tenant
from app.modules.verification.codes import grouped, mask_identifier, mask_name, normalize
from app.modules.verification.models import VerificationRecord

GONE_STATUSES = ("closing", "closed")  # the institution has left: nothing about its students is shown


@dataclass(frozen=True)
class Verification:
    code: str
    status: str  # valid | superseded | withdrawn | revoked | institution_left
    status_at: datetime | None
    institution: str
    exam: str
    term: str
    session: str
    issued_at: datetime | None
    version: int
    student_name: str
    enrollment_no: str
    document_sha256: str | None
    timezone: str = "Asia/Kolkata"


class VerificationService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    async def lookup(self, raw_code: str) -> Verification | None:
        code = normalize(raw_code)
        if code is None:
            return None
        async with self.infra.db.uow() as uow:
            found = (
                await uow.session.execute(
                    text("SELECT tenant_id, tenant_status FROM verification_lookup(:code)"), {"code": code}
                )
            ).one_or_none()
        if found is None:
            return None
        tenant_id, tenant_status = found
        async with self.infra.db.uow(tenant_id) as uow:
            row = (
                await uow.session.execute(
                    select(VerificationRecord, Publication, PublishedResult.payload, MarksheetDocument.sha256)
                    .join(Publication, Publication.id == VerificationRecord.publication_id)
                    .join(
                        PublishedResult,
                        (PublishedResult.publication_id == VerificationRecord.publication_id)
                        & (PublishedResult.student_id == VerificationRecord.student_id),
                    )
                    .outerjoin(
                        MarksheetDocument,
                        (MarksheetDocument.publication_id == VerificationRecord.publication_id)
                        & (MarksheetDocument.student_id == VerificationRecord.student_id),
                    )
                    .where(VerificationRecord.code == code)
                )
            ).one_or_none()
            if row is None:
                return None
            rec, pub, payload, sha256 = row
            if pub.status in ("scheduled", "cancelled"):
                return None  # never issued: indistinguishable from an unknown code
            status, status_at = await self._status(uow, rec, pub)
            timezone = (await uow.session.scalars(select(Tenant.timezone))).one()
            await uow.session.execute(
                update(VerificationRecord)
                .where(VerificationRecord.code == code)
                .values(verify_count=VerificationRecord.verify_count + 1, last_verified_at=utcnow())
            )
        if tenant_status in GONE_STATUSES:
            return Verification(
                code=grouped(code),
                status="institution_left",
                status_at=None,
                institution=payload["institution"]["display_name"],
                exam="",
                term="",
                session="",
                issued_at=None,
                version=pub.version,
                student_name="",
                enrollment_no="",
                document_sha256=None,
            )
        exam = payload["exam"]
        return Verification(
            code=grouped(code),
            status=status,
            status_at=status_at,
            institution=payload["institution"]["display_name"],
            exam=exam["name"],
            term=exam["term"],
            session=exam["session"],
            issued_at=pub.published_at,
            version=pub.version,
            student_name=mask_name(payload["student"]["full_name"]),
            enrollment_no=mask_identifier(payload["student"]["enrollment_no"]),
            document_sha256=sha256,
            timezone=timezone,
        )

    @staticmethod
    async def _status(
        uow: UnitOfWork, rec: VerificationRecord, pub: Publication
    ) -> tuple[str, datetime | None]:
        if rec.revoked_at is not None:
            return "revoked", rec.revoked_at
        if pub.status == "withdrawn":
            return "withdrawn", pub.withdrawn_at
        if pub.status == "superseded":
            revised = await uow.session.scalar(
                select(Publication.published_at).where(Publication.supersedes_id == pub.id)
            )
            return "superseded", revised
        return "valid", pub.published_at

    # ---- for the student and administrators ---------------------------------------------------------
    @staticmethod
    async def code_for(uow: UnitOfWork, publication_id: uuid.UUID, student_id: uuid.UUID) -> str | None:
        return (
            await uow.session.scalars(
                select(VerificationRecord.code).where(
                    VerificationRecord.publication_id == publication_id,
                    VerificationRecord.student_id == student_id,
                )
            )
        ).one_or_none()

    async def revoke(
        self,
        uow: UnitOfWork,
        principal: Principal,
        publication_id: uuid.UUID,
        student_id: uuid.UUID,
        reason: str,
    ) -> VerificationRecord:
        """Revoke one issued marksheet (an error or fraud affecting one student). Not reversible: issue a
        corrected result instead."""
        AuthService(self.infra).require_recent_auth(principal)
        rec = (
            await uow.session.scalars(
                select(VerificationRecord)
                .where(
                    VerificationRecord.publication_id == publication_id,
                    VerificationRecord.student_id == student_id,
                )
                .with_for_update()
            )
        ).one_or_none()
        if rec is None:
            raise NotFound("There's no marksheet for this student in this publication.")
        if rec.revoked_at is not None:
            raise InvalidState("This marksheet is already revoked.")
        rec.revoked_at, rec.revoked_reason, rec.revoked_by = utcnow(), reason.strip(), principal.user_id
        await uow.flush()
        await record(
            uow,
            Actor.from_principal(principal),
            "verification.revoked",
            entity_type="student",
            entity_id=student_id,
            summary="Marksheet verification revoked",
            after={"publication_id": str(publication_id)},
            reason=reason.strip(),
        )
        return rec
