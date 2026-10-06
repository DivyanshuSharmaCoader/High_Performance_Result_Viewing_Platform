"""Student activation codes (P6.7, docs/10 §2).

A code is shown exactly once — in the response that creates it — and only its keyed hash is stored
(bound to tenant + enrollment number, so a code is useless anywhere else). Nothing with plaintext codes is
written to storage or the audit log; if slips are lost, issuing again replaces the old codes.

Issuing creates the student's login (``users`` row, ``status='invited'``, no password) if it doesn't exist.
The student sets a password on the activation page and is signed in.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import NotFound, ValidationFailed
from app.core.http import Principal
from app.core.security import human_code
from app.modules.academics.models import AcademicSession, Cohort
from app.modules.audit.service import Actor, record
from app.modules.directory.models import CohortMembership, Student
from app.modules.identity.models import AuthToken, User, UserRole
from app.modules.identity.service import ACTIVATION_TTL, activation_token_hash, normalise_login_id

MAX_PER_REQUEST = 2_000
CAN_ACTIVATE = ("active", "graduated")


def format_code(code: str) -> str:
    """``ABCDE12345`` → ``ABCDE-12345`` (easier to read off a slip)."""
    return f"{code[:5]}-{code[5:]}"


@dataclass(frozen=True)
class IssuedCode:
    student_id: uuid.UUID
    enrollment_no: str
    full_name: str
    cohort_code: str | None
    code: str
    expires_at: datetime


@dataclass(frozen=True)
class Skipped:
    student_id: uuid.UUID
    enrollment_no: str
    full_name: str
    reason: str  # already_active | has_code | not_active_student


class ActivationService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    async def issue(
        self,
        uow: UnitOfWork,
        principal: Principal,
        *,
        cohort_id: uuid.UUID | None,
        student_ids: Sequence[uuid.UUID],
        replace_existing: bool,
    ) -> tuple[list[IssuedCode], list[Skipped], str | None]:
        if (cohort_id is None) == (not student_ids):
            raise ValidationFailed("Choose a cohort or a list of students.", field="cohort_id")
        tenant_id = uow.require_tenant()
        cohort_label = None
        if cohort_id is not None:
            cohort = (await uow.session.scalars(select(Cohort).where(Cohort.id == cohort_id))).one_or_none()
            if cohort is None:
                raise NotFound("Cohort not found")
            cohort_label = cohort.code
            stmt = (
                select(Student)
                .join(CohortMembership, CohortMembership.student_id == Student.id)
                .where(CohortMembership.cohort_id == cohort.id)
            )
        else:
            stmt = select(Student).where(Student.id.in_(list(dict.fromkeys(student_ids))))
        students = list(
            (
                await uow.session.scalars(stmt.order_by(Student.enrollment_no).with_for_update(of=Student))
            ).all()
        )
        if cohort_id is None and len(students) != len(set(student_ids)):
            raise NotFound("Some of those students weren't found")
        if len(students) > MAX_PER_REQUEST:
            raise ValidationFailed(f"Issue codes for at most {MAX_PER_REQUEST:,} students at a time.")
        cohort_of = (
            {s.id: cohort_label or "" for s in students}
            if cohort_id is not None
            else await self._current_cohorts(uow, [s.id for s in students])
        )

        users = {
            u.id: u
            for u in (
                await uow.session.scalars(
                    select(User)
                    .where(User.id.in_([s.user_id for s in students if s.user_id]))
                    .with_for_update()
                )
            ).all()
        }
        pending = set(
            (
                await uow.session.scalars(
                    select(AuthToken.user_id).where(
                        AuthToken.user_id.in_(list(users)),
                        AuthToken.purpose == "activation",
                        AuthToken.consumed_at.is_(None),
                        AuthToken.expires_at > utcnow(),
                    )
                )
            ).all()
        )

        issued: list[IssuedCode] = []
        skipped: list[Skipped] = []
        now = utcnow()
        expires = now + ACTIVATION_TTL
        for s in students:
            user = users.get(s.user_id) if s.user_id else None
            reason = None
            if s.status not in CAN_ACTIVATE:
                reason = "not_active_student"
            elif user is not None and user.status != "invited":
                reason = "already_active" if user.status == "active" else "not_active_student"
            elif user is not None and user.id in pending and not replace_existing:
                reason = "has_code"
            if reason:
                skipped.append(Skipped(s.id, s.enrollment_no, s.full_name, reason))
                continue
            if user is None:
                user = User(
                    tenant_id=tenant_id,
                    kind="student",
                    login_id=normalise_login_id(s.enrollment_no),
                    email=s.email,
                    full_name=s.full_name,
                    status="invited",
                )
                uow.session.add(user)
                await uow.flush()
                uow.session.add(UserRole(tenant_id=tenant_id, user_id=user.id, role="student"))
                s.user_id = user.id
            else:
                await uow.session.execute(
                    update(AuthToken)
                    .where(
                        AuthToken.user_id == user.id,
                        AuthToken.purpose == "activation",
                        AuthToken.consumed_at.is_(None),
                    )
                    .values(consumed_at=now)
                )
            code = human_code(10)
            uow.session.add(
                AuthToken(
                    tenant_id=tenant_id,
                    user_id=user.id,
                    purpose="activation",
                    token_hash=activation_token_hash(tenant_id, user.login_id, code),
                    expires_at=expires,
                    created_by=principal.user_id,
                )
            )
            issued.append(
                IssuedCode(
                    s.id, s.enrollment_no, s.full_name, cohort_of.get(s.id), format_code(code), expires
                )
            )
        await uow.flush()
        if issued:
            await record(
                uow,
                Actor.from_principal(principal),
                "activation_codes.issued",
                entity_type="cohort" if cohort_id else "student",
                entity_id=cohort_id if cohort_id else (issued[0].student_id if len(issued) == 1 else None),
                summary=f"Issued {len(issued)} activation code(s)"
                + (f" for {cohort_label}" if cohort_label else ""),
                after={"issued": len(issued), "skipped": len(skipped), "replaced": replace_existing},
            )
        return issued, skipped, cohort_label

    async def _current_cohorts(self, uow: UnitOfWork, student_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        rows = await uow.session.execute(
            select(CohortMembership.student_id, Cohort.code)
            .join(Cohort, Cohort.id == CohortMembership.cohort_id)
            .join(AcademicSession, AcademicSession.id == CohortMembership.session_id)
            .where(CohortMembership.student_id.in_(student_ids))
            .order_by(AcademicSession.is_current.desc(), AcademicSession.starts_on.desc())
        )
        out: dict[uuid.UUID, str] = {}
        for sid, code in rows.all():
            out.setdefault(sid, code)
        return out
