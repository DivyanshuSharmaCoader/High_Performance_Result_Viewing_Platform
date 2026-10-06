from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.errors import ValidationFailed
from app.core.http import InfraDep, Principal, UoW, require
from app.modules.grading import onboarding as _onboarding  # noqa: F401  (registers the checklist step)
from app.modules.grading.engine import (
    Attendance,
    Component,
    ExamResult,
    GradingInputError,
    MarkInput,
    PaperResult,
    PaperSpec,
    grade_exam,
)
from app.modules.grading.service import STRATEGY_LABEL, GradingService, SchemeView, validated
from app.modules.grading.templates import TEMPLATES
from app.modules.identity.models import User
from app.modules.identity.permissions import P

router = APIRouter(prefix="/api/v1/admin/grading-schemes", tags=["grading"])

Strategy = Literal["percentage_bands", "credit_gpa", "marks_only"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SchemeIn(In):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class SchemeCreateIn(SchemeIn):
    config: dict[str, Any]


class VersionIn(In):
    config: dict[str, Any]
    note: str | None = Field(default=None, max_length=200)
    based_on: int = Field(ge=1)


class ArchivedIn(In):
    archived: bool


class VersionOut(BaseModel):
    id: uuid.UUID
    version: int
    note: str | None
    created_at: datetime
    created_by_name: str | None


class SchemeOut(BaseModel):
    id: uuid.UUID
    name: str
    strategy: Strategy
    strategy_label: str
    description: str | None
    is_default: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
    version_id: uuid.UUID
    config: dict[str, Any]


class SchemeDetailOut(SchemeOut):
    versions: list[VersionOut]
    saved: bool | None = None  # on save: False when nothing changed (no new version)


class TemplateOut(BaseModel):
    key: str
    name: str
    description: str
    strategy: Strategy
    config: dict[str, Any]


def _out(view: SchemeView) -> dict[str, Any]:
    s, v = view.scheme, view.latest
    return {
        "id": s.id,
        "name": s.name,
        "strategy": s.strategy,
        "strategy_label": STRATEGY_LABEL[s.strategy],
        "description": s.description,
        "is_default": view.is_default,
        "archived_at": s.archived_at,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "version": v.version,
        "version_id": v.id,
        "config": v.config,
    }


async def _detail(
    uow: Any, service: GradingService, scheme_id: uuid.UUID, saved: bool | None = None
) -> SchemeDetailOut:
    await uow.flush()
    view = await service.detail(uow, scheme_id)
    await uow.session.refresh(view.scheme)
    ids = {v.created_by for v in view.versions if v.created_by}
    names: dict[uuid.UUID, str] = {}
    if ids:
        rows = await uow.session.execute(select(User.id, User.full_name).where(User.id.in_(ids)))
        names = {uid: name for uid, name in rows.all()}  # noqa: C416 (Row → tuple unpacking)
    return SchemeDetailOut(
        **_out(view),
        versions=[
            VersionOut(
                id=v.id,
                version=v.version,
                note=v.note,
                created_at=v.created_at,
                created_by_name=names.get(v.created_by) if v.created_by else None,
            )
            for v in view.versions
        ],
        saved=saved,
    )


# ---- preview calculator -------------------------------------------------------------------------


class PreviewComponentIn(In):
    code: str = Field(min_length=1, max_length=12)
    max: Decimal = Field(gt=0, le=1000)
    min_pass: Decimal | None = Field(default=None, ge=0, le=1000)


class PreviewPaperIn(In):
    id: str = Field(min_length=1, max_length=40)
    credits: Decimal | None = Field(default=None, ge=0, le=40)
    pass_total: Decimal | None = Field(default=None, ge=0, le=10000)
    components: list[PreviewComponentIn] = Field(min_length=1, max_length=10)


class PreviewMarkIn(In):
    attendance: Attendance = Attendance.PRESENT
    components: dict[str, Decimal | None] = Field(default_factory=dict)


class PreviewIn(In):
    config: dict[str, Any]
    papers: list[PreviewPaperIn] = Field(min_length=1, max_length=20)
    marks: dict[str, PreviewMarkIn]


class PaperResultOut(BaseModel):
    paper_id: str
    outcome: str
    total: Decimal | None
    max_total: Decimal
    percentage: Decimal | None
    grade: str | None
    grade_point: Decimal | None
    credits: Decimal | None
    failed_components: list[str]
    missing_components: list[str]


class ExamResultOut(BaseModel):
    outcome: str
    total: Decimal | None
    max_total: Decimal | None
    percentage: Decimal | None
    grade: str | None
    grade_point: Decimal | None
    sgpa: Decimal | None
    credits_attempted: Decimal | None
    credits_earned: Decimal | None
    papers: list[PaperResultOut]


def _paper_out(p: PaperResult) -> PaperResultOut:
    return PaperResultOut(
        paper_id=p.paper_id,
        outcome=p.outcome.value,
        total=p.total,
        max_total=p.max_total,
        percentage=p.percentage,
        grade=p.grade,
        grade_point=p.grade_point,
        credits=p.credits,
        failed_components=list(p.failed_components),
        missing_components=list(p.missing_components),
    )


def _exam_out(r: ExamResult) -> ExamResultOut:
    return ExamResultOut(
        outcome=r.outcome.value,
        total=r.total,
        max_total=r.max_total,
        percentage=r.percentage,
        grade=r.grade,
        grade_point=r.grade_point,
        sgpa=r.sgpa,
        credits_attempted=r.credits_attempted,
        credits_earned=r.credits_earned,
        papers=[_paper_out(p) for p in r.papers],
    )


# ---- routes -------------------------------------------------------------------------------------


@router.get("")
async def list_schemes(
    uow: UoW, infra: InfraDep, include_archived: bool = False, _: Principal = require(P.GRADING_VIEW)
) -> list[SchemeOut]:
    views = await GradingService(infra).list(uow, include_archived=include_archived)
    return [SchemeOut(**_out(v)) for v in views]


@router.get("/templates")
async def list_templates(_: Principal = require(P.GRADING_VIEW)) -> list[TemplateOut]:
    return [
        TemplateOut(
            key=t.key, name=t.name, description=t.description, strategy=t.config["strategy"], config=t.config
        )
        for t in TEMPLATES
    ]


@router.post("/preview")
async def preview(body: PreviewIn, _: Principal = require(P.GRADING_VIEW)) -> ExamResultOut:
    """Grade sample marks with an unsaved config — the editor's live calculator. Touches no data."""
    cfg = validated(body.config)
    if len({p.id for p in body.papers}) != len(body.papers):
        raise ValidationFailed("Each sample paper needs its own name.", field="papers")
    papers = [
        PaperSpec(
            p.id,
            tuple(Component(c.code, c.max, c.min_pass) for c in p.components),
            credits=p.credits,
            pass_total=p.pass_total,
        )
        for p in body.papers
    ]
    marks = {pid: MarkInput(m.components, m.attendance) for pid, m in body.marks.items()}
    try:
        return _exam_out(grade_exam(papers, marks, cfg))
    except GradingInputError as exc:
        raise ValidationFailed(str(exc), field="marks") from exc


@router.post("", status_code=201)
async def create_scheme(
    body: SchemeCreateIn, uow: UoW, infra: InfraDep, principal: Principal = require(P.GRADING_MANAGE)
) -> SchemeDetailOut:
    service = GradingService(infra)
    scheme = await service.create(
        uow, principal, name=body.name, description=body.description, config=body.config
    )
    return await _detail(uow, service, scheme.id)


@router.get("/{scheme_id}")
async def get_scheme(
    scheme_id: uuid.UUID, uow: UoW, infra: InfraDep, _: Principal = require(P.GRADING_VIEW)
) -> SchemeDetailOut:
    return await _detail(uow, GradingService(infra), scheme_id)


@router.put("/{scheme_id}")
async def update_scheme(
    scheme_id: uuid.UUID,
    body: SchemeIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.GRADING_MANAGE),
) -> SchemeDetailOut:
    service = GradingService(infra)
    await service.update_details(uow, principal, scheme_id, name=body.name, description=body.description)
    return await _detail(uow, service, scheme_id)


@router.post("/{scheme_id}/versions")
async def save_version(
    scheme_id: uuid.UUID,
    body: VersionIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.GRADING_MANAGE),
) -> SchemeDetailOut:
    service = GradingService(infra)
    _, created = await service.add_version(
        uow, principal, scheme_id, config=body.config, note=body.note, based_on=body.based_on
    )
    return await _detail(uow, service, scheme_id, saved=created)


@router.put("/{scheme_id}/archived")
async def set_archived(
    scheme_id: uuid.UUID,
    body: ArchivedIn,
    uow: UoW,
    infra: InfraDep,
    principal: Principal = require(P.GRADING_MANAGE),
) -> SchemeDetailOut:
    service = GradingService(infra)
    await service.set_archived(uow, principal, scheme_id, body.archived)
    return await _detail(uow, service, scheme_id)


@router.post("/{scheme_id}/default")
async def make_default(
    scheme_id: uuid.UUID, uow: UoW, infra: InfraDep, principal: Principal = require(P.GRADING_MANAGE)
) -> SchemeDetailOut:
    service = GradingService(infra)
    await service.make_default(uow, principal, scheme_id)
    return await _detail(uow, service, scheme_id)
