"""Everything an institution has in ScoreCode, as a ZIP of CSV files (P18.5; docs/legal: no lock-in).

* The owner requests an export (re-authenticated); a job builds it under the tenant's own RLS context, so
  it can only ever contain that tenant's rows. Each file is an explicit query below: what goes out is a
  list of columns, never ``SELECT *``, so password hashes, two-step secrets, session and reset tokens,
  rate-limit and job bookkeeping never leave.
* CSVs are UTF-8 with a byte-order mark (Excel then shows Hindi and Punjabi names correctly), with JSON in
  the few columns that hold structure (mark components, grading configuration, audit before/after).
* The ZIP is a private object; downloads are signed links that expire in five minutes, each one audited.
  After seven days the object is deleted (maintenance task) and the export says "expired".
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import Conflict, InvalidState, LimitExceeded, NotFound
from app.core.http import Principal
from app.core.jobs import enqueue, maintenance_task
from app.core.logging import get_logger
from app.modules.audit.service import Actor, record
from app.modules.exports.models import DataExport
from app.modules.files.models import StoredFile
from app.modules.files.service import FileService, FileType
from app.modules.identity.service import AuthService

log = get_logger(__name__)

ZIP = FileType(".zip", "application/zip")
KEEP = timedelta(days=7)
PER_DAY = 5
LINK_TTL_S = 300

# An exam is named "academic year / term / name" in every file: s.code || ' / ' || t.code || ' / ' || e.name.

# file name → (what it holds, query). Ordered as the README lists them.
FILES: dict[str, tuple[str, str]] = {
    "institution.csv": (
        "Your institution's settings and display name.",
        """SELECT ts.official_name, b.display_name, ts.address, ts.affiliation, ts.contact_email,
                  ts.contact_phone, ts.locale, ts.approval_mode, ts.student_activation_mode, ts.student_stats
           FROM tenant_settings ts LEFT JOIN tenant_branding b ON true""",
    ),
    "academic_sessions.csv": (
        "Academic years.",
        "SELECT code, name, starts_on, ends_on, is_current, archived_at FROM academic_sessions ORDER BY starts_on",
    ),
    "terms.csv": (
        "Terms of each academic year.",
        """SELECT s.code AS session, t.code, t.name, t.sequence, t.starts_on, t.ends_on
           FROM terms t JOIN academic_sessions s ON s.id = t.session_id ORDER BY s.starts_on, t.sequence""",
    ),
    "departments.csv": ("Departments.", "SELECT code, name, archived_at FROM departments ORDER BY code"),
    "programs.csv": (
        "Programmes or streams.",
        """SELECT d.code AS department, p.code, p.name, p.level, p.duration_terms, p.archived_at
           FROM programs p LEFT JOIN departments d ON d.id = p.department_id ORDER BY p.code""",
    ),
    "cohorts.csv": (
        "Classes and sections, per academic year.",
        """SELECT s.code AS session, p.code AS program, c.code, c.name, c.archived_at
           FROM cohorts c JOIN academic_sessions s ON s.id = c.session_id JOIN programs p ON p.id = c.program_id
           ORDER BY s.starts_on, c.code""",
    ),
    "courses.csv": (
        "Subjects / courses.",
        """SELECT d.code AS department, c.code, c.name, c.credits, c.archived_at
           FROM courses c LEFT JOIN departments d ON d.id = c.department_id ORDER BY c.code""",
    ),
    "students.csv": (
        "Students and their details. has_account: whether the student has activated a sign-in.",
        """SELECT enrollment_no, full_name, date_of_birth, email, phone, guardian_name, admission_year, status,
                  user_id IS NOT NULL AS has_account, archived_at, created_at
           FROM students ORDER BY enrollment_no""",
    ),
    "cohort_memberships.csv": (
        "Which class or section each student was in, per academic year.",
        """SELECT s.code AS session, c.code AS cohort, st.enrollment_no
           FROM cohort_memberships m JOIN cohorts c ON c.id = m.cohort_id
           JOIN academic_sessions s ON s.id = m.session_id JOIN students st ON st.id = m.student_id
           ORDER BY s.starts_on, c.code, st.enrollment_no""",
    ),
    "staff.csv": (
        "Staff accounts and roles (no passwords or two-step secrets).",
        """SELECT u.full_name, u.email, u.login_id, string_agg(r.role, ' ' ORDER BY r.role) AS roles, u.status,
                  u.last_login_at, sp.employee_code, sp.designation, sp.phone, u.created_at
           FROM users u LEFT JOIN user_roles r ON r.user_id = u.id LEFT JOIN staff_profiles sp ON sp.user_id = u.id
           WHERE u.kind <> 'student'
           GROUP BY u.id, sp.employee_code, sp.designation, sp.phone ORDER BY u.full_name""",
    ),
    "grading_schemes.csv": (
        "Grading schemes, every version, with their configuration (JSON).",
        """SELECT g.name, g.strategy, g.description, v.version, v.note, v.config, v.created_at
           FROM grading_schemes g JOIN grading_scheme_versions v ON v.scheme_id = g.id ORDER BY g.name, v.version""",
    ),
    "exams.csv": (
        "Exams (exam = 'academic year / term / name' in the other files).",
        """SELECT s.code || ' / ' || t.code || ' / ' || e.name AS exam, e.kind, e.status, g.name AS grading_scheme, e.marks_deadline, e.notes, e.created_at
            FROM examinations e JOIN terms t ON t.id = e.term_id JOIN academic_sessions s ON s.id = t.session_id JOIN grading_schemes g ON g.id = e.grading_scheme_id
            ORDER BY s.starts_on, t.sequence, e.name""",
    ),
    "exam_papers.csv": (
        "Each exam's papers, their maximum and pass marks, credits and components (JSON).",
        """SELECT s.code || ' / ' || t.code || ' / ' || e.name AS exam, c.code AS course, p.position, p.max_total, p.pass_total, p.credits, p.components
            FROM exam_papers p JOIN examinations e ON e.id = p.exam_id JOIN terms t ON t.id = e.term_id JOIN academic_sessions s ON s.id = t.session_id JOIN courses c ON c.id = p.course_id
            ORDER BY exam, p.position""",
    ),
    "marks.csv": (
        "Every mark entered: components (JSON), total and attendance, as last saved.",
        """SELECT s.code || ' / ' || t.code || ' / ' || e.name AS exam, c.code AS course, co.code AS cohort, st.enrollment_no, m.attendance,
                   m.components, m.total, m.version, m.source, m.updated_at
            FROM mark_entries m JOIN examinations e ON e.id = m.exam_id JOIN terms t ON t.id = e.term_id JOIN academic_sessions s ON s.id = t.session_id
            JOIN exam_papers p ON p.id = m.exam_paper_id JOIN courses c ON c.id = p.course_id
            JOIN cohorts co ON co.id = m.cohort_id JOIN students st ON st.id = m.student_id
            ORDER BY exam, course, st.enrollment_no""",
    ),
    "publications.csv": (
        "Every publication of results (versions, withdrawals, corrections).",
        """SELECT s.code || ' / ' || t.code || ' / ' || e.name AS exam, pb.version, pb.status, pb.scheduled_at, pb.published_at, pb.withdrawn_at,
                   pb.withdraw_reason, pb.students, pb.content_hash
            FROM publications pb JOIN examinations e ON e.id = pb.exam_id JOIN terms t ON t.id = e.term_id JOIN academic_sessions s ON s.id = t.session_id
            ORDER BY exam, pb.version""",
    ),
    "results.csv": (
        "Each student's published result, per publication version.",
        """SELECT s.code || ' / ' || t.code || ' / ' || e.name AS exam, pb.version, pb.status AS publication_status, r.payload->'student'->>'enrollment_no'
                   AS enrollment_no, r.payload->'student'->>'full_name' AS full_name,
                   r.payload->'result'->>'outcome' AS outcome, r.payload->'result'->>'total' AS total,
                   r.payload->'result'->>'max_total' AS max_total, r.payload->'result'->>'percentage' AS percentage,
                   r.payload->'result'->>'grade' AS grade, r.payload->'result'->>'grade_point' AS grade_point,
                   r.payload->'result'->>'sgpa' AS sgpa, r.payload->'result'->>'credits_earned' AS credits_earned,
                   r.payload->'result'->>'credits_attempted' AS credits_attempted,
                   r.payload->'result'->>'rank' AS rank
            FROM published_results r JOIN publications pb ON pb.id = r.publication_id
            JOIN examinations e ON e.id = r.exam_id JOIN terms t ON t.id = e.term_id JOIN academic_sessions s ON s.id = t.session_id
            ORDER BY exam, pb.version, enrollment_no""",
    ),
    "result_papers.csv": (
        "Each student's published result per paper, with component marks (JSON).",
        """SELECT s.code || ' / ' || t.code || ' / ' || e.name AS exam, pb.version, r.payload->'student'->>'enrollment_no' AS enrollment_no,
                   p->>'course_code' AS course, p->>'outcome' AS outcome, p->>'total' AS total,
                   p->>'max_total' AS max_total, p->>'percentage' AS percentage, p->>'grade' AS grade,
                   p->>'grade_point' AS grade_point, p->'components' AS components
            FROM published_results r JOIN publications pb ON pb.id = r.publication_id
            JOIN examinations e ON e.id = r.exam_id JOIN terms t ON t.id = e.term_id JOIN academic_sessions s ON s.id = t.session_id
            CROSS JOIN LATERAL jsonb_array_elements(r.payload->'papers') AS p
            ORDER BY exam, pb.version, enrollment_no, course""",
    ),
    "verification_codes.csv": (
        "The verification code printed on each marksheet, and whether it was revoked.",
        """SELECT v.code, s.code || ' / ' || t.code || ' / ' || e.name AS exam, pb.version, st.enrollment_no, v.revoked_at, v.revoked_reason,
                   v.verify_count, v.last_verified_at, v.created_at
            FROM verification_records v JOIN publications pb ON pb.id = v.publication_id
            JOIN examinations e ON e.id = pb.exam_id JOIN terms t ON t.id = e.term_id JOIN academic_sessions s ON s.id = t.session_id JOIN students st ON st.id = v.student_id
            ORDER BY exam, pb.version, st.enrollment_no""",
    ),
    "audit_log.csv": (
        "Who did what and when (before/after as JSON). IP addresses and browsers are not included.",
        """SELECT occurred_at, actor_type, actor_label, action, entity_type, entity_id, summary, reason, before, after
           FROM audit_logs ORDER BY occurred_at, id""",
    ),
}


@dataclass(frozen=True)
class ExportLink:
    url: str
    filename: str


def _cell(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")
    if isinstance(v, bool):
        return "true" if v else "false"
    return v


class ExportService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    # ---- the owner --------------------------------------------------------------------------------
    async def request(self, uow: UnitOfWork, principal: Principal) -> DataExport:
        AuthService(self.infra).require_recent_auth(principal)
        busy = await uow.session.scalar(
            select(func.count()).select_from(DataExport).where(DataExport.status.in_(("queued", "running")))
        )
        if busy:
            raise Conflict("An export is already being prepared. It will appear here when it's ready.")
        today = await uow.session.scalar(
            select(func.count())
            .select_from(DataExport)
            .where(DataExport.created_at > utcnow() - timedelta(days=1))
        )
        if (today or 0) >= PER_DAY:
            raise LimitExceeded(
                f"At most {PER_DAY} exports a day. Download a recent one instead.",
                limit="exports_per_day",
                current=int(today or 0),
                requested=1,
                max=PER_DAY,
            )
        export = DataExport(tenant_id=uow.require_tenant(), requested_by=principal.user_id, status="queued")
        uow.session.add(export)
        await uow.flush()
        await enqueue(
            uow,
            "exports.build",
            {"export_id": str(export.id)},
            dedupe_key=f"export:{export.id}",
            created_by=principal.user_id,
        )
        await record(
            uow,
            Actor.from_principal(principal),
            "data.export_requested",
            entity_type="data_export",
            entity_id=export.id,
            summary="An export of all the institution's data was requested",
        )
        return export

    @staticmethod
    async def recent(uow: UnitOfWork, limit: int = 10) -> list[DataExport]:
        rows = await uow.session.scalars(
            select(DataExport).order_by(DataExport.created_at.desc()).limit(limit)
        )
        return list(rows.all())

    async def link(self, uow: UnitOfWork, principal: Principal, export_id: uuid.UUID) -> ExportLink:
        AuthService(self.infra).require_recent_auth(principal)
        export = (
            await uow.session.scalars(select(DataExport).where(DataExport.id == export_id))
        ).one_or_none()
        if export is None:
            raise NotFound("Export not found")
        if export.status != "ready" or export.file_id is None:
            raise InvalidState(
                "This export isn't ready to download."
                if export.status != "expired"
                else "This export has expired. Request a new one."
            )
        stored = (await uow.session.scalars(select(StoredFile).where(StoredFile.id == export.file_id))).one()
        filename = f"scorecode-export-{export.created_at:%Y-%m-%d}.zip"
        await record(
            uow,
            Actor.from_principal(principal),
            "data.export_downloaded",
            entity_type="data_export",
            entity_id=export.id,
            summary="The data export was downloaded",
        )
        return ExportLink(
            FileService(self.infra).signed_url(stored, filename=filename, ttl_s=LINK_TTL_S), filename
        )

    # ---- the job ----------------------------------------------------------------------------------
    async def build(self, tenant_id: uuid.UUID, export_id: uuid.UUID) -> dict[str, Any]:
        async with self.infra.db.uow(tenant_id) as uow:
            export = (
                await uow.session.scalars(
                    select(DataExport).where(DataExport.id == export_id).with_for_update()
                )
            ).one()
            if export.status not in ("queued", "running"):
                return {"skipped": export.status}
            export.status = "running"
        try:
            data, counts = await self._zip(tenant_id)
        except Exception as exc:
            log.exception("data_export_failed")
            async with self.infra.db.uow(tenant_id) as uow:
                export = (
                    await uow.session.scalars(select(DataExport).where(DataExport.id == export_id))
                ).one()
                export.status, export.error, export.finished_at = "failed", type(exc).__name__, utcnow()
            raise
        async with self.infra.db.uow(tenant_id) as uow:
            export = (await uow.session.scalars(select(DataExport).where(DataExport.id == export_id))).one()
            stored = await FileService(self.infra).store(
                uow,
                data=data,
                kind="export",
                file_type=ZIP,
                original_name=f"scorecode-export-{export.created_at:%Y-%m-%d}.zip",
                uploaded_by=export.requested_by,
                count_usage=False,  # ours, temporary: not the institution's storage allowance
            )
            now = utcnow()
            export.status, export.file_id, export.size_bytes = "ready", stored.id, len(data)
            export.counts, export.finished_at, export.expires_at = counts, now, now + KEEP
            await record(
                uow,
                Actor.system("exports"),
                "data.export_ready",
                entity_type="data_export",
                entity_id=export.id,
                summary=f"The data export is ready ({sum(counts.values()):,} rows in {len(counts)} files)",
                after={"counts": counts, "bytes": len(data)},
            )
        return {"rows": sum(counts.values()), "bytes": len(data)}

    async def _zip(self, tenant_id: uuid.UUID) -> tuple[bytes, dict[str, int]]:
        counts: dict[str, int] = {}
        with tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024) as spool:
            with zipfile.ZipFile(spool, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                # One transaction under the tenant's RLS context. Each file is read when its query runs
                # (read committed), so work saved during an export may appear in later files only.
                async with self.infra.db.uow(tenant_id) as uow:
                    for name, (_, query) in FILES.items():
                        result = await uow.session.execute(text(query))
                        buf = io.StringIO()
                        writer = csv.writer(buf)
                        writer.writerow(list(result.keys()))
                        n = 0
                        for row in result:
                            writer.writerow([_cell(v) for v in row])
                            n += 1
                        counts[name] = n
                        zf.writestr(name, ("﻿" + buf.getvalue()).encode("utf-8"))
                zf.writestr("README.txt", _readme(counts))
            spool.seek(0)
            return spool.read(), counts


def _readme(counts: dict[str, int]) -> str:
    lines = [
        "ScoreCode data export",
        f"Created {utcnow():%Y-%m-%d %H:%M} UTC.",
        "",
        "Everything your institution has in ScoreCode, as CSV files (UTF-8; open in Excel or any spreadsheet).",
        "Exams are named 'academic year / term / exam name'. Students are identified by enrollment number.",
        "Columns in JSON hold structure: mark components, grading configuration, audit before/after.",
        "Not included, by design: passwords, two-step secrets, sign-in sessions and links, IP addresses.",
        "Marksheet PDFs are not included; every result is in results.csv and result_papers.csv.",
        "",
    ]
    for name, (what, _) in FILES.items():
        lines.append(f"{name:24} {counts.get(name, 0):>8} rows   {what}")
    return "\n".join(lines) + "\n"


_EXPIRED = text(
    """
    SELECT x.id, f.id AS file_id, f.object_key
    FROM data_exports x JOIN files f ON f.id = x.file_id
    WHERE x.status = 'ready' AND x.expires_at < now() AND f.purged_at IS NULL
    """
)


@maintenance_task
async def purge_expired_exports(infra: Infra) -> dict[str, int]:
    """Exports are kept seven days, then their ZIP is deleted (docs/10 §12 retention)."""
    removed = 0
    async with infra.db.uow() as uow:
        tenant_ids = (await uow.session.scalars(text("SELECT * FROM ops_tenant_ids()"))).all()
    for tenant_id in tenant_ids:
        async with infra.db.uow(tenant_id) as uow:
            for row in (await uow.session.execute(_EXPIRED)).all():
                await infra.storage.delete(row.object_key)
                await uow.session.execute(
                    text("UPDATE files SET purged_at = now() WHERE id = :id"), {"id": row.file_id}
                )
                await uow.session.execute(
                    text("UPDATE data_exports SET status = 'expired', updated_at = now() WHERE id = :id"),
                    {"id": row.id},
                )
                removed += 1
    return {"exports": removed}
