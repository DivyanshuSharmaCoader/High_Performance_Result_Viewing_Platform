"""Grading strategies (docs/08 §7). Each strategy grades one paper and aggregates one student's papers.

Shared rules, applied identically by every strategy (and pinned by the property tests):

* **Exempt** papers are left out of every total, percentage and credit sum.
* **Absent** papers score nothing, never pass, and show the scheme's ``absent_grade``; if every
  counted paper is absent the exam outcome is ``absent``.
* **Withheld / malpractice** on any paper withholds the whole exam result.
* A paper with a **missing** component mark is ``incomplete``, and so is the exam — results are never
  computed from partial marks.
* A present paper passes when every component meets its ``min_pass`` and the total meets the paper's
  pass total (or the scheme's ``paper_pass_percentage``).
* Grades come from the **rounded** percentage, i.e. the figure the student sees.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any, Protocol

from app.modules.grading.engine.config import (
    Band,
    CreditGpaConfig,
    GradingConfig,
    MarksOnlyConfig,
    PercentageBandsConfig,
)
from app.modules.grading.engine.types import (
    Attendance,
    ExamOutcome,
    ExamResult,
    GradingInputError,
    MarkInput,
    PaperOutcome,
    PaperResult,
    PaperSpec,
)

ZERO = Decimal(0)
HUNDRED = Decimal(100)


class GradingStrategy(Protocol):
    code: str

    def grade_paper(self, paper: PaperSpec, mark: MarkInput | None, cfg: GradingConfig) -> PaperResult: ...

    def aggregate(self, papers: Sequence[PaperResult], cfg: GradingConfig) -> ExamResult: ...


def _band(bands: Sequence[Band], percentage: Decimal) -> Band:
    for b in bands:
        if percentage >= b.min_percentage:
            return b
    return bands[-1]  # unreachable: validation guarantees the last band starts at 0


def _pct(total: Decimal, max_total: Decimal, cfg: GradingConfig) -> Decimal:
    if max_total <= 0:
        return ZERO
    with localcontext() as ctx:  # independent of any global decimal context
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_EVEN
        raw = total * HUNDRED / max_total
    return cfg.rounding.q(raw, cfg.rounding.percentage_places)


def score_paper(paper: PaperSpec, mark: MarkInput | None, cfg: GradingConfig) -> PaperResult:
    """Everything about a paper except its grade: attendance, totals, pass/fail."""

    def result(outcome: PaperOutcome, **extra: Any) -> PaperResult:
        return PaperResult(
            paper_id=paper.paper_id,
            outcome=outcome,
            max_total=paper.max_total,
            credits=paper.credits,
            **extra,
        )

    if mark is None:
        return result(PaperOutcome.INCOMPLETE, missing_components=tuple(c.code for c in paper.components))
    if mark.attendance is Attendance.EXEMPT:
        return result(PaperOutcome.EXEMPT)
    if mark.attendance in (Attendance.WITHHELD, Attendance.MALPRACTICE):
        return result(PaperOutcome.WITHHELD)
    if mark.attendance is Attendance.ABSENT:
        return result(PaperOutcome.ABSENT, grade=cfg.absent_grade)

    known = {c.code for c in paper.components}
    unknown = sorted(set(mark.components) - known)
    if unknown:
        raise GradingInputError(f"{paper.paper_id}: unknown component(s) {', '.join(unknown)}")
    values: dict[str, Decimal] = {}
    missing: list[str] = []
    for c in paper.components:
        v = mark.components.get(c.code)
        if v is None:
            missing.append(c.code)
            continue
        if v < 0 or v > c.max:
            raise GradingInputError(f"{paper.paper_id}/{c.code}: {v} is outside 0–{c.max}")
        values[c.code] = v
    if missing:
        return result(PaperOutcome.INCOMPLETE, missing_components=tuple(missing))
    total = cfg.rounding.q(sum(values.values(), ZERO), cfg.rounding.total_places)
    percentage = _pct(total, paper.max_total, cfg)
    failed = tuple(c.code for c in paper.components if c.min_pass is not None and values[c.code] < c.min_pass)
    threshold = paper.pass_total
    if threshold is None and cfg.pass_rules.paper_pass_percentage is not None:
        threshold = paper.max_total * cfg.pass_rules.paper_pass_percentage / HUNDRED
    passed = not failed and (threshold is None or total >= threshold)
    return result(
        PaperOutcome.PASS if passed else PaperOutcome.FAIL,
        total=total,
        percentage=percentage,
        failed_components=failed,
    )


def _with(paper: PaperResult, **changes: Any) -> PaperResult:
    return replace(paper, **changes)


def _exam_outcome(papers: Sequence[PaperResult]) -> tuple[ExamOutcome | None, list[PaperResult]]:
    """Outcomes that end aggregation early, plus the papers that count."""
    counted = [p for p in papers if p.outcome is not PaperOutcome.EXEMPT]
    if any(p.outcome is PaperOutcome.WITHHELD for p in counted):
        return ExamOutcome.WITHHELD, counted
    if not counted or any(p.outcome is PaperOutcome.INCOMPLETE for p in counted):
        return ExamOutcome.INCOMPLETE, counted
    if all(p.outcome is PaperOutcome.ABSENT for p in counted):
        return ExamOutcome.ABSENT, counted
    return None, counted


def _totals(counted: Sequence[PaperResult], cfg: GradingConfig) -> tuple[Decimal, Decimal, Decimal]:
    total = cfg.rounding.q(sum((p.total or ZERO for p in counted), ZERO), cfg.rounding.total_places)
    max_total = sum((p.max_total for p in counted), ZERO)
    return total, max_total, _pct(total, max_total, cfg)


def _passed_overall(counted: Sequence[PaperResult], percentage: Decimal, cfg: GradingConfig) -> bool:
    rules = cfg.pass_rules
    if rules.require_all_papers and any(not p.passed for p in counted):
        return False
    return not (rules.overall_pass_percentage is not None and percentage < rules.overall_pass_percentage)


class PercentageBandsStrategy:
    code = "percentage_bands"

    def grade_paper(self, paper: PaperSpec, mark: MarkInput | None, cfg: GradingConfig) -> PaperResult:
        assert isinstance(cfg, PercentageBandsConfig)
        r = score_paper(paper, mark, cfg)
        if r.outcome is PaperOutcome.ABSENT:
            return _with(r, grade_point=ZERO if any(b.grade_point is not None for b in cfg.bands) else None)
        if r.percentage is None:
            return r
        if r.outcome is PaperOutcome.FAIL and cfg.fail_grade:
            return _with(
                r, grade=cfg.fail_grade, grade_point=ZERO if cfg.bands[0].grade_point is not None else None
            )
        band = _band(cfg.bands, r.percentage)
        return _with(r, grade=band.grade, grade_point=band.grade_point)

    def aggregate(self, papers: Sequence[PaperResult], cfg: GradingConfig) -> ExamResult:
        assert isinstance(cfg, PercentageBandsConfig)
        early, counted = _exam_outcome(papers)
        if early is not None:
            return ExamResult(outcome=early, papers=tuple(papers))
        total, max_total, percentage = _totals(counted, cfg)
        passed = _passed_overall(counted, percentage, cfg)
        grade = cfg.fail_grade if (not passed and cfg.fail_grade) else _band(cfg.bands, percentage).grade
        points = [p.grade_point for p in counted]
        average = None
        if points and all(gp is not None for gp in points):
            with localcontext() as ctx:
                ctx.prec = 28
                raw = sum((gp for gp in points if gp is not None), ZERO) / len(points)
            average = cfg.rounding.q(raw, cfg.rounding.gpa_places)
        return ExamResult(
            outcome=ExamOutcome.PASS if passed else ExamOutcome.FAIL,
            papers=tuple(papers),
            total=total,
            max_total=max_total,
            percentage=percentage,
            grade=grade,
            grade_point=average,
        )


class CreditGpaStrategy:
    code = "credit_gpa"

    def grade_paper(self, paper: PaperSpec, mark: MarkInput | None, cfg: GradingConfig) -> PaperResult:
        assert isinstance(cfg, CreditGpaConfig)
        r = score_paper(paper, mark, cfg)
        if r.outcome is PaperOutcome.ABSENT:
            return _with(r, grade_point=ZERO)
        if r.percentage is None:
            return r
        if r.outcome is PaperOutcome.FAIL:
            return _with(r, grade=cfg.fail_grade, grade_point=ZERO)
        band = _band(cfg.bands, r.percentage)
        if band.grade_point == 0:
            # Passed the paper's own rules but landed in a zero-point band: the band decides.
            return _with(r, outcome=PaperOutcome.FAIL, grade=band.grade, grade_point=ZERO)
        return _with(r, grade=band.grade, grade_point=band.grade_point)

    def aggregate(self, papers: Sequence[PaperResult], cfg: GradingConfig) -> ExamResult:
        assert isinstance(cfg, CreditGpaConfig)
        early, counted = _exam_outcome(papers)
        if early is not None:
            return ExamResult(outcome=early, papers=tuple(papers))
        total, max_total, percentage = _totals(counted, cfg)
        attempted = [
            p
            for p in counted
            if p.credits is not None
            and p.credits > 0
            and (p.outcome is not PaperOutcome.ABSENT or cfg.count_absent_as_attempted)
        ]
        credits = sum((p.credits or ZERO for p in attempted), ZERO)
        sgpa = None
        if credits > 0:
            with localcontext() as ctx:
                ctx.prec = 28
                ctx.rounding = ROUND_HALF_EVEN
                raw = sum(((p.grade_point or ZERO) * (p.credits or ZERO) for p in attempted), ZERO) / credits
            sgpa = cfg.rounding.q(raw, cfg.rounding.gpa_places)
        earned = sum((p.credits or ZERO for p in counted if p.passed and p.credits), ZERO)
        passed = _passed_overall(counted, percentage, cfg)
        return ExamResult(
            outcome=ExamOutcome.PASS if passed else ExamOutcome.FAIL,
            papers=tuple(papers),
            total=total,
            max_total=max_total,
            percentage=percentage,
            sgpa=sgpa,
            credits_attempted=credits,
            credits_earned=earned,
        )


class MarksOnlyStrategy:
    code = "marks_only"

    def grade_paper(self, paper: PaperSpec, mark: MarkInput | None, cfg: GradingConfig) -> PaperResult:
        assert isinstance(cfg, MarksOnlyConfig)
        return score_paper(paper, mark, cfg)

    def aggregate(self, papers: Sequence[PaperResult], cfg: GradingConfig) -> ExamResult:
        assert isinstance(cfg, MarksOnlyConfig)
        early, counted = _exam_outcome(papers)
        if early is not None:
            return ExamResult(outcome=early, papers=tuple(papers))
        total, max_total, percentage = _totals(counted, cfg)
        passed = _passed_overall(counted, percentage, cfg)
        return ExamResult(
            outcome=ExamOutcome.PASS if passed else ExamOutcome.FAIL,
            papers=tuple(papers),
            total=total,
            max_total=max_total,
            percentage=percentage,
        )


REGISTRY: dict[str, GradingStrategy] = {
    s.code: s for s in (PercentageBandsStrategy(), CreditGpaStrategy(), MarksOnlyStrategy())
}
