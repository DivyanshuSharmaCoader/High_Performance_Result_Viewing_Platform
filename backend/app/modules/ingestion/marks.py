"""Marks import profile (P8.5, docs/13 §2 and §4).

One profile instance per exam: its columns come from the exam's papers and components.

File shapes it understands:
* **single paper** — the import targets one paper: a column per component (``Internal``, ``EXT``…);
* **long** — one row per student × paper, with a course-code column and component columns;
* **wide** — one row per student, columns ``<COURSE>_<COMPONENT>`` (``UCS301_INT``) for each paper.

Columns that aren't in the file leave the existing marks alone, so internal marks can be uploaded before
the externals. Attendance codes (AB, EX, MP, WH) can be typed in a mark cell or an attendance column.
"""

from __future__ import annotations

import difflib
import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from sqlalchemy import select

from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import InvalidState
from app.core.sql import in_rows
from app.modules.academics.models import Cohort, Course
from app.modules.audit.service import Actor, record
from app.modules.directory.models import CohortMembership, Student
from app.modules.examinations.models import (
    ExamCohort,
    Examination,
    ExamPaper,
    PaperAssignment,
    PaperSubmission,
)
from app.modules.ingestion.engine import FieldSpec, Issue, RowInput, RowResult, suggest
from app.modules.ingestion.values import is_mangled_number
from app.modules.marks.models import MarkEntry
from app.modules.tenancy.models import TenantSettings

DEFAULT_CODES = {"AB": "absent", "EX": "exempt", "MP": "malpractice", "WH": "withheld"}
ATTENDANCE_WORDS = {
    "absent": "absent",
    "abs": "absent",
    "a": "absent",
    "exempt": "exempt",
    "exempted": "exempt",
    "malpractice": "malpractice",
    "ufm": "malpractice",
    "withheld": "withheld",
    "present": "present",
    "p": "present",
}
ROSTER_STATUSES = ("active", "graduated")
WRITE_STATES_ADMIN = ("marks_entry_open", "marks_entry_closed")


@dataclass(frozen=True)
class PaperRef:
    id: uuid.UUID
    course_code: str
    components: tuple[dict[str, Any], ...]  # {"code", "label", "max", "min_pass"}

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(c["code"] for c in self.components)


@dataclass(frozen=True)
class StudentRef:
    id: uuid.UUID
    enrollment_no: str
    full_name: str
    cohort_id: uuid.UUID | None  # the exam cohort the student sits with; None = not sitting this exam


@dataclass
class MarksContext:
    exam_status: str
    papers: dict[str, PaperRef]  # by upper-case course code
    students: dict[str, StudentRef]
    existing: dict[tuple[uuid.UUID, uuid.UUID], tuple[dict[str, str], str, int]] = field(default_factory=dict)
    submissions: dict[tuple[uuid.UUID, uuid.UUID], str] = field(default_factory=dict)
    allowed: set[tuple[uuid.UUID, uuid.UUID]] | None = None  # None = may write any paper × cohort
    codes: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CODES))
    single: PaperRef | None = None
    roster: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)  # cohort → students
    cohort_codes: dict[uuid.UUID, str] = field(default_factory=dict)


def norm_enrollment(value: str) -> str:
    return "".join(value.split()).upper()


def _name_key(value: str) -> str:
    return " ".join(re.sub(r"[^a-z ]", " ", value.lower()).split())


def names_disagree(in_file: str, roster: str) -> bool:
    """Flags shifted rows (a classic spreadsheet error) without nagging about initials or spelling."""
    a, b = _name_key(in_file), _name_key(roster)
    if not a or not b or a == b:
        return False
    if set(a.split()) & set(b.split()):
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() < 0.6


