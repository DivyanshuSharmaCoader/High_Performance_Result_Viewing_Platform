"""Result computation without a database (P9.2): determinism, hashes, statistics and anomalies.

Expected figures are worked out by hand from the six students below (two papers, 200 marks in all).
"""

from __future__ import annotations

import random
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.grading.engine import Component, PaperSpec
from app.modules.grading.templates import BY_KEY
from app.modules.results.compute import (
    Inputs,
    Mark,
    Paper,
    ProcessingError,
    Student,
    anomalies,
    compute,
    input_hash,
    num,
    result_doc,
    statistics,
)

P1 = Paper(
    PaperSpec(
        "p1",
        (
            Component("INT", Decimal(40), label="Internal"),
            Component("EXT", Decimal(60), Decimal(21), "External"),
        ),
        credits=Decimal(4),
    ),
    "UCS301",
    "Data Structures",
)
P2 = Paper(
    PaperSpec("p2", (Component("TH", Decimal(100), label="Theory"),), credits=Decimal(3)), "UMA101", "Maths"
)
STUDENTS = tuple(Student(f"s{i}", f"A00{i}", f"Student {i}", "c1") for i in range(1, 7))


def _marks() -> dict[tuple[str, str], Mark]:
    m = {
        ("p1", "s1"): Mark({"INT": "40", "EXT": "60"}, "present"),
        ("p2", "s1"): Mark({"TH": "100"}, "present"),
        ("p1", "s2"): Mark({"INT": "30", "EXT": "40"}, "present"),
        ("p2", "s2"): Mark({"TH": "55"}, "present"),
        ("p1", "s3"): Mark({"INT": "20"}, "present"),  # EXT missing
        ("p2", "s3"): Mark({"TH": "50"}, "present"),
        # s4: nothing entered
        ("p1", "s5"): Mark({}, "absent"),
        ("p2", "s5"): Mark({}, "absent"),
        ("p1", "s6"): Mark({"INT": "10", "EXT": "15"}, "present"),  # EXT below its minimum of 21
        ("p2", "s6"): Mark({"TH": "30"}, "present"),
    }
    return m


def inputs(template: str = "simple_letters", **changes: object) -> Inputs:
    base: dict[str, object] = {
        "scheme_version_id": "v1",
        "config": BY_KEY[template].config,
        "papers": (P1, P2),
        "students": STUDENTS,
        "marks": _marks(),
    }
    base.update(changes)
    return Inputs(**base)  # type: ignore[arg-type]


def test_canonical_numbers() -> None:
    assert num(Decimal("72.50")) == "72.5"
    assert num(Decimal("100")) == num(Decimal("1E+2")) == "100"
    assert num(Decimal("0.00")) == num(Decimal("-0")) == "0"
    assert num(None) is None


