"""Grading engine rules, one at a time (P7.1). Expected values are worked out by hand in the comments."""

from __future__ import annotations

from decimal import Decimal as D  # noqa: N817 - short alias keeps expected values readable
from typing import Any

import pytest

from app.modules.grading.engine import (
    Attendance,
    Component,
    ExamOutcome,
    GradingConfigError,
    GradingInputError,
    MarkInput,
    PaperOutcome,
    PaperSpec,
    assign_ranks,
    grade_exam,
    parse_config,
)

BANDS = [
    {"grade": "A", "min_percentage": "80", "grade_point": "10"},
    {"grade": "B", "min_percentage": "60", "grade_point": "8"},
    {"grade": "C", "min_percentage": "40", "grade_point": "6"},
    {"grade": "D", "min_percentage": "0", "grade_point": "0"},
]


def paper(
    pid: str = "P1", *, credits: str | None = None, pass_total: str | None = None, **comps: Any
) -> PaperSpec:
    """``paper(INT=(40, 16), EXT=60)`` → components INT max 40 min_pass 16, EXT max 60."""
    components = []
    for code, spec in (comps or {"T": 100}).items():
        mx, mp = spec if isinstance(spec, tuple) else (spec, None)
        components.append(Component(code, D(str(mx)), D(str(mp)) if mp is not None else None))
    return PaperSpec(
        pid,
        tuple(components),
        credits=D(credits) if credits else None,
        pass_total=D(pass_total) if pass_total else None,
    )


def marks(attendance: Attendance = Attendance.PRESENT, **values: Any) -> MarkInput:
    return MarkInput({k: (D(str(v)) if v is not None else None) for k, v in values.items()}, attendance)


def bands_cfg(**extra: Any):
    return parse_config({"strategy": "percentage_bands", "bands": BANDS, **extra})


def credit_cfg(**extra: Any):
    return parse_config({"strategy": "credit_gpa", "bands": BANDS, **extra})


# ---- configuration ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"strategy": "magic"}, "Choose a grading strategy"),
        ({"strategy": "percentage_bands", "bands": []}, "at least one grade band"),
        (
            {"strategy": "percentage_bands", "bands": [{"grade": "A", "min_percentage": "50"}]},
            "lowest band must start at 0%",
        ),
        (
            {
                "strategy": "percentage_bands",
                "bands": [{"grade": "A", "min_percentage": "40"}, {"grade": "B", "min_percentage": "60"}],
            },
            "highest to lowest",
        ),
        (
            {
                "strategy": "percentage_bands",
                "bands": [{"grade": "A", "min_percentage": "50"}, {"grade": "A", "min_percentage": "0"}],
            },
            "only once",
        ),
        (
            {"strategy": "credit_gpa", "bands": [{"grade": "A", "min_percentage": "0"}]},
            "needs grade points",
        ),
        (
            {
                "strategy": "credit_gpa",
                "bands": [
                    {"grade": "A", "min_percentage": "50", "grade_point": "5"},
                    {"grade": "B", "min_percentage": "0", "grade_point": "9"},
                ],
            },
            "must not increase",
        ),
        ({"strategy": "marks_only", "colour": "red"}, "Extra inputs are not permitted"),
        ({"strategy": "marks_only", "rounding": {"mode": "bankers"}}, "rounding.mode"),
        (
            {"strategy": "marks_only", "pass_rules": {"overall_pass_percentage": "101"}},
            "less than or equal to 100",
        ),
    ],
)
def test_invalid_configs_are_rejected_with_a_reason(config: dict[str, Any], message: str) -> None:
    with pytest.raises(GradingConfigError, match=message):
        parse_config(config)


def test_config_roundtrips_through_json() -> None:
    cfg = credit_cfg(rounding={"mode": "half_even", "gpa_places": 1})
    from app.modules.grading.engine import config_to_json

    again = parse_config(config_to_json(cfg))
    assert again == cfg and again.rounding.gpa_places == 1


# ---- papers ---------------------------------------------------------------------------------------


def test_component_minimums_and_paper_pass_total() -> None:
    p = paper(INT=(40, 16), EXT=(60, 24), pass_total="40")
    cfg = bands_cfg()
    ok = grade_exam([p], {"P1": marks(INT=16, EXT=24)}, cfg)  # 40/100: meets everything exactly
    assert ok.outcome is ExamOutcome.PASS and ok.papers[0].grade == "C"
    low_ext = grade_exam([p], {"P1": marks(INT=40, EXT=23.5)}, cfg)  # 63.5 total, but EXT < 24
    assert low_ext.papers[0].outcome is PaperOutcome.FAIL
    assert low_ext.papers[0].failed_components == ("EXT",) and low_ext.outcome is ExamOutcome.FAIL
    assert low_ext.papers[0].grade == "B"  # no fail_grade configured: band grade is kept
    total_rule = paper(T=100, pass_total="40")  # no component minimums: only the total rule
    assert grade_exam([total_rule], {"P1": marks(T=40)}, cfg).outcome is ExamOutcome.PASS
    under = grade_exam([total_rule], {"P1": marks(T="39.99")}, cfg)
    assert under.papers[0].outcome is PaperOutcome.FAIL and under.papers[0].failed_components == ()


