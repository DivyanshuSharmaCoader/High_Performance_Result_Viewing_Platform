"""Student import profile (P6.6, docs/13 §4).

Rows are matched to existing students by enrollment number. ``mode="upsert"`` (default) updates the
fields present in the file; ``mode="create_only"`` skips students who already exist. An optional cohort
column (cohort codes of the chosen session) places students in cohorts, moving them out of sibling
cohorts of the same program. Blank optional cells never erase existing data.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, ClassVar

from sqlalchemy import delete, select, tuple_

from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import InvalidState, ValidationFailed
from app.modules.academics.models import AcademicSession, Cohort
from app.modules.audit.service import Actor, record
from app.modules.directory.models import CohortMembership, Student
from app.modules.directory.service import ENROLLMENT_RE
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EntitlementService
from app.modules.identity.models import User
from app.modules.ingestion.engine import FieldSpec, Issue, RowInput, RowResult, suggest
from app.modules.ingestion.values import (
    is_mangled_number,
    looks_like_formula,
    parse_date,
    parse_email,
    parse_phone,
    parse_year,
)

OPTIONAL = ("email", "phone", "date_of_birth", "guardian_name", "admission_year")
UPDATABLE = ("full_name", *OPTIONAL)


@dataclass(frozen=True)
class Existing:
    id: uuid.UUID
    status: str
    fields: dict[str, Any]


@dataclass(frozen=True)
class CohortRef:
    id: uuid.UUID
    code: str
    archived: bool


@dataclass
class StudentsContext:
    existing: dict[str, Existing]
    cohorts: dict[str, CohortRef]  # normalised code → cohort in the chosen session
    session_code: str | None
    remaining: int | None  # free max_students seats; None = unlimited
    mode: str = "upsert"


def norm_code(value: str) -> str:
    return " ".join(value.split()).upper()


def norm_enrollment(value: str) -> str:
    return "".join(value.split()).upper()


class StudentsProfile:
    kind: ClassVar[str] = "students"

    def __init__(self, infra: Infra | None = None) -> None:
        self.infra = infra  # only the database steps need it; validation is pure

    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "enrollment_no",
            "Enrollment no.",
            required=True,
            aliases=(
                "enrollment",
                "enrolment",
                "enrolment no",
                "enrollment number",
                "enrolment number",
                "roll no",
                "roll number",
                "roll",
                "reg no",
                "registration no",
                "registration number",
                "admission no",
                "admission number",
                "student id",
                "scholar no",
            ),
            help="Unique per student; becomes their login.",
            example="102303001",
        ),
        FieldSpec(
            "full_name",
            "Full name",
            required=True,
            aliases=("name", "student name", "name of student", "student", "candidate name"),
            example="Aarav Gupta",
        ),
        FieldSpec(
            "first_name", "First name", aliases=("given name", "fname"), help="Used if there's no full name"
        ),
        FieldSpec("last_name", "Last name", aliases=("surname", "family name", "lname")),
        FieldSpec(
            "email",
            "Email",
            aliases=("email address", "e-mail", "email id", "mail"),
            example="aarav@example.com",
        ),
        FieldSpec("phone", "Phone", aliases=("mobile", "mobile no", "phone number", "contact", "contact no")),
        FieldSpec(
            "date_of_birth",
            "Date of birth",
            aliases=("dob", "birth date", "d.o.b", "date of birth (dd/mm/yyyy)"),
            help="DD/MM/YYYY or YYYY-MM-DD",
            example="14/03/2005",
        ),
        FieldSpec(
            "guardian_name",
            "Guardian name",
            aliases=("father name", "father's name", "fathers name", "parent name", "guardian", "parent"),
        ),
        FieldSpec(
            "admission_year",
            "Admission year",
            aliases=("year of admission", "admitted", "admission"),
            example="2023",
        ),
        FieldSpec(
            "cohort",
            "Cohort",
            aliases=("cohort code", "section", "class", "class section", "group", "batch"),
            help="Cohort code in the chosen session",
            example="CSE-G1",
        ),
    )

    def _infra(self) -> Infra:
        if self.infra is None:
            raise RuntimeError("StudentsProfile needs the infra container for database steps")
        return self.infra

    def missing_fields(self, mapping: dict[str, int]) -> list[str]:
        missing = []
        if "enrollment_no" not in mapping:
            missing.append("enrollment_no")
        if "full_name" not in mapping and not ("first_name" in mapping and "last_name" in mapping):
            missing.append("full_name")
        return missing

    # ---- validation (pure) ----------------------------------------------------------------------
    def validate(
        self, rows: list[RowInput], ctx: StudentsContext
    ) -> tuple[list[RowResult], list[Issue], dict[str, Any]]:
        results: list[RowResult] = []
        first_seen: dict[str, int] = {}
        cohort_codes = sorted(c.code for c in ctx.cohorts.values() if not c.archived)
        counts = {"create": 0, "update": 0, "unchanged": 0, "skip": 0}
        cohort_column_used = False
        for row in rows:
            v = row.values
            issues: list[Issue] = []
            out: dict[str, Any] = {}

            raw_enrollment = v.get("enrollment_no", "")
            enrollment = norm_enrollment(raw_enrollment)
            if not enrollment:
                issues.append(
                    Issue("MISSING_VALUE", "error", "Enrollment number is missing.", "enrollment_no")
                )
            elif is_mangled_number(raw_enrollment):
                issues.append(
                    Issue(
                        "MANGLED_NUMBER",
                        "error",
                        f"“{raw_enrollment}” was shortened by Excel into scientific notation, so digits are lost. "
                        "Format the column as Text in Excel and export again.",
                        "enrollment_no",
                    )
                )
            elif not ENROLLMENT_RE.match(enrollment):
                issues.append(
                    Issue(
                        "INVALID_FORMAT",
                        "error",
                        f"“{raw_enrollment}” isn't a valid enrollment number (letters, digits and / . _ - only).",
                        "enrollment_no",
                    )
                )
            elif enrollment in first_seen:
                issues.append(
                    Issue(
                        "DUPLICATE_IN_FILE",
                        "error",
                        f"Enrollment number {enrollment} is also on row {first_seen[enrollment]}.",
                        "enrollment_no",
                    )
                )
            else:
                first_seen[enrollment] = row.row_no
            out["enrollment_no"] = enrollment

            name = " ".join(v.get("full_name", "").split())
            if not name:
                name = " ".join(f"{v.get('first_name', '')} {v.get('last_name', '')}".split())
            if not name:
                issues.append(Issue("MISSING_VALUE", "error", "Name is missing.", "full_name"))
            out["full_name"] = name[:200] or None
            for key, text in (("full_name", name), ("guardian_name", v.get("guardian_name", ""))):
                if looks_like_formula(text):
                    issues.append(
                        Issue(
                            "FORMULA_LIKE",
                            "warning",
                            f"“{text[:40]}” looks like a spreadsheet formula. It will be stored as plain text.",
                            key,
                        )
                    )

            email, problem = parse_email(v.get("email", ""))
            if problem:
                issues.append(Issue("INVALID_EMAIL", "error", problem, "email"))
            out["email"] = email

            phone, problem = parse_phone(v.get("phone", ""))
            if problem:
                issues.append(Issue("INVALID_PHONE", "warning", problem, "phone"))
            out["phone"] = phone

            dob, problem = parse_date(v.get("date_of_birth", ""))
            if problem:
                issues.append(Issue("INVALID_DATE", "error", problem, "date_of_birth"))
            elif dob and not date(1900, 1, 1) <= dob <= date.today():
                issues.append(
                    Issue(
                        "IMPLAUSIBLE_DATE",
                        "error",
                        f"Date of birth {dob:%d/%m/%Y} isn't plausible.",
                        "date_of_birth",
                    )
                )
                dob = None
            out["date_of_birth"] = dob.isoformat() if dob else None

            guardian = " ".join(v.get("guardian_name", "").split())
            out["guardian_name"] = guardian[:200] or None

            year, problem = parse_year(v.get("admission_year", ""))
            if problem:
                issues.append(Issue("INVALID_YEAR", "error", problem, "admission_year"))
            out["admission_year"] = year

            cohort_raw = v.get("cohort", "")
            out["cohort_id"] = None
            if cohort_raw:
                cohort_column_used = True
                code = norm_code(cohort_raw)
                ref = ctx.cohorts.get(code)
                if ctx.session_code is None:
                    issues.append(
                        Issue(
                            "NO_SESSION",
                            "error",
                            "Choose an academic session to place students in cohorts.",
                            "cohort",
                        )
                    )
                elif ref is None:
                    hint = suggest(code, cohort_codes)
                    issues.append(
                        Issue(
                            "UNKNOWN_COHORT",
                            "error",
                            f"Cohort “{cohort_raw}” doesn't exist in {ctx.session_code}."
                            + (f" Did you mean {hint}?" if hint else ""),
                            "cohort",
                        )
                    )
                elif ref.archived:
                    issues.append(
                        Issue("ARCHIVED_COHORT", "error", f"Cohort {ref.code} is archived.", "cohort")
                    )
                else:
                    out["cohort_id"] = str(ref.id)
                    out["cohort_code"] = ref.code

            # What committing this row would do.
            action = "create"
            existing = ctx.existing.get(enrollment) if enrollment else None
            if existing is not None:
                if ctx.mode == "create_only":
                    action = "skip"
                    issues.append(
                        Issue(
                            "ALREADY_EXISTS",
                            "warning",
                            f"{enrollment} already exists and will be skipped (create-only import).",
                            "enrollment_no",
                        )
                    )
                else:
                    changes = {
                        f: [_show(existing.fields.get(f)), _show(out.get(f))]
                        for f in UPDATABLE
                        if out.get(f) is not None and _show(existing.fields.get(f)) != _show(out.get(f))
                    }
                    action = "update" if changes or out["cohort_id"] else "unchanged"
                    if changes:
                        out["changes"] = changes
                        issues.append(
                            Issue(
                                "OVERWRITES_EXISTING",
                                "info",
                                "Updates "
                                + ", ".join(
                                    f"{k.replace('_', ' ')}: {a or '—'} → {b}"
                                    for k, (a, b) in changes.items()
                                ),
                            )
                        )
                    if existing.status != "active":
                        issues.append(
                            Issue(
                                "NOT_ACTIVE",
                                "warning",
                                f"{enrollment} is {existing.status}; the import updates the record but doesn't reactivate it.",
                                "enrollment_no",
                            )
                        )
            out["action"] = action
            result = RowResult(row.row_no, row.cells, out, issues)
            if result.status != "error":
                counts[action] += 1
            results.append(result)

        file_issues: list[Issue] = []
        if ctx.remaining is not None and counts["create"] > ctx.remaining:
            file_issues.append(
                Issue(
                    "LIMIT_EXCEEDED",
                    "error",
                    f"This file adds {counts['create']:,} new students, but your plan has room for "
                    f"{max(ctx.remaining, 0):,} more. Archive students who have left or upgrade your plan.",
                )
            )
        summary = {
            **counts,
            "session_code": ctx.session_code,
            "cohort_column": cohort_column_used,
            "seats_remaining": ctx.remaining,
            "mode": ctx.mode,
        }
        return results, file_issues, summary

    # ---- database -------------------------------------------------------------------------------
    async def load_context(self, uow: UnitOfWork, params: dict[str, Any]) -> StudentsContext:
        session_code = None
        cohorts: dict[str, CohortRef] = {}
        session_id = params.get("session_id")
        stmt = select(AcademicSession)
        stmt = (
            stmt.where(AcademicSession.id == uuid.UUID(str(session_id)))
            if session_id
            else stmt.where(AcademicSession.is_current.is_(True))
        )
        session = (await uow.session.scalars(stmt)).one_or_none()
        if session is not None:
            session_code = session.code
            for c in (await uow.session.scalars(select(Cohort).where(Cohort.session_id == session.id))).all():
                cohorts[norm_code(c.code)] = CohortRef(c.id, c.code, c.archived_at is not None)
        existing = {
            s.enrollment_no: Existing(
                s.id,
                s.status,
                {f: getattr(s, f) for f in UPDATABLE},
            )
            for s in (await uow.session.scalars(select(Student))).all()
        }
        service = EntitlementService(self._infra())
        limit = (await service.effective(uow)).limit(F.MAX_STUDENTS)
        remaining = None
        if limit is not None:
            remaining = limit - (await service.usage(uow)).get("active_students", 0)
        return StudentsContext(existing, cohorts, session_code, remaining, params.get("mode", "upsert"))

    async def commit(
        self,
        uow: UnitOfWork,
        actor: Actor,
        job_id: uuid.UUID,
        params: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Apply staged rows in the caller's transaction. Re-reads students under lock so a student created
        since validation is updated rather than duplicated, and re-checks cohorts and the seat limit."""
        tenant_id = uow.require_tenant()
        by_enrollment = {r["enrollment_no"]: r for r in rows if r.get("action") != "skip"}
        locked = {
            s.enrollment_no: s
            for s in (
                await uow.session.scalars(
                    select(Student).where(Student.enrollment_no.in_(list(by_enrollment))).with_for_update()
                )
            ).all()
        }
        mode = params.get("mode", "upsert")
        to_create = [r for e, r in by_enrollment.items() if e not in locked]
        to_update = (
            [] if mode == "create_only" else [(locked[e], r) for e, r in by_enrollment.items() if e in locked]
        )
        if to_create:
            await EntitlementService(self._infra()).consume(uow, F.MAX_STUDENTS, len(to_create))

        created: list[Student] = []
        for r in to_create:
            s = Student(
                tenant_id=tenant_id,
                status="active",
                enrollment_no=r["enrollment_no"],
                **_fields(r, fill=True),
            )
            created.append(s)
        uow.session.add_all(created)
        updated = 0
        renamed_accounts: list[Student] = []
        for s, r in to_update:
            changed = False
            for f, value in _fields(r, fill=False).items():
                if value is not None and getattr(s, f) != value:
                    setattr(s, f, value)
                    changed = True
            if changed:
                s.version += 1
                updated += 1
                if s.user_id is not None:
                    renamed_accounts.append(s)
        await uow.flush()
        for s in renamed_accounts:
            user = (await uow.session.scalars(select(User).where(User.id == s.user_id))).one()
            user.full_name, user.email = s.full_name, s.email

        placed, moved = await self._place_in_cohorts(
            uow, tenant_id, [*created, *(s for s, _ in to_update)], by_enrollment
        )
        summary = {
            "created": len(created),
            "updated": updated,
            "unchanged": len(to_update) - updated,
            "skipped": len(rows) - len(to_create) - len(to_update),
            "placed_in_cohorts": placed,
            "moved_between_cohorts": moved,
        }
        await record(
            uow,
            actor,
            "import.committed",
            entity_type="import",
            entity_id=job_id,
            summary=f"Student import: {len(created)} added, {updated} updated",
            after=summary,
        )
        return summary

    async def _place_in_cohorts(
        self, uow: UnitOfWork, tenant_id: uuid.UUID, students: list[Student], rows: dict[str, dict[str, Any]]
    ) -> tuple[int, int]:
        target: dict[uuid.UUID, uuid.UUID] = {}
        for s in students:
            cid = rows[s.enrollment_no].get("cohort_id")
            if cid:
                target[s.id] = uuid.UUID(cid)
        if not target:
            return 0, 0
        cohorts = {
            c.id: c
            for c in (
                await uow.session.scalars(select(Cohort).where(Cohort.id.in_(set(target.values()))))
            ).all()
        }
        for cid in set(target.values()):
            c = cohorts.get(cid)
            if c is None or c.archived_at is not None:
                raise InvalidState(
                    "A cohort in this file was archived or removed after the file was checked. Re-check the import."
                )
        current: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], uuid.UUID] = {}
        keys = {(sid, cohorts[cid].session_id, cohorts[cid].program_id) for sid, cid in target.items()}
        if keys:
            for m in (
                await uow.session.scalars(
                    select(CohortMembership).where(
                        tuple_(
                            CohortMembership.student_id,
                            CohortMembership.session_id,
                            CohortMembership.program_id,
                        ).in_(list(keys))
                    )
                )
            ).all():
                current[(m.student_id, m.session_id, m.program_id)] = m.cohort_id
        remove: list[tuple[uuid.UUID, uuid.UUID]] = []
        add: list[CohortMembership] = []
        moved = 0
        by_cohort: dict[uuid.UUID, int] = defaultdict(int)
        for sid, cid in target.items():
            c = cohorts[cid]
            existing = current.get((sid, c.session_id, c.program_id))
            if existing == cid:
                continue
            if existing is not None:
                remove.append((sid, existing))
                moved += 1
            add.append(
                CohortMembership(
                    tenant_id=tenant_id,
                    cohort_id=cid,
                    student_id=sid,
                    session_id=c.session_id,
                    program_id=c.program_id,
                )
            )
            by_cohort[cid] += 1
        if remove:
            await uow.session.execute(
                delete(CohortMembership).where(
                    tuple_(CohortMembership.student_id, CohortMembership.cohort_id).in_(remove)
                )
            )
        uow.session.add_all(add)
        await uow.flush()
        return len(add), moved


def _show(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _fields(row: dict[str, Any], *, fill: bool) -> dict[str, Any]:
    out: dict[str, Any] = {"full_name": row.get("full_name")}
    for f in OPTIONAL:
        value = row.get(f)
        if f == "date_of_birth" and value:
            value = date.fromisoformat(value)
        out[f] = value
    if not out["full_name"]:
        raise ValidationFailed("A row without a name reached commit.")
    return out if fill else {k: v for k, v in out.items() if v is not None}