class MarksProfile:
    kind: ClassVar[str] = "marks"

    def __init__(self, infra: Infra | None, papers: list[PaperRef], single: PaperRef | None) -> None:
        self.infra = infra
        self.papers = papers
        self.single = single
        fields: list[FieldSpec] = [
            FieldSpec(
                "enrollment_no",
                "Enrollment no.",
                required=True,
                aliases=(
                    "enrollment",
                    "enrolment",
                    "enrollment number",
                    "roll no",
                    "roll number",
                    "roll",
                    "reg no",
                    "registration no",
                    "admission no",
                    "student id",
                ),
            ),
            FieldSpec(
                "full_name", "Name (to cross-check)", aliases=("name", "student name", "name of student")
            ),
            FieldSpec("attendance", "Attendance", aliases=("status", "present absent", "remarks")),
            FieldSpec(
                "total", "Total (to cross-check)", aliases=("total", "grand total", "marks obtained total")
            ),
        ]
        if single is None:
            fields.append(
                FieldSpec(
                    "course",
                    "Course code",
                    aliases=("course", "course code", "subject", "subject code", "paper", "paper code"),
                )
            )
        seen: set[str] = set()
        scope = [single] if single else papers
        for p in scope:
            for c in p.components:
                if c["code"] in seen:
                    continue
                seen.add(c["code"])
                extra = ("marks", "score", "marks obtained") if single and len(single.components) == 1 else ()
                fields.append(FieldSpec(f"c:{c['code']}", c["label"], aliases=(c["code"], *extra)))
        if single is None:
            for p in papers:
                for c in p.components:
                    names = [
                        f"{p.course_code}_{c['code']}",
                        f"{p.course_code} {c['code']}",
                        f"{p.course_code} {c['label']}",
                    ]
                    if len(p.components) == 1:
                        names.append(p.course_code)
                    fields.append(
                        FieldSpec(
                            f"w:{p.course_code}:{c['code']}",
                            f"{p.course_code} {c['label']}",
                            aliases=tuple(names),
                        )
                    )
        self.fields = tuple(fields)

    def missing_fields(self, mapping: dict[str, int]) -> list[str]:
        missing = []
        if "enrollment_no" not in mapping:
            missing.append("enrollment_no")
        long_cols = [k for k in mapping if k.startswith("c:")]
        wide_cols = [k for k in mapping if k.startswith("w:")]
        if not long_cols and not wide_cols:
            first = next((f.key for f in self.fields if f.key.startswith(("c:", "w:"))), None)
            if first:
                missing.append(first)
        elif long_cols and self.single is None and "course" not in mapping and not wide_cols:
            missing.append("course")
        return missing

    # ---- validation (pure) ----------------------------------------------------------------------
    def validate(
        self, rows: list[RowInput], ctx: MarksContext
    ) -> tuple[list[RowResult], list[Issue], dict[str, Any]]:
        file_issues: list[Issue] = []
        if ctx.exam_status not in WRITE_STATES_ADMIN or (
            ctx.allowed is not None and ctx.exam_status != "marks_entry_open"
        ):
            file_issues.append(
                Issue(
                    "EXAM_NOT_OPEN",
                    "error",
                    "This exam isn't taking marks right now (marks entry isn't open).",
                )
            )
        sitting = sorted(s.enrollment_no for s in ctx.students.values() if s.cohort_id is not None)
        first_seen: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
        counts = {"create": 0, "update": 0, "unchanged": 0}
        touched: dict[uuid.UUID, set[uuid.UUID]] = {}  # paper → students in the file
        shape = "single" if self.single else "long"
        results: list[RowResult] = []
        for row in rows:
            issues: list[Issue] = []
            v = row.values
            raw_enrollment = v.get("enrollment_no", "")
            enrollment = norm_enrollment(raw_enrollment)
            out: dict[str, Any] = {"enrollment_no": enrollment, "items": []}
            student: StudentRef | None = None
            if not enrollment:
                issues.append(
                    Issue("MISSING_VALUE", "error", "Enrollment number is missing.", "enrollment_no")
                )
            elif is_mangled_number(raw_enrollment):
                issues.append(
                    Issue(
                        "MANGLED_NUMBER",
                        "error",
                        f"“{raw_enrollment}” was shortened by Excel into scientific notation. Format the column as Text.",
                        "enrollment_no",
                    )
                )
            else:
                student = ctx.students.get(enrollment)
                if student is None:
                    hint = suggest(enrollment, sitting)
                    issues.append(
                        Issue(
                            "UNKNOWN_STUDENT",
                            "error",
                            f"Enrollment no. {enrollment} not found."
                            + (f" Did you mean {hint}?" if hint else ""),
                            "enrollment_no",
                        )
                    )
                elif student.cohort_id is None:
                    issues.append(
                        Issue(
                            "STUDENT_NOT_IN_EXAM",
                            "error",
                            f"{enrollment} ({student.full_name}) isn't in a cohort sitting this exam.",
                            "enrollment_no",
                        )
                    )
                    student = None
            if student is not None:
                out["student_id"] = str(student.id)
                out["cohort_id"] = str(student.cohort_id)
                given_name = v.get("full_name", "").strip()
                if given_name and names_disagree(given_name, student.full_name):
                    issues.append(
                        Issue(
                            "NAME_MISMATCH",
                            "warning",
                            f"The file says “{given_name}” but {enrollment} is {student.full_name}. Check the rows aren't shifted.",
                            "full_name",
                        )
                    )

            # Which papers does this row carry marks for?
            items: list[tuple[PaperRef, dict[str, str], str]] = []  # paper, {code: raw}, field prefix
            wide = {k: val for k, val in v.items() if k.startswith("w:")}
            if wide:
                shape = "wide"
                for p in self.papers:
                    cells = {
                        c: wide.get(f"w:{p.course_code}:{c}", "")
                        for c in p.codes
                        if f"w:{p.course_code}:{c}" in wide
                    }
                    if cells and any(x.strip() for x in cells.values()):
                        items.append((p, cells, f"w:{p.course_code}:"))
            else:
                cells = {k[2:]: val for k, val in v.items() if k.startswith("c:")}
                if self.single is not None:
                    items.append((self.single, {c: cells[c] for c in self.single.codes if c in cells}, "c:"))
                else:
                    course_raw = v.get("course", "").strip()
                    paper = ctx.papers.get(" ".join(course_raw.split()).upper())
                    if not course_raw:
                        issues.append(Issue("MISSING_VALUE", "error", "Course code is missing.", "course"))
                    elif paper is None:
                        hint = suggest(" ".join(course_raw.split()).upper(), sorted(ctx.papers))
                        issues.append(
                            Issue(
                                "PAPER_NOT_IN_EXAM",
                                "error",
                                f"“{course_raw}” isn't a paper in this exam."
                                + (f" Did you mean {hint}?" if hint else ""),
                                "course",
                            )
                        )
                    else:
                        extra = [c for c, val in cells.items() if val.strip() and c not in paper.codes]
                        if extra:
                            issues.append(
                                Issue(
                                    "UNKNOWN_COMPONENT",
                                    "error",
                                    f"{paper.course_code} has no {', '.join(extra)} component.",
                                    f"c:{extra[0]}",
                                )
                            )
                        items.append((paper, {c: cells[c] for c in paper.codes if c in cells}, "c:"))
            if not items and student is not None and not any(i.severity == "error" for i in issues):
                issues.append(Issue("NO_MARKS", "warning", "This row has no marks; it will be skipped."))

            row_attendance = v.get("attendance", "").strip()
            for paper, cells, prefix in items:
                item_issues, item = self._item(
                    paper, cells, prefix, row_attendance, v.get("total", ""), student, ctx
                )
                issues.extend(item_issues)
                if student is None or item is None:
                    continue
                key = (paper.id, student.id)
                if key in first_seen:
                    issues.append(
                        Issue(
                            "DUPLICATE_IN_FILE",
                            "error",
                            f"{enrollment} / {paper.course_code} is also on row {first_seen[key]}.",
                            "enrollment_no",
                        )
                    )
                    continue
                first_seen[key] = row.row_no
                touched.setdefault(paper.id, set()).add(student.id)
                out["items"].append(item)
            result = RowResult(row.row_no, row.cells, out, issues)
            if result.status != "error":
                for item in out["items"]:
                    counts[item["action"]] += 1
            results.append(result)

        # Students sitting the exam (and in scope) with no row for a paper that is in the file.
        by_paper = {p.id: p for p in self.papers}
        for paper_id, students in touched.items():
            paper = by_paper.get(paper_id)
            if paper is None:
                continue
            for cohort_id, members in ctx.roster.items():
                if ctx.allowed is not None and (paper_id, cohort_id) not in ctx.allowed:
                    continue
                missing = members - students
                if missing and members & students:
                    file_issues.append(
                        Issue(
                            "MISSING_STUDENTS",
                            "warning",
                            f"{len(missing)} student(s) in {ctx.cohort_codes.get(cohort_id, '?')} have no marks for {paper.course_code} in this file.",
                        )
                    )
        summary = {
            **counts,
            "shape": shape,
            "papers": sorted({by_paper[p].course_code for p in touched if p in by_paper}),
        }
        return results, file_issues, summary

    def _item(
        self,
        paper: PaperRef,
        cells: dict[str, str],
        prefix: str,
        row_attendance: str,
        total_raw: str,
        student: StudentRef | None,
        ctx: MarksContext,
    ) -> tuple[list[Issue], dict[str, Any] | None]:
        issues: list[Issue] = []
        comps = {c["code"]: c for c in paper.components}
        attendance = "present"
        if row_attendance:
            word = row_attendance.strip().lower()
            attendance = ctx.codes.get(row_attendance.strip().upper()) or ATTENDANCE_WORDS.get(word, "")
            if not attendance:
                issues.append(
                    Issue(
                        "UNKNOWN_CODE", "error", f"“{row_attendance}” isn't an attendance code.", "attendance"
                    )
                )
                attendance = "present"
        values: dict[str, str] = {}
        for code, raw in cells.items():
            text = raw.strip()
            if not text:
                continue
            special = ctx.codes.get(text.upper())
            if special:
                attendance = special
                continue
            try:
                num = Decimal(text.replace(",", ""))
            except InvalidOperation:
                issues.append(
                    Issue(
                        "NOT_A_NUMBER",
                        "error",
                        f"{paper.course_code} {comps[code]['label']}: “{text}” isn't a number.",
                        prefix + code if prefix == "c:" else f"{prefix}{code}",
                    )
                )
                continue
            maximum = Decimal(comps[code]["max"])
            if not num.is_finite() or num < 0 or num > maximum:
                issues.append(
                    Issue(
                        "OUT_OF_RANGE",
                        "error",
                        f"{paper.course_code} {comps[code]['label']}: {text} is outside 0–{maximum.normalize():f}.",
                        f"{prefix}{code}",
                    )
                )
                continue
            if num.as_tuple().exponent < -2:  # type: ignore[operator]
                issues.append(
                    Issue(
                        "INVALID_PRECISION",
                        "error",
                        f"{paper.course_code} {comps[code]['label']}: use at most two decimals.",
                        f"{prefix}{code}",
                    )
                )
                continue
            values[code] = format(num.normalize(), "f")
        if attendance != "present" and values:
            issues.append(
                Issue(
                    "ABSENT_WITH_MARKS",
                    "error",
                    f"{paper.course_code}: marked {attendance} but has marks. Clear the marks or the code.",
                    f"{prefix}{next(iter(values))}",
                )
            )
        if student is None or any(i.severity == "error" for i in issues):
            return issues, None
        cohort_id = student.cohort_id
        assert cohort_id is not None
        if ctx.allowed is not None and (paper.id, cohort_id) not in ctx.allowed:
            issues.append(
                Issue(
                    "NOT_ASSIGNED",
                    "error",
                    f"You aren't assigned to {paper.course_code} for this student's cohort.",
                )
            )
            return issues, None
        status = ctx.submissions.get((paper.id, cohort_id), "open")
        if status == "locked" or (ctx.allowed is not None and status == "submitted"):
            issues.append(
                Issue(
                    "PAPER_LOCKED",
                    "error",
                    f"{paper.course_code} for this cohort is {status}; its marks can't change.",
                )
            )
            return issues, None
        existing = ctx.existing.get((paper.id, student.id))
        merged = dict(existing[0]) if existing and existing[1] == "present" else {}
        if attendance == "present":
            merged.update(values)
        else:
            merged = {}
        if attendance == "present":
            blank = [comps[c]["label"] for c in cells if c not in merged]
            if blank:
                issues.append(
                    Issue(
                        "MISSING_MARK",
                        "warning",
                        f"{paper.course_code}: no mark for {', '.join(blank)}.",
                        f"{prefix}{next(c for c in cells if c not in merged)}",
                    )
                )
            if total_raw.strip() and all(c in merged for c in paper.codes):
                try:
                    stated = Decimal(total_raw.strip())
                    computed = sum((Decimal(x) for x in merged.values()), Decimal(0))
                    if stated != computed:
                        parts = " + ".join(merged[c] for c in paper.codes)
                        working = (
                            f"{parts} = {computed.normalize():f}"
                            if len(paper.codes) > 1
                            else f"the mark {parts}"
                        )
                        issues.append(
                            Issue(
                                "TOTAL_MISMATCH",
                                "warning",
                                f"{paper.course_code}: the file's total {total_raw.strip()} ≠ {working}.",
                                "total",
                            )
                        )
                except InvalidOperation:
                    pass
        action = "create"
        if existing is not None:
            before = (existing[0] if existing[1] == "present" else {}, existing[1])
            if before == (merged, attendance):
                action = "unchanged"
            else:
                action = "update"
                diff = ", ".join(
                    f"{c} {before[0].get(c, '—')} → {merged.get(c, '—')}"
                    for c in paper.codes
                    if before[0].get(c) != merged.get(c)
                )
                issues.append(
                    Issue(
                        "OVERWRITES_EXISTING",
                        "info",
                        f"{paper.course_code}: " + (diff or f"{before[1]} → {attendance}"),
                    )
                )
        item = {
            "paper_id": str(paper.id),
            "course_code": paper.course_code,
            "attendance": attendance,
            "components": merged,
            "action": action,
            "version": existing[2] if existing else None,
        }
        return issues, item

    # ---- database -------------------------------------------------------------------------------
    async def load_context(self, uow: UnitOfWork, params: dict[str, Any]) -> MarksContext:
        exam_id = uuid.UUID(params["exam_id"])
        exam = (await uow.session.scalars(select(Examination).where(Examination.id == exam_id))).one()
        settings = (await uow.session.scalars(select(TenantSettings))).one()
        codes = {k.upper(): v for k, v in (settings.special_codes or DEFAULT_CODES).items()}
        cohort_rows = (
            await uow.session.execute(
                select(Cohort.id, Cohort.code)
                .join(ExamCohort, ExamCohort.cohort_id == Cohort.id)
                .where(ExamCohort.exam_id == exam.id)
            )
        ).all()
        cohort_codes: dict[uuid.UUID, str] = dict(cohort_rows)
        roster: dict[uuid.UUID, set[uuid.UUID]] = {cid: set() for cid in cohort_codes}
        sitting: dict[uuid.UUID, uuid.UUID] = {}
        for sid, cid in (
            await uow.session.execute(
                select(CohortMembership.student_id, CohortMembership.cohort_id)
                .join(Student, Student.id == CohortMembership.student_id)
                .where(
                    CohortMembership.cohort_id.in_(list(cohort_codes)), Student.status.in_(ROSTER_STATUSES)
                )
            )
        ).all():
            roster[cid].add(sid)
            sitting[sid] = cid
        students = {
            s.enrollment_no: StudentRef(s.id, s.enrollment_no, s.full_name, sitting.get(s.id))
            for s in (await uow.session.scalars(select(Student))).all()
        }
        existing = {
            (e.exam_paper_id, e.student_id): (dict(e.components), e.attendance, e.version)
            for e in (await uow.session.scalars(select(MarkEntry).where(MarkEntry.exam_id == exam.id))).all()
        }
        submissions = {
            (s.exam_paper_id, s.cohort_id): s.status
            for s in (
                await uow.session.scalars(select(PaperSubmission).where(PaperSubmission.exam_id == exam.id))
            ).all()
        }
        allowed = None
        actor_id = params.get("actor_id")
        if params.get("scope") == "assigned" and actor_id:
            allowed = {
                (a.exam_paper_id, a.cohort_id)
                for a in (
                    await uow.session.scalars(
                        select(PaperAssignment).where(
                            PaperAssignment.exam_id == exam.id, PaperAssignment.user_id == uuid.UUID(actor_id)
                        )
                    )
                ).all()
            }
        return MarksContext(
            exam_status=exam.status,
            papers={p.course_code.upper(): p for p in self.papers},
            students=students,
            existing=existing,
            submissions=submissions,
            allowed=allowed,
            codes=codes,
            single=self.single,
            roster=roster,
            cohort_codes=cohort_codes,
        )

    async def commit(
        self,
        uow: UnitOfWork,
        actor: Actor,
        job_id: uuid.UUID,
        params: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Write the checked marks in one transaction. Anything that changed since the check (a mark saved in
        the grid meanwhile, entry closed, a paper submitted) refuses the whole commit; re-check and retry."""
        ctx = await self.load_context(uow, params)
        if ctx.exam_status not in WRITE_STATES_ADMIN or (
            ctx.allowed is not None and ctx.exam_status != "marks_entry_open"
        ):
            raise InvalidState("Marks entry closed after the file was checked.")
        items = [(r, i) for r in rows for i in r.get("items", [])]
        keys = [(uuid.UUID(i["paper_id"]), uuid.UUID(r["student_id"])) for r, i in items]
        locked = (
            {
                (e.exam_paper_id, e.student_id): e
                for e in (
                    await uow.session.scalars(
                        select(MarkEntry)
                        .where(in_rows((MarkEntry.exam_paper_id, MarkEntry.student_id), keys))
                        .with_for_update()
                    )
                ).all()
            }
            if keys
            else {}
        )
        exam_id = uuid.UUID(params["exam_id"])
        tenant_id = uow.require_tenant()
        created = updated = unchanged = 0
        per_paper: dict[str, int] = {}
        papers = {p.id: p for p in self.papers}
        for r, item in items:
            paper_id, student_id = uuid.UUID(item["paper_id"]), uuid.UUID(r["student_id"])
            cohort_id = uuid.UUID(r["cohort_id"])
            if ctx.allowed is not None and (paper_id, cohort_id) not in ctx.allowed:
                raise InvalidState("A paper in this file is no longer assigned to you.")
            status = ctx.submissions.get((paper_id, cohort_id), "open")
            if status == "locked" or (ctx.allowed is not None and status == "submitted"):
                raise InvalidState(f"{item['course_code']} was {status} after the file was checked.")
            entry = locked.get((paper_id, student_id))
            if (entry.version if entry else None) != item["version"]:
                raise InvalidState(
                    f"Marks for {r['enrollment_no']} / {item['course_code']} changed after the file was checked. Check the file again."
                )
            if item["action"] == "unchanged":
                unchanged += 1
                continue
            comps = item["components"]
            paper = papers[paper_id]
            total = None
            if item["attendance"] == "present" and all(c in comps for c in paper.codes):
                total = sum((Decimal(x) for x in comps.values()), Decimal(0))
            if entry is None:
                uow.session.add(
                    MarkEntry(
                        tenant_id=tenant_id,
                        exam_id=exam_id,
                        exam_paper_id=paper_id,
                        cohort_id=cohort_id,
                        student_id=student_id,
                        components=comps,
                        total=total,
                        attendance=item["attendance"],
                        version=1,
                        source=f"import:{job_id}",
                        updated_by=actor.id,
                    )
                )
                created += 1
            else:
                entry.components, entry.total, entry.attendance = comps, total, item["attendance"]
                entry.version += 1
                entry.source, entry.updated_by = f"import:{job_id}", actor.id
                updated += 1
            per_paper[item["course_code"]] = per_paper.get(item["course_code"], 0) + 1
        await uow.flush()
        summary = {"created": created, "updated": updated, "unchanged": unchanged, "papers": per_paper}
        await record(
            uow,
            actor,
            "marks.imported",
            entity_type="exam",
            entity_id=exam_id,
            summary=f"Imported marks: {created} new, {updated} changed",
            after={**summary, "import_id": str(job_id)},
        )
        return summary


async def paper_refs(uow: UnitOfWork, exam_id: uuid.UUID) -> list[PaperRef]:
    rows = (
        await uow.session.execute(
            select(ExamPaper, Course.code)
            .join(Course, Course.id == ExamPaper.course_id)
            .where(ExamPaper.exam_id == exam_id)
            .order_by(ExamPaper.position, Course.code)
        )
    ).all()
    return [PaperRef(p.id, code.upper(), tuple(p.components)) for p, code in rows]
