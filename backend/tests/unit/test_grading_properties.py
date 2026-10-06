"""Property-based tests for every grading strategy (P7.1, docs/08 §3 "Liskov", docs/15).

Each property holds for *any* valid scheme and *any* valid marks Hypothesis can generate:

* bounded       — 0 ≤ percentage ≤ 100, total ≤ max, 0 ≤ SGPA ≤ the scheme's best grade point;
* deterministic — the same inputs give the same result, whatever the order of the papers;
* monotonic     — more marks never lower the percentage, grade, grade points or SGPA, and never turn
                  a pass into a fail;
* absence       — an absent paper never passes and, with "all papers must pass", fails the exam.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D  # noqa: N817 - short alias keeps expected values readable
from typing import Any

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.modules.grading.engine import (
    Attendance,
    Component,
    CreditGpaConfig,
    ExamOutcome,
    ExamResult,
    GradingConfig,
    MarkInput,
    PaperOutcome,
    PaperSpec,
    PercentageBandsConfig,
    grade_exam,
    parse_config,
)

SETTINGS = settings(max_examples=300, deadline=None)
GRADES = ["A1", "A2", "B1", "B2", "C1", "C2", "D", "E"]


@st.composite
def schemes(draw: Any) -> GradingConfig:
    strategy = draw(st.sampled_from(["percentage_bands", "credit_gpa", "marks_only"]))
    n = draw(st.integers(1, 6))
    mins = [*sorted(draw(st.sets(st.integers(1, 99), min_size=n - 1, max_size=n - 1)), reverse=True), 0]
    points = sorted(draw(st.lists(st.integers(0, 10), min_size=n, max_size=n)), reverse=True)
    with_points = strategy == "credit_gpa" or draw(st.booleans())
    bands = [
        {
            "grade": GRADES[i],
            "min_percentage": str(m),
            **({"grade_point": str(points[i])} if with_points else {}),
        }
        for i, m in enumerate(mins)
    ]
    config: dict[str, Any] = {
        "strategy": strategy,
        "rounding": {
            "mode": draw(st.sampled_from(["half_up", "half_even", "down", "up"])),
            "percentage_places": draw(st.integers(0, 3)),
            "gpa_places": draw(st.integers(0, 3)),
            "total_places": draw(st.integers(1, 3)),
        },
        "pass_rules": {
            "paper_pass_percentage": draw(st.none() | st.integers(0, 100).map(str)),
            "overall_pass_percentage": draw(st.none() | st.integers(0, 100).map(str)),
            "require_all_papers": draw(st.booleans()),
        },
    }
    if strategy != "marks_only":
        config["bands"] = bands
    if strategy == "percentage_bands" and draw(st.booleans()):
        config["fail_grade"] = "F"
    if strategy == "credit_gpa":
        config["count_absent_as_attempted"] = draw(st.booleans())
    return parse_config(config)


MAXES = [10, 20, 25, 30, 40, 50, 60, 70, 80, 100]


@st.composite
def papers(draw: Any) -> list[PaperSpec]:
    out = []
    for i in range(draw(st.integers(1, 5))):
        comps = []
        for j in range(draw(st.integers(1, 3))):
            mx = draw(st.sampled_from(MAXES))
            min_pass = draw(st.none() | st.integers(0, mx))
            comps.append(Component(f"C{j}", D(mx), D(min_pass) if min_pass is not None else None))
        total = sum(c.max for c in comps)
        pass_total = draw(st.none() | st.integers(0, int(total)))
        credits = draw(st.none() | st.integers(0, 5))
        out.append(
            PaperSpec(
                f"P{i}",
                tuple(comps),
                credits=D(credits) if credits is not None else None,
                pass_total=D(pass_total) if pass_total is not None else None,
            )
        )
    return out


def half_steps(mx: D) -> st.SearchStrategy[D]:
    return st.integers(0, int(mx * 2)).map(lambda n: D(n) / 2)


@st.composite
def exam_inputs(
    draw: Any, mostly_present: bool = True
) -> tuple[GradingConfig, list[PaperSpec], dict[str, MarkInput]]:
    cfg = draw(schemes())
    ps = draw(papers())
    attendance = (
        st.sampled_from([Attendance.PRESENT] * 6 + list(Attendance))
        if mostly_present
        else st.sampled_from(list(Attendance))
    )
    marks = {}
    for p in ps:
        att = draw(attendance)
        values = {c.code: draw(half_steps(c.max)) for c in p.components}
        marks[p.paper_id] = MarkInput(values, att)
    return cfg, ps, marks


def _grade_rank(cfg: GradingConfig, grade: str | None) -> int | None:
    """Lower is better: band order, with the fail grade worst of all."""
    if grade is None or not isinstance(cfg, PercentageBandsConfig | CreditGpaConfig):
        return None
    order = [b.grade for b in cfg.bands]
    return order.index(grade) if grade in order else len(order)


def _check_bounds(cfg: GradingConfig, r: ExamResult) -> None:
    for p in r.papers:
        if p.percentage is not None:
            assert D(0) <= p.percentage <= D(100)
        if p.total is not None:
            assert D(0) <= p.total <= p.max_total
    if r.percentage is not None:
        assert D(0) <= r.percentage <= D(100)
    if r.total is not None and r.max_total is not None:
        assert D(0) <= r.total <= r.max_total
    if r.sgpa is not None:
        assert isinstance(cfg, CreditGpaConfig)
        assert D(0) <= r.sgpa <= cfg.max_grade_point
    if r.credits_earned is not None and r.credits_attempted is not None:
        assert r.credits_earned >= 0 and r.credits_attempted >= 0


@SETTINGS
@given(exam_inputs())
def test_results_are_bounded(inputs: Any) -> None:
    cfg, ps, marks = inputs
    _check_bounds(cfg, grade_exam(ps, marks, cfg))


@SETTINGS
@given(exam_inputs(), st.randoms())
def test_results_are_deterministic_and_independent_of_paper_order(inputs: Any, rnd: Any) -> None:
    cfg, ps, marks = inputs
    first = grade_exam(ps, marks, cfg)
    assert grade_exam(ps, marks, cfg) == first
    shuffled = list(ps)
    rnd.shuffle(shuffled)
    again = grade_exam(shuffled, marks, cfg)
    for field in (
        "outcome",
        "total",
        "max_total",
        "percentage",
        "grade",
        "grade_point",
        "sgpa",
        "credits_earned",
    ):
        assert getattr(again, field) == getattr(first, field), field
    assert sorted(again.papers, key=lambda p: p.paper_id) == sorted(first.papers, key=lambda p: p.paper_id)


@SETTINGS
@given(exam_inputs(), st.data())
def test_more_marks_never_make_a_result_worse(inputs: Any, data: Any) -> None:
    cfg, ps, marks = inputs
    present = [p for p in ps if marks[p.paper_id].attendance is Attendance.PRESENT]
    assume(present)
    p = data.draw(st.sampled_from(present))
    c = data.draw(st.sampled_from(p.components))
    current = marks[p.paper_id].components[c.code]
    assert current is not None
    assume(current < c.max)
    higher = data.draw(st.integers(int(current * 2) + 1, int(c.max * 2)).map(lambda n: D(n) / 2))
    better_marks = {
        **marks,
        p.paper_id: replace(marks[p.paper_id], components={**marks[p.paper_id].components, c.code: higher}),
    }
    before, after = grade_exam(ps, marks, cfg), grade_exam(ps, better_marks, cfg)

    pb = next(x for x in before.papers if x.paper_id == p.paper_id)
    pa = next(x for x in after.papers if x.paper_id == p.paper_id)
    assert pa.percentage is not None and pb.percentage is not None and pa.percentage >= pb.percentage
    assert not (pb.outcome is PaperOutcome.PASS and pa.outcome is not PaperOutcome.PASS)
    rb, ra = _grade_rank(cfg, pb.grade), _grade_rank(cfg, pa.grade)
    if rb is not None and ra is not None:
        assert ra <= rb
    if pb.grade_point is not None and pa.grade_point is not None:
        assert pa.grade_point >= pb.grade_point

    assert after.outcome is not ExamOutcome.FAIL or before.outcome is not ExamOutcome.PASS
    if before.percentage is not None and after.percentage is not None:
        assert after.percentage >= before.percentage
    if before.sgpa is not None and after.sgpa is not None:
        assert after.sgpa >= before.sgpa
    rb, ra = _grade_rank(cfg, before.grade), _grade_rank(cfg, after.grade)
    if rb is not None and ra is not None:
        assert ra <= rb


@SETTINGS
@given(exam_inputs(mostly_present=False))
def test_absent_papers_never_pass(inputs: Any) -> None:
    cfg, ps, marks = inputs
    r = grade_exam(ps, marks, cfg)
    absent = [p for p in r.papers if p.outcome is PaperOutcome.ABSENT]
    assert all(not p.passed for p in absent)
    blocked = any(p.outcome in (PaperOutcome.WITHHELD, PaperOutcome.INCOMPLETE) for p in r.papers)
    if absent and cfg.pass_rules.require_all_papers and not blocked:
        assert r.outcome in (ExamOutcome.FAIL, ExamOutcome.ABSENT)
    if r.outcome is ExamOutcome.ABSENT:
        counted = [p for p in r.papers if p.outcome is not PaperOutcome.EXEMPT]
        assert counted and all(p.outcome is PaperOutcome.ABSENT for p in counted)
