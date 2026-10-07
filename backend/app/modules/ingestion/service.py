"""Import lifecycle (docs/13, state diagram in docs/diagrams/state-diagrams.md §4).

uploaded → parsing → needs_mapping | validated → committing → committed
                   ↘ failed (unreadable file)          ↘ validated again if the commit is refused
Any state before committing → cancelled (by the admin, or when a fixed file supersedes it).

Upload, mapping changes and the commit request are short API transactions; parsing/validation and the
commit itself run on the ``imports`` queue. Nothing touches live data before the commit job, and the
commit is a single transaction.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

import anyio
from sqlalchemy import delete, func, insert, select

from app.core.clock import utcnow
from app.core.container import Infra
from app.core.db import UnitOfWork
from app.core.errors import Conflict, DomainError, InvalidState, NotFound, PermissionDenied, ValidationFailed
from app.core.http import Principal
from app.core.integrity import ConstraintMessage, flush_checked
from app.core.jobs import enqueue
from app.core.pagination import clamp_limit
from app.modules.academics.models import AcademicSession
from app.modules.audit.service import Actor, record
from app.modules.entitlements.catalogue import F
from app.modules.entitlements.service import EntitlementService
from app.modules.files.service import SPREADSHEET_TYPES, XLSX, FileService, validate_upload
from app.modules.identity.models import User
from app.modules.identity.permissions import P
from app.modules.ingestion.engine import Analysis, ImportProfile, analyse, pick_sheet
from app.modules.ingestion.marks import MarksProfile, paper_refs
from app.modules.ingestion.models import ImportJob, ImportRow
from app.modules.ingestion.parsers import FileUnreadable, Limits, parse_workbook
from app.modules.ingestion.report import error_report, template
from app.modules.ingestion.students import StudentsProfile

KINDS = ("students", "marks")
KIND_LABEL = {"students": "Students", "marks": "Marks"}
OPEN_STATES = ("uploaded", "parsing", "needs_mapping", "validating", "validated", "failed")
BUSY_STATES = ("uploaded", "parsing", "validating", "committing")
MESSAGES = {
    "uq_import_jobs__active_file": ConstraintMessage("This file is already being imported.", "file"),
}
ROW_BATCH = 1_000


@dataclass
class UploadResult:
    job: ImportJob
    resumed: bool


class ImportService:
    def __init__(self, infra: Infra) -> None:
        self.infra = infra

    async def profile(
        self, uow: UnitOfWork, kind: str, params: dict[str, Any] | None = None
    ) -> ImportProfile:
        """The rules for an import. Marks profiles are built per exam (their columns are its papers)."""
        if kind == "students":
            return StudentsProfile(self.infra)
        if kind == "marks":
            exam_id = (params or {}).get("exam_id")
            if not exam_id:
                raise ValidationFailed("Choose the exam these marks belong to.", field="exam_id")
            papers = await paper_refs(uow, uuid.UUID(str(exam_id)))
            paper_id = (params or {}).get("paper_id")
            single = next((p for p in papers if str(p.id) == str(paper_id)), None) if paper_id else None
            return MarksProfile(self.infra, papers, single)
        raise ValidationFailed("Unknown import type.", field="kind")

    @staticmethod
    def check_kind_permission(principal: Principal, kind: str) -> None:
        """Students: administrators. Marks: administrators, or faculty for their own papers (checked per row)."""
        if kind == "students":
            ok = principal.has(P.IMPORTS_MANAGE) and principal.has(P.STUDENTS_MANAGE)
        elif kind == "marks":
            ok = principal.has(P.IMPORTS_MANAGE) or principal.has(P.IMPORTS_MARKS_ASSIGNED)
        else:
            ok = False
        if not ok:
            raise PermissionDenied()

    async def get_visible(
        self, uow: UnitOfWork, principal: Principal, import_id: uuid.UUID, *, lock: bool = False
    ) -> ImportJob:
        """Administrators see every import; faculty only the ones they uploaded."""
        job = await self.get(uow, import_id, lock=lock)
        if not principal.has(P.IMPORTS_MANAGE) and job.created_by != principal.user_id:
            raise NotFound("Import not found")
        return job

    # ---- reads ----------------------------------------------------------------------------------
    async def get(self, uow: UnitOfWork, import_id: uuid.UUID, *, lock: bool = False) -> ImportJob:
        stmt = select(ImportJob).where(ImportJob.id == import_id)
        if lock:
            stmt = stmt.with_for_update()
        job = (await uow.session.scalars(stmt)).one_or_none()
        if job is None:
            raise NotFound("Import not found")
        return job

    async def recent(
        self,
        uow: UnitOfWork,
        principal: Principal,
        kind: str | None,
        *,
        exam_id: uuid.UUID | None = None,
        limit: int = 20,
    ) -> list[ImportJob]:
        stmt = select(ImportJob).order_by(ImportJob.created_at.desc(), ImportJob.id.desc()).limit(limit)
        if kind:
            stmt = stmt.where(ImportJob.kind == kind)
        if exam_id:
            stmt = stmt.where(ImportJob.target_exam_id == exam_id)
        if not principal.has(P.IMPORTS_MANAGE):
            stmt = stmt.where(ImportJob.created_by == principal.user_id)
        return list((await uow.session.scalars(stmt)).all())

    async def user_names(self, uow: UnitOfWork, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
        wanted = [i for i in ids if i]
        if not wanted:
            return {}
        rows = await uow.session.execute(select(User.id, User.full_name).where(User.id.in_(wanted)))
        return {uid: name for uid, name in rows.all()}  # noqa: C416 (Row → tuple unpacking)

    async def rows(
        self,
        uow: UnitOfWork,
        principal: Principal,
        import_id: uuid.UUID,
        *,
        status: str | None,
        after: int | None,
        limit: int | None,
    ) -> tuple[list[ImportRow], int | None]:
        await self.get_visible(uow, principal, import_id)
        n = clamp_limit(limit)
        stmt = (
            select(ImportRow)
            .where(ImportRow.import_job_id == import_id)
            .order_by(ImportRow.row_no)
            .limit(n + 1)
        )
        if status == "problems":
            stmt = stmt.where(ImportRow.status.in_(("error", "warning")))
        elif status:
            stmt = stmt.where(ImportRow.status == status)
        if after is not None:
            stmt = stmt.where(ImportRow.row_no > after)
        rows = list((await uow.session.scalars(stmt)).all())
        next_after = None
        if len(rows) > n:
            rows = rows[:n]
            next_after = rows[-1].row_no
        return rows, next_after

    # ---- upload ---------------------------------------------------------------------------------
    async def upload(
        self,
        uow: UnitOfWork,
        principal: Principal,
        *,
        kind: str,
        data: bytes,
        filename: str | None,
        params: dict[str, Any],
        supersedes_id: uuid.UUID | None = None,
    ) -> UploadResult:
        if kind not in KINDS:
            raise ValidationFailed("Unknown import type.", field="kind")
        self.check_kind_permission(principal, kind)
        file_type = validate_upload(data, SPREADSHEET_TYPES, self.infra.settings.max_upload_bytes)
        clean_params = await self._clean_params(uow, principal, kind, params)
        target_exam = uuid.UUID(clean_params["exam_id"]) if kind == "marks" else None
        sha = hashlib.sha256(data).digest()

        same = (
            await uow.session.scalars(
                select(ImportJob).where(
                    ImportJob.kind == kind,
                    ImportJob.target_exam_id.is_not_distinct_from(target_exam),
                    ImportJob.file_sha256 == sha,
                    ImportJob.status.notin_(("cancelled", "failed")),
                )
            )
        ).one_or_none()
        if same is not None:
            if same.status == "committed":
                names = await self.user_names(uow, {same.committed_by})
                who = names.get(same.committed_by) if same.committed_by else None
                when = same.committed_at.strftime("%-d %b %Y") if same.committed_at else "earlier"
                raise Conflict(
                    f"This exact file was already imported on {when}" + (f" by {who}" if who else "") + ".",
                    import_id=str(same.id),
                )
            return UploadResult(same, resumed=True)

        previous = None
        if supersedes_id is not None:
            previous = await self.get_visible(uow, principal, supersedes_id, lock=True)
            if previous.kind != kind:
                raise ValidationFailed("That import is of a different type.", field="supersedes_id")
            if previous.status in OPEN_STATES and previous.status not in BUSY_STATES:
                await self._cancel(uow, previous)
            if previous.mapping and previous.columns:
                clean_params["mapping_hint"] = {"columns": previous.columns, "mapping": previous.mapping}

        stored = await FileService(self.infra).store(
            uow,
            data=data,
            kind="import",
            file_type=file_type,
            original_name=filename,
            uploaded_by=principal.user_id,
        )
        job = ImportJob(
            tenant_id=uow.require_tenant(),
            kind=kind,
            status="uploaded",
            file_id=stored.id,
            file_name=(filename or "upload")[:255],
            file_sha256=sha,
            params={**clean_params, "format": "xlsx" if file_type == XLSX else "csv"},
            supersedes_id=previous.id if previous else None,
            target_exam_id=target_exam,
            created_by=principal.user_id,
        )
        uow.session.add(job)
        await flush_checked(uow, MESSAGES)
        job.last_job_id = await enqueue(
            uow, "imports.analyse", {"import_id": str(job.id)}, created_by=principal.user_id
        )
        await record(
            uow,
            Actor.from_principal(principal),
            "import.uploaded",
            entity_type="import",
            entity_id=job.id,
            summary=f"Uploaded {job.file_name} ({KIND_LABEL[kind].lower()} import)",
            after={"bytes": len(data), "kind": kind},
        )
        return UploadResult(job, resumed=False)

    async def _clean_params(
        self, uow: UnitOfWork, principal: Principal, kind: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if kind == "marks":
            from app.modules.examinations.models import Examination, ExamPaper

            exam_id = params.get("exam_id")
            if not exam_id:
                raise ValidationFailed("Choose the exam these marks belong to.", field="exam_id")
            exam = (
                await uow.session.scalars(select(Examination).where(Examination.id == exam_id))
            ).one_or_none()
            if exam is None:
                raise ValidationFailed("That exam doesn't exist.", field="exam_id")
            out["exam_id"] = str(exam.id)
            if params.get("paper_id"):
                paper = (
                    await uow.session.scalars(
                        select(ExamPaper.id).where(
                            ExamPaper.id == params["paper_id"], ExamPaper.exam_id == exam.id
                        )
                    )
                ).one_or_none()
                if paper is None:
                    raise ValidationFailed("That paper isn't part of the exam.", field="paper_id")
                out["paper_id"] = str(paper)
            # Faculty imports are limited to their assigned papers × cohorts (rule NOT_ASSIGNED).
            out["scope"] = "all" if principal.has(P.IMPORTS_MANAGE) else "assigned"
            out["actor_id"] = str(principal.user_id)
            return out
        if kind == "students":
            mode = params.get("mode") or "upsert"
            if mode not in ("upsert", "create_only"):
                raise ValidationFailed("Choose how to treat existing students.", field="mode")
            out["mode"] = mode
            session_id = params.get("session_id")
            if session_id:
                exists = (
                    await uow.session.scalars(
                        select(AcademicSession.id).where(AcademicSession.id == session_id)
                    )
                ).one_or_none()
                if exists is None:
                    raise ValidationFailed("That academic session doesn't exist.", field="session_id")
                out["session_id"] = str(session_id)
        return out

    # ---- state changes from the API -------------------------------------------------------------
    async def set_mapping(
        self,
        uow: UnitOfWork,
        principal: Principal,
        import_id: uuid.UUID,
        *,
        mapping: dict[str, int | None],
        header_row: int | None,
        sheet_name: str | None,
    ) -> ImportJob:
        job = await self.get_visible(uow, principal, import_id, lock=True)
        self.check_kind_permission(principal, job.kind)
        if job.status not in ("needs_mapping", "validated"):
            raise InvalidState("This import can't be changed now.")
        known = {f.key for f in (await self.profile(uow, job.kind, job.params)).fields}
        unknown = sorted(k for k in mapping if k not in known)
        if unknown:
            raise ValidationFailed(f"Unknown field: {unknown[0]}.", field="mapping")
        columns = {c for c in mapping.values() if c is not None}
        if len(columns) != len([c for c in mapping.values() if c is not None]):
            raise ValidationFailed("Each column can be used for one field only.", field="mapping")
        job.mapping = {k: v for k, v in mapping.items() if v is not None}
        job.params = {**job.params, "mapping_locked": True}
        if header_row is not None:
            job.header_row = header_row
            job.params = {**job.params, "header_row_locked": True}
        if sheet_name is not None:
            job.sheet_name = sheet_name
        job.status = "validating"
        job.error_code = job.error_detail = None
        job.last_job_id = await enqueue(
            uow, "imports.analyse", {"import_id": str(job.id)}, created_by=principal.user_id
        )
        return job

    async def revalidate(self, uow: UnitOfWork, principal: Principal, import_id: uuid.UUID) -> ImportJob:
        job = await self.get_visible(uow, principal, import_id, lock=True)
        self.check_kind_permission(principal, job.kind)
        if job.status not in ("needs_mapping", "validated"):
            raise InvalidState("This import can't be re-checked now.")
        job.status = "validating"
        job.error_code = job.error_detail = None
        job.last_job_id = await enqueue(
            uow, "imports.analyse", {"import_id": str(job.id)}, created_by=principal.user_id
        )
        return job

    async def request_commit(
        self, uow: UnitOfWork, principal: Principal, import_id: uuid.UUID, *, skip_errors: bool
    ) -> ImportJob:
        job = await self.get_visible(uow, principal, import_id, lock=True)
        self.check_kind_permission(principal, job.kind)
        if job.status in ("committing", "committed"):
            return job  # repeated click / retried request: the commit is already under way or done
        if job.status != "validated":
            raise InvalidState("Only a checked import can be committed.")
        blocking = [i for i in job.file_issues or [] if i.get("severity") == "error"]
        if blocking:
            raise InvalidState(blocking[0]["msg"])
        if job.rows_error and not skip_errors:
            raise InvalidState(
                f"{job.rows_error} row(s) have errors. Fix them and upload again, or import only the valid rows."
            )
        if job.rows_valid + job.rows_warning == 0:
            raise InvalidState("There are no valid rows to import.")
        job.status = "committing"
        job.params = {**job.params, "skip_errors": skip_errors}
        job.committed_by = principal.user_id
        job.error_code = job.error_detail = None
        job.last_job_id = await enqueue(
            uow,
            "imports.commit",
            {"import_id": str(job.id), "actor_label": principal.display_name},
            created_by=principal.user_id,
            dedupe_key=f"import-commit:{job.id}",
        )
        return job

    async def cancel(self, uow: UnitOfWork, principal: Principal, import_id: uuid.UUID) -> ImportJob:
        job = await self.get_visible(uow, principal, import_id, lock=True)
        self.check_kind_permission(principal, job.kind)
        if job.status == "cancelled":
            return job
        if job.status not in ("needs_mapping", "validated", "failed"):
            raise InvalidState("This import can't be cancelled now.")
        await self._cancel(uow, job)
        await record(
            uow, Actor.from_principal(principal), "import.cancelled", entity_type="import", entity_id=job.id
        )
        return job

    async def _cancel(self, uow: UnitOfWork, job: ImportJob) -> None:
        job.status = "cancelled"
        await uow.session.execute(delete(ImportRow).where(ImportRow.import_job_id == job.id))

    # ---- generated files ------------------------------------------------------------------------
    async def error_report(
        self, uow: UnitOfWork, principal: Principal, import_id: uuid.UUID
    ) -> tuple[bytes, str]:
        job = await self.get_visible(uow, principal, import_id)
        if job.status not in ("validated", "committing", "committed"):
            raise InvalidState("The report is available once the file has been checked.")
        rows = (
            await uow.session.execute(
                select(ImportRow.row_no, ImportRow.raw, ImportRow.issues, ImportRow.status)
                .where(ImportRow.import_job_id == job.id)
                .order_by(ImportRow.row_no)
            )
        ).all()
        data = await anyio.to_thread.run_sync(
            lambda: error_report(
                columns=job.columns or [],
                mapping=job.mapping or {},
                rows=({"row_no": r[0], "raw": r[1], "issues": r[2], "status": r[3]} for r in rows),
                file_issues=job.file_issues or [],
                title=f"Checked: {job.file_name}",
            )
        )
        stem = (job.file_name or "import").rsplit(".", 1)[0][:80]
        return data, f"{stem} - checked.xlsx"

    async def template(
        self,
        uow: UnitOfWork,
        principal: Principal,
        kind: str,
        *,
        exam_id: uuid.UUID | None = None,
        paper_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
    ) -> tuple[bytes, str]:
        self.check_kind_permission(principal, kind)
        if kind == "marks":
            return await self._marks_template(uow, principal, exam_id, paper_id, cohort_id)
        profile = await self.profile(uow, kind)
        choices: dict[str, list[str]] = {}
        if kind == "students":
            ctx = await profile.load_context(uow, {})
            choices["cohort"] = sorted(c.code for c in ctx.cohorts.values() if not c.archived)
        data = template(profile.fields, title=f"{KIND_LABEL[kind]} import template", choices=choices)
        return data, f"{kind}-import-template.xlsx"

    async def _marks_template(
        self,
        uow: UnitOfWork,
        principal: Principal,
        exam_id: uuid.UUID | None,
        paper_id: uuid.UUID | None,
        cohort_id: uuid.UUID | None,
    ) -> tuple[bytes, str]:
        from app.modules.academics.models import Cohort
        from app.modules.directory.models import CohortMembership, Student
        from app.modules.examinations.models import ExamCohort, Examination, PaperAssignment
        from app.modules.ingestion.report import marks_template
        from app.modules.tenancy.models import TenantSettings

        if exam_id is None:
            raise ValidationFailed("Choose the exam.", field="exam_id")
        exam = (await uow.session.scalars(select(Examination).where(Examination.id == exam_id))).one_or_none()
        if exam is None:
            raise NotFound("Exam not found")
        papers = await paper_refs(uow, exam.id)
        if paper_id is not None:
            papers = [p for p in papers if p.id == paper_id]
            if not papers:
                raise NotFound("Paper not found")
        cohorts = list(
            (
                await uow.session.execute(
                    select(Cohort.id, Cohort.code)
                    .join(ExamCohort, ExamCohort.cohort_id == Cohort.id)
                    .where(ExamCohort.exam_id == exam.id)
                )
            ).all()
        )
        if cohort_id is not None:
            cohorts = [c for c in cohorts if c[0] == cohort_id]
            if not cohorts:
                raise NotFound("That cohort doesn't sit this exam")
        if not principal.has(P.IMPORTS_MANAGE):  # faculty: only what they're assigned
            assignment_rows = await uow.session.execute(
                select(PaperAssignment.exam_paper_id, PaperAssignment.cohort_id).where(
                    PaperAssignment.exam_id == exam.id, PaperAssignment.user_id == principal.user_id
                )
            )
            assigned = {(pid, cid) for pid, cid in assignment_rows.all()}
            papers = [p for p in papers if any((p.id, c[0]) in assigned for c in cohorts)]
            cohorts = [c for c in cohorts if any((p.id, c[0]) in assigned for p in papers)]
            if not papers:
                raise NotFound("Paper not found")
        codes = list(((await uow.session.scalars(select(TenantSettings))).one().special_codes or {}).keys())
        single = paper_id is not None  # must match how the file is uploaded (with or without a paper)
        columns = [
            (
                (c["label"] if single else f"{p.course_code}_{c['code']}"),
                c["max"],
                f"{p.course_code} {c['label']}",
            )
            for p in papers
            for c in p.components
        ]
        cohort_code = dict(cohorts)
        students = [
            (s.enrollment_no, s.full_name, cohort_code[cid])
            for s, cid in (
                await uow.session.execute(
                    select(Student, CohortMembership.cohort_id)
                    .join(CohortMembership, CohortMembership.student_id == Student.id)
                    .where(
                        CohortMembership.cohort_id.in_(list(cohort_code)),
                        Student.status.in_(("active", "graduated")),
                    )
                    .order_by(CohortMembership.cohort_id, Student.enrollment_no)
                )
            ).all()
        ]
        students.sort(key=lambda r: (r[2], r[0]))
        label = papers[0].course_code if single else "all papers"
        data = await anyio.to_thread.run_sync(
            lambda: marks_template(
                title=f"Marks — {exam.name}, {label}",
                columns=columns,
                students=students,
                codes=[c.upper() for c in codes],
                show_cohort=len(cohorts) > 1,
            )
        )
        name = f"marks-{exam.name}-{label}".replace("/", "-")[:80]
        return data, f"{name}.xlsx"

    # ---- background work ------------------------------------------------------------------------
    async def run_analysis(
        self, tenant_id: uuid.UUID, import_id: uuid.UUID, *, final_attempt: bool
    ) -> dict[str, Any]:
        async with self.infra.db.uow(tenant_id) as uow:
            job = await self.get(uow, import_id, lock=True)
            if job.status not in ("uploaded", "parsing", "validating"):
                return {"skipped": job.status}
            if job.status == "uploaded":
                job.status = "parsing"
            key = (await FileService(self.infra).get(uow, job.file_id)).object_key
            file_format = job.params.get("format", "csv")
        try:
            data = await self.infra.storage.get(key)
            row_cap = await self._row_cap(tenant_id)
            limits = Limits(
                max_rows=row_cap,
                max_columns=self.infra.settings.max_import_columns,
                max_uncompressed_bytes=self.infra.settings.max_xlsx_uncompressed_bytes,
            )
            workbook = await anyio.to_thread.run_sync(lambda: parse_workbook(data, file_format, limits))
            async with self.infra.db.uow(tenant_id) as uow:
                job = await self.get(uow, import_id, lock=True)
                if job.status not in ("parsing", "validating"):
                    return {"skipped": job.status}
                profile = await self.profile(uow, job.kind, job.params)
                sheet = pick_sheet(workbook, profile.fields, job.sheet_name)
                ctx = await profile.load_context(uow, job.params)
                mapping = job.mapping if job.params.get("mapping_locked") else None
                hint = job.params.get("mapping_hint")
                header_row = job.header_row if job.params.get("header_row_locked") else None
                result = await anyio.to_thread.run_sync(
                    lambda: _analyse_with_hint(sheet, profile, ctx, mapping, header_row, hint)
                )
                data_rows = len(result.rows)
                if data_rows > row_cap:
                    raise FileUnreadable(
                        "too-many-rows",
                        f"This file has {data_rows:,} rows; your plan allows {row_cap:,} per import. Split the file.",
                    )
                await self._store_analysis(uow, job, result, [s.name for s in workbook.sheets], sheet.name)
                return {"status": job.status, "rows": data_rows}
        except FileUnreadable as exc:
            await self._fail(tenant_id, import_id, exc.reason, exc.detail)
            return {"status": "failed", "reason": exc.reason}
        except DomainError as exc:
            await self._fail(tenant_id, import_id, exc.code, exc.detail)
            return {"status": "failed", "reason": exc.code}
        except Exception:
            if final_attempt:
                await self._fail(
                    tenant_id, import_id, "internal", "Something went wrong while reading this file."
                )
            raise

    async def _row_cap(self, tenant_id: uuid.UUID) -> int:
        async with self.infra.db.uow(tenant_id) as uow:
            plan_cap = (await EntitlementService(self.infra).effective(uow)).limit(F.MAX_IMPORT_ROWS)
        hard_cap = self.infra.settings.max_import_rows
        return min(plan_cap, hard_cap) if plan_cap is not None else hard_cap

    async def _store_analysis(
        self, uow: UnitOfWork, job: ImportJob, result: Analysis, sheets: list[str], sheet_name: str
    ) -> None:
        await uow.session.execute(delete(ImportRow).where(ImportRow.import_job_id == job.id))
        payload = [
            {
                "tenant_id": job.tenant_id,
                "import_job_id": job.id,
                "row_no": r.row_no,
                "raw": r.cells,
                "normalized": r.normalized,
                "issues": [i.to_json() for i in r.issues],
                "status": r.status,
            }
            for r in result.rows
        ]
        for start in range(0, len(payload), ROW_BATCH):
            await uow.session.execute(insert(ImportRow), payload[start : start + ROW_BATCH])
        counts = result.counts()
        job.sheet_name = sheet_name
        job.columns = result.columns
        job.header_row = result.header_row
        job.mapping = result.mapping
        job.file_issues = [i.to_json() for i in result.file_issues]
        job.rows_total = len(result.rows)
        job.rows_valid = counts["valid"]
        job.rows_warning = counts["warning"]
        job.rows_error = counts["error"]
        job.summary = {**result.summary, "sheets": sheets}
        job.status = "needs_mapping" if result.needs_mapping else "validated"

    async def _fail(self, tenant_id: uuid.UUID, import_id: uuid.UUID, code: str, detail: str) -> None:
        async with self.infra.db.uow(tenant_id) as uow:
            job = await self.get(uow, import_id, lock=True)
            if job.status in ("committed", "cancelled"):
                return
            job.status = "failed"
            job.error_code = code
            job.error_detail = detail

    async def run_commit(
        self, tenant_id: uuid.UUID, import_id: uuid.UUID, actor_label: str | None
    ) -> dict[str, Any]:
        try:
            async with self.infra.db.uow(tenant_id) as uow:
                job = await self.get(uow, import_id, lock=True)
                if job.status != "committing":
                    return {"skipped": job.status}
                rows = [
                    r
                    for (r,) in (
                        await uow.session.execute(
                            select(ImportRow.normalized)
                            .where(
                                ImportRow.import_job_id == job.id, ImportRow.status.in_(("valid", "warning"))
                            )
                            .order_by(ImportRow.row_no)
                        )
                    ).all()
                ]
                actor = Actor("user", job.committed_by, actor_label)
                profile = await self.profile(uow, job.kind, job.params)
                outcome = await profile.commit(uow, actor, job.id, job.params, rows)
                job.status = "committed"
                job.committed_at = utcnow()
                job.summary = {**(job.summary or {}), "result": outcome}
                return outcome
        except DomainError as exc:
            # A business rule refused the commit (seat limit, archived cohort…): nothing was written.
            # Back to "validated" with the reason, so the admin can act and try again.
            async with self.infra.db.uow(tenant_id) as uow:
                job = await self.get(uow, import_id, lock=True)
                if job.status == "committing":
                    job.status = "validated"
                    job.error_code = exc.code
                    job.error_detail = exc.detail
            return {"refused": exc.code}

    async def counts_by_status(self, uow: UnitOfWork, import_id: uuid.UUID) -> dict[str, int]:
        rows = await uow.session.execute(
            select(ImportRow.status, func.count())
            .where(ImportRow.import_job_id == import_id)
            .group_by(ImportRow.status)
        )
        return {s: int(n) for s, n in rows.all()}


def _analyse_with_hint(
    sheet: Any,
    profile: ImportProfile,
    ctx: Any,
    mapping: dict[str, Any] | None,
    header_row: int | None,
    hint: dict[str, Any] | None,
) -> Analysis:
    """A fixed file re-uploaded with the same columns keeps the mapping the admin chose last time."""
    if mapping is None and hint:
        first = analyse(sheet, profile, ctx, header_row=header_row)
        if first.columns == hint.get("columns"):
            return analyse(
                sheet, profile, ctx, mapping=hint.get("mapping") or {}, header_row=first.header_row
            )
        return first
    return analyse(sheet, profile, ctx, mapping=mapping, header_row=header_row)