def test_results_statistics_and_anomalies_for_a_hand_worked_exam() -> None:
    c = compute(inputs())
    by = {o.student.enrollment_no: o.result for o in c.outcomes}
    assert [o.student.enrollment_no for o in c.outcomes] == [f"A00{i}" for i in range(1, 7)]
    assert (by["A001"].outcome, by["A001"].percentage, by["A001"].grade) == ("pass", Decimal("100.00"), "A")
    assert (by["A002"].outcome, by["A002"].total, by["A002"].grade) == ("pass", Decimal("125.00"), "C")
    assert by["A003"].outcome == by["A004"].outcome == "incomplete"
    assert by["A005"].outcome == "absent"
    assert (by["A006"].outcome, by["A006"].grade) == ("fail", "F")

    s = statistics(c, (P1, P2))
    assert s["students"] == 6
    assert s["outcomes"] == {"pass": 2, "fail": 1, "absent": 1, "withheld": 0, "incomplete": 2}
    assert s["pass_percentage"] == "66.7"  # 2 of the 3 students with a result
    assert s["average_percentage"] == "63.33"  # (100 + 62.5 + 27.5) / 3
    assert s["median_percentage"] == "62.5"
    assert [b["count"] for b in s["histogram"]] == [0, 0, 1, 0, 0, 0, 1, 0, 0, 1]
    assert s["grades"] == [{"grade": "A", "count": 1}, {"grade": "C", "count": 1}, {"grade": "F", "count": 1}]
    p1, p2 = s["papers"]
    assert (p1["appeared"], p1["passed"], p1["pass_percentage"], p1["absent"], p1["incomplete"]) == (
        3,
        2,
        "66.7",
        1,
        2,
    )
    assert (p1["average"], p1["highest"], p1["lowest"]) == ("65", "100", "25")
    assert (p2["appeared"], p2["passed"], p2["pass_percentage"], p2["average"]) == (4, 3, "75", "58.75")
    # Spread (P13.1), by hand. Exam: percentages 100, 62.5, 27.5 → mean 63.333…, squared deviations
    # 1344.44 + 0.69 + 1284.03 = 2629.17, / 3 = 876.39, √ = 29.60 (population: the cohort is everyone).
    assert s["stdev_percentage"] == "29.6"
    # UCS301 totals 100, 70, 25: median 70; deviations 35, 5, −40 → (1225 + 25 + 1600) / 3 = 950, √ = 30.82.
    assert (p1["median"], p1["stdev"]) == ("70", "30.82")
    # UMA101 totals 100, 55, 50, 30: median (50 + 55) / 2 = 52.5; (1701.56 + 14.06 + 76.56 + 826.56) / 4
    # = 654.69, √ = 25.59.
    assert (p2["median"], p2["stdev"]) == ("52.5", "25.59")
    assert [b["count"] for b in p1["histogram"]] == [0, 0, 1, 0, 0, 0, 0, 1, 0, 1]  # 25%, 70%, 100%
    assert [b["count"] for b in p2["histogram"]] == [0, 0, 0, 1, 0, 2, 0, 0, 0, 1]  # 30%, 50%, 55%, 100%
    # Per section (all six in c1 here); names come from the caller.
    assert statistics(c, (P1, P2), {"c1": ("COE-1", "Section 1")})["cohorts"] == [
        {
            "cohort_id": "c1",
            "code": "COE-1",
            "name": "Section 1",
            "students": 6,
            "appeared": 3,
            "passed": 2,
            "pass_percentage": "66.7",
            "average_percentage": "63.33",
        }
    ]

    found = {a["code"]: a for a in anomalies(c, (P1, P2))}
    assert set(found) == {"NO_MARKS", "INCOMPLETE", "ABSENT_ALL", "ALL_MAX"}
    assert [i["enrollment_no"] for i in found["NO_MARKS"]["items"]] == ["A004"]
    assert found["INCOMPLETE"]["items"][0] == {
        "student_id": "s3",
        "enrollment_no": "A003",
        "full_name": "Student 3",
        "detail": "Missing: UCS301 (EXT)",
    }
    assert [i["enrollment_no"] for i in found["ABSENT_ALL"]["items"]] == ["A005"]
    assert [i["enrollment_no"] for i in found["ALL_MAX"]["items"]] == ["A001"]


def test_changes_since_the_previous_run_and_unsubmitted_papers_are_reported() -> None:
    c = compute(inputs())
    previous = {o.student.student_id: result_doc(o) for o in c.outcomes}
    previous["s2"] = previous["s2"] | {"total": "120", "grade": "D"}
    found = {
        a["code"]: a
        for a in anomalies(
            c,
            (P1, P2),
            previous=previous,
            unsubmitted=[{"course_code": "UCS301", "cohort_code": "G1", "status": "returned"}],
        )
    }
    assert found["CHANGED"]["count"] == 1
    assert found["CHANGED"]["items"][0]["detail"] == "Total 120 → 125; grade D → C"
    assert found["UNSUBMITTED"]["items"] == [{"detail": "UCS301 · G1 (returned)"}]


def test_credit_schemes_report_paper_grades() -> None:
    s = statistics(compute(inputs("credit_10_point")), (P1, P2))
    assert s["grades_basis"] == "paper"  # the exam itself gets an SGPA, not a grade
    # Hand-worked: P1 100% O, 70% A, 25% F (EXT below 21); P2 100% O, 55% B, 50% B, 30% F.
    assert s["grades"] == [
        {"grade": "O", "count": 2},
        {"grade": "A", "count": 1},
        {"grade": "B", "count": 2},
        {"grade": "F", "count": 2},
    ]
    assert statistics(compute(inputs()), (P1, P2))["grades_basis"] == "exam"


def test_ranks_follow_the_scheme() -> None:
    c = compute(inputs("marks_with_ranks"))
    ranks = {o.student.enrollment_no: o.rank for o in c.outcomes}
    assert ranks == {"A001": 1, "A002": 2, "A006": 3, "A003": None, "A004": None, "A005": None}
    assert all(o.rank is None for o in compute(inputs()).outcomes)  # simple_letters has no ranking