def test_scheme_pass_percentage_applies_when_a_paper_has_no_pass_total() -> None:
    cfg = bands_cfg(pass_rules={"paper_pass_percentage": "33"}, fail_grade="E")
    p = paper(T=80)
    # 33% of 80 = 26.4: 26.5 passes, 26 fails (and shows the fail grade)
    assert grade_exam([p], {"P1": marks(T=26.5)}, cfg).outcome is ExamOutcome.PASS
    failed = grade_exam([p], {"P1": marks(T=26)}, cfg)
    assert failed.outcome is ExamOutcome.FAIL and failed.papers[0].grade == "E" and failed.grade == "E"


def test_band_boundaries_use_the_rounded_percentage() -> None:
    p = paper(T=300)
    cfg = bands_cfg()
    # 239.99/300 = 79.9966…% → rounds to 80.00% → grade A (what the marksheet shows)
    r = grade_exam([p], {"P1": marks(T="239.99")}, cfg)
    assert r.percentage == D("80.00") and r.grade == "A"
    r = grade_exam([p], {"P1": marks(T="239.98")}, cfg)  # 79.9933…% → 79.99% → B
    assert r.percentage == D("79.99") and r.grade == "B"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("half_up", D("66.67")), ("half_even", D("66.67")), ("down", D("66.66")), ("up", D("66.67"))],
)
def test_rounding_modes(mode: str, expected: D) -> None:
    # 200/300 = 66.666…%
    cfg = parse_config({"strategy": "marks_only", "rounding": {"mode": mode}})
    assert grade_exam([paper(T=300)], {"P1": marks(T=200)}, cfg).percentage == expected


def test_half_up_differs_from_half_even_on_exact_halves() -> None:
    # 1/8 = 12.5% exactly; with 0 places half_up → 13, half_even → 12
    up = parse_config({"strategy": "marks_only", "rounding": {"mode": "half_up", "percentage_places": 0}})
    even = parse_config({"strategy": "marks_only", "rounding": {"mode": "half_even", "percentage_places": 0}})
    assert grade_exam([paper(T=8)], {"P1": marks(T=1)}, up).percentage == D("13")
    assert grade_exam([paper(T=8)], {"P1": marks(T=1)}, even).percentage == D("12")


def test_invalid_marks_are_refused_not_graded() -> None:
    cfg = bands_cfg()
    with pytest.raises(GradingInputError, match="outside 0–100"):
        grade_exam([paper()], {"P1": marks(T=101)}, cfg)
    with pytest.raises(GradingInputError, match="outside"):
        grade_exam([paper()], {"P1": marks(T=-1)}, cfg)
    with pytest.raises(GradingInputError, match="unknown component"):
        grade_exam([paper()], {"P1": marks(T=50, X=1)}, cfg)


# ---- attendance and completeness ----------------------------------------------------------------


def test_attendance_outcomes() -> None:
    cfg = bands_cfg()
    p1, p2 = paper("P1"), paper("P2")
    present = marks(T=90)
    absent_one = grade_exam([p1, p2], {"P1": present, "P2": marks(Attendance.ABSENT)}, cfg)
    assert absent_one.outcome is ExamOutcome.FAIL  # an absent paper fails the exam
    assert absent_one.papers[1].grade == "AB" and absent_one.papers[1].grade_point == D(0)
    assert absent_one.total == D("90.00") and absent_one.max_total == D(200)
    assert grade_exam(
        [p1, p2], {"P1": marks(Attendance.ABSENT), "P2": marks(Attendance.ABSENT)}, cfg
    ).outcome is (ExamOutcome.ABSENT)
    exempt = grade_exam([p1, p2], {"P1": present, "P2": marks(Attendance.EXEMPT)}, cfg)
    assert (
        exempt.outcome is ExamOutcome.PASS and exempt.max_total == D(100) and exempt.percentage == D("90.00")
    )
    for att in (Attendance.WITHHELD, Attendance.MALPRACTICE):
        r = grade_exam([p1, p2], {"P1": present, "P2": marks(att)}, cfg)
        assert r.outcome is ExamOutcome.WITHHELD and r.total is None and r.grade is None
    missing_paper = grade_exam([p1, p2], {"P1": present}, cfg)
    assert missing_paper.outcome is ExamOutcome.INCOMPLETE
    assert missing_paper.papers[1].missing_components == ("T",)
    blank = grade_exam([paper(INT=40, EXT=60)], {"P1": marks(INT=30, EXT=None)}, cfg)
    assert blank.outcome is ExamOutcome.INCOMPLETE and blank.papers[0].missing_components == ("EXT",)
    all_exempt = grade_exam([p1], {"P1": marks(Attendance.EXEMPT)}, cfg)
    assert all_exempt.outcome is ExamOutcome.INCOMPLETE