def test_running_twice_gives_identical_results_and_hashes() -> None:
    a, b = compute(inputs()), compute(inputs())
    assert a.content_hash == b.content_hash
    assert [result_doc(o) for o in a.outcomes] == [result_doc(o) for o in b.outcomes]
    assert input_hash(inputs()) == input_hash(inputs())


def test_the_input_hash_covers_everything_results_depend_on() -> None:
    base = input_hash(inputs())
    changed_mark = _marks() | {("p2", "s2"): Mark({"TH": "56"}, "present")}
    changed_attendance = _marks() | {("p2", "s2"): Mark({}, "absent")}
    only_attendance = _marks() | {("p1", "s5"): Mark({}, "exempt")}  # still no marks; only the code moves
    moved = tuple(
        Student(s.student_id, s.enrollment_no, s.full_name, "c2" if s.student_id == "s1" else "c1")
        for s in STUDENTS
    )
    tighter = Paper(PaperSpec("p2", (Component("TH", Decimal(90)),), credits=Decimal(3)), "UMA101", "Maths")
    variants = [
        inputs(marks=changed_mark),
        inputs(marks=changed_attendance),
        inputs(marks=only_attendance),
        inputs(students=moved),
        inputs(students=STUDENTS[:5]),
        inputs(scheme_version_id="v2"),
        inputs(papers=(P1, tighter)),
    ]
    hashes = [input_hash(v) for v in variants]
    assert base not in hashes and len(set(hashes)) == len(hashes)
    # Marks of someone who doesn't sit the exam change nothing.
    stray = _marks() | {("p1", "s99"): Mark({"INT": "1"}, "present")}
    assert input_hash(inputs(marks=stray)) == base


def test_ungradable_marks_fail_the_run_naming_the_student() -> None:
    bad = _marks() | {("p1", "s2"): Mark({"INT": "45", "EXT": "40"}, "present")}
    with pytest.raises(ProcessingError, match=r"^A002: "):
        compute(inputs(marks=bad))


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.integers(0, 40),
            st.integers(0, 60),
            st.integers(0, 100),
            st.sampled_from(["present", "present", "present", "absent", None]),
        ),
        min_size=1,
        max_size=25,
    ),
    st.randoms(use_true_random=False),
)
def test_input_order_never_changes_results_or_hashes(
    rows: list[tuple[int, int, int, str | None]], rnd: random.Random
) -> None:
    students = tuple(Student(f"id{i:03}", f"E{i:03}", f"N{i}", f"c{i % 3}") for i in range(len(rows)))
    marks: dict[tuple[str, str], Mark] = {}
    for s, (a, b, t, att) in zip(students, rows, strict=True):
        if att is None:
            continue
        marks[("p1", s.student_id)] = Mark({"INT": str(a), "EXT": str(b)} if att == "present" else {}, att)
        marks[("p2", s.student_id)] = Mark({"TH": str(t)} if att == "present" else {}, att)
    for template in ("credit_10_point", "marks_with_ranks"):
        first = inputs(template, students=students, marks=marks)
        shuffled_students = list(students)
        rnd.shuffle(shuffled_students)
        items = list(marks.items())
        rnd.shuffle(items)
        second = inputs(template, students=tuple(shuffled_students), marks=dict(items), papers=(P1, P2))
        assert input_hash(first) == input_hash(second)
        a, b = compute(first), compute(second)
        assert a.content_hash == b.content_hash
        assert [result_doc(o) for o in a.outcomes] == [result_doc(o) for o in b.outcomes]


def test_sections_are_compared_side_by_side() -> None:
    students = tuple(
        Student(f"s{i}", f"A00{i}", f"Student {i}", "c1" if i <= 3 else "c2") for i in range(1, 7)
    )
    s = statistics(compute(inputs(students=students)), (P1, P2), {"c1": ("A", "Sec A"), "c2": ("B", "Sec B")})
    a, b = s["cohorts"]
    # A: A001 pass 100%, A002 pass 62.5%, A003 incomplete. B: A004 incomplete, A005 absent, A006 fail 27.5%.
    assert (a["code"], a["students"], a["appeared"], a["passed"], a["pass_percentage"]) == (
        "A",
        3,
        2,
        2,
        "100",
    )
    assert a["average_percentage"] == "81.25"
    assert (b["code"], b["students"], b["appeared"], b["passed"], b["pass_percentage"]) == ("B", 3, 1, 0, "0")
    assert b["average_percentage"] == "27.5"
    assert statistics(compute(inputs(marks={})), (P1, P2))["stdev_percentage"] is None  # nothing to spread