def test_overall_rules() -> None:
    p1, p2 = paper("P1"), paper("P2")
    lenient = bands_cfg(pass_rules={"require_all_papers": False, "overall_pass_percentage": "50"})
    r = grade_exam([p1, p2], {"P1": marks(T=90), "P2": marks(T=20)}, lenient)  # 110/200 = 55%
    assert r.outcome is ExamOutcome.PASS and r.percentage == D("55.00") and r.grade == "C"
    r = grade_exam([p1, p2], {"P1": marks(T=60), "P2": marks(T=20)}, lenient)  # 40% < 50%
    assert r.outcome is ExamOutcome.FAIL
    # average grade point: A(10) and D(0) → 5.00
    assert grade_exam([p1, p2], {"P1": marks(T=90), "P2": marks(T=20)}, bands_cfg()).grade_point == D("5.00")


# ---- credit / SGPA --------------------------------------------------------------------------------


def test_sgpa_is_credit_weighted() -> None:
    cfg = credit_cfg(pass_rules={"paper_pass_percentage": "40"})
    papers = [paper("A", credits="4"), paper("B", credits="3"), paper("C", credits="1"), paper("D")]
    r = grade_exam(
        papers,
        {"A": marks(T=85), "B": marks(T=65), "C": marks(T=30), "D": marks(T=99)},
        cfg,
    )
    # A: 10×4 = 40, B: 8×3 = 24, C: fails (30 < 40) → F, 0×1; D has no credits → not in SGPA
    # SGPA = 64 / 8 = 8.00; credits earned = 4 + 3 = 7
    assert [p.grade for p in r.papers] == ["A", "B", "F", "A"]
    assert r.sgpa == D("8.00") and r.credits_attempted == D(8) and r.credits_earned == D(7)
    assert r.outcome is ExamOutcome.FAIL


def test_sgpa_rounding_and_absent_credits() -> None:
    cfg = credit_cfg()
    papers = [paper("A", credits="3"), paper("B", credits="3"), paper("C", credits="3")]
    r = grade_exam(papers, {"A": marks(T=85), "B": marks(T=85), "C": marks(T=65)}, cfg)
    assert r.sgpa == D("9.33")  # (30 + 30 + 24) / 9 = 9.333…
    absent = grade_exam(papers, {"A": marks(T=85), "B": marks(T=85), "C": marks(Attendance.ABSENT)}, cfg)
    assert absent.sgpa == D("6.67") and absent.credits_attempted == D(9)  # 60 / 9
    ignore = credit_cfg(count_absent_as_attempted=False)
    absent = grade_exam(papers, {"A": marks(T=85), "B": marks(T=85), "C": marks(Attendance.ABSENT)}, ignore)
    assert absent.sgpa == D("10.00") and absent.credits_attempted == D(6)


def test_zero_point_band_fails_the_paper_in_credit_schemes() -> None:
    cfg = credit_cfg()  # band D starts at 0 with 0 points; no paper pass rule
    r = grade_exam([paper(credits="2")], {"P1": marks(T=35)}, cfg)
    assert r.papers[0].outcome is PaperOutcome.FAIL and r.papers[0].grade == "D" and r.sgpa == D("0.00")


# ---- ranks ----------------------------------------------------------------------------------------


def test_ranks_share_ties_and_skip_unranked_outcomes() -> None:
    cfg = parse_config({"strategy": "marks_only"})
    p = [paper()]
    results = {
        "s1": grade_exam(p, {"P1": marks(T=90)}, cfg),
        "s2": grade_exam(p, {"P1": marks(T=95)}, cfg),
        "s3": grade_exam(p, {"P1": marks(T=90)}, cfg),
        "s4": grade_exam(p, {"P1": marks(T=40)}, cfg),
        "s5": grade_exam(p, {"P1": marks(Attendance.ABSENT)}, cfg),
    }
    assert assign_ranks(results, "competition") == {"s1": 2, "s2": 1, "s3": 2, "s4": 4, "s5": None}
    assert assign_ranks(results, "dense") == {"s1": 2, "s2": 1, "s3": 2, "s4": 3, "s5": None}
    assert assign_ranks(results, "none") == dict.fromkeys(results)
    reordered = dict(reversed(list(results.items())))
    assert assign_ranks(reordered, "competition") == assign_ranks(results, "competition")
