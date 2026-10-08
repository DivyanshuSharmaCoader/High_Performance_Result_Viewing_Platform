"""The student-facing snapshot (P10.2): exact shape, canonical numbers, hash, what students may see."""

from __future__ import annotations

from decimal import Decimal

from app.modules.publishing.snapshot import (
    ExamInfo,
    Institution,
    PaperInfo,
    SchemeInfo,
    StudentInfo,
    build_payload,
    payload_hash,
    student_stats,
)

INT = {"code": "INT", "label": "Internal", "max": "40"}
EXT = {"code": "EXT", "label": "External", "max": "60", "min_pass": "21"}
PAPERS = {
    "p1": PaperInfo("p1", "UCS301", "Data Structures", Decimal("4.0"), [INT, EXT]),
    "p2": PaperInfo("p2", "UMA101", "Maths", None, [{"code": "TH", "label": "Theory", "max": "100"}]),
}


def _payload(**result: object) -> dict:
    return build_payload(
        institution=Institution("Thapar Institute of Engineering & Technology", "Thapar Institute"),
        exam=ExamInfo("End semester", "semester", "Odd semester", "2025-26"),
        scheme=SchemeInfo("10-point scale", "credit_gpa"),
        student=StudentInfo("102303001", "Aarav Gupta", "COE-2A", "Group A", "B.E. Computer Engineering"),
        result={
            "outcome": "pass",
            "total": Decimal("85.000"),
            "max_total": Decimal("100.000"),
            "percentage": Decimal("85.000"),
            "grade": None,
            "grade_point": None,
            "sgpa": Decimal("9.000"),
            "credits_attempted": Decimal("4.00"),
            "credits_earned": Decimal("4.00"),
            "rank": None,
            "notes": [],
        }
        | result,
        papers=[
            {
                "exam_paper_id": "p1",
                "outcome": "pass",
                "attendance": "present",
                "components": {"INT": "35", "EXT": "50"},
                "total": Decimal("85.000"),
                "max_total": Decimal("100.000"),
                "percentage": Decimal("85.000"),
                "grade": "A+",
                "grade_point": Decimal("9.000"),
                "failed_components": [],
                "missing_components": [],
            }
        ],
        paper_info=PAPERS,
    )


def test_the_payload_is_exactly_what_the_student_sees() -> None:
    assert _payload() == {
        "schema": 1,
        "institution": {
            "name": "Thapar Institute of Engineering & Technology",
            "display_name": "Thapar Institute",
        },
        "exam": {"name": "End semester", "kind": "semester", "term": "Odd semester", "session": "2025-26"},
        "scheme": {"name": "10-point scale", "strategy": "credit_gpa"},
        "student": {
            "enrollment_no": "102303001",
            "full_name": "Aarav Gupta",
            "cohort": {"code": "COE-2A", "name": "Group A"},
            "program": "B.E. Computer Engineering",
        },
        "result": {
            "outcome": "pass",
            "total": "85",
            "max_total": "100",
            "percentage": "85",
            "grade": None,
            "grade_point": None,
            "sgpa": "9",
            "credits_attempted": "4",
            "credits_earned": "4",
            "rank": None,
            "notes": [],
        },
        "papers": [  # p2 has no result for this student, so it isn't listed
            {
                "course_code": "UCS301",
                "course_name": "Data Structures",
                "credits": "4",
                "attendance": "present",
                "outcome": "pass",
                "total": "85",
                "max_total": "100",
                "percentage": "85",
                "grade": "A+",
                "grade_point": "9",
                "failed_components": [],
                "missing_components": [],
                "components": [
                    {"code": "INT", "label": "Internal", "max": "40", "marks": "35"},
                    {"code": "EXT", "label": "External", "max": "60", "marks": "50"},
                ],
            }
        ],
    }


def test_no_internal_identifiers_leak_into_the_payload() -> None:
    text = str(_payload())
    for internal in ("p1", "p2", "exam_paper_id", "student_id", "input_hash", "run"):
        assert f"'{internal}'" not in text


def test_the_hash_is_stable_and_covers_every_field() -> None:
    a, b = _payload(), _payload()
    assert payload_hash(a) == payload_hash(b) and len(payload_hash(a)) == 64
    assert payload_hash(_payload(total=Decimal("85.0"))) == payload_hash(a)  # same number, other scale
    assert payload_hash(_payload(total=Decimal("86"))) != payload_hash(a)
    assert payload_hash(_payload(notes=["Revised after re-evaluation"])) != payload_hash(a)


STATS = {
    "students": 4,
    "outcomes": {"pass": 2, "fail": 1, "absent": 1, "withheld": 0, "incomplete": 0},
    "pass_percentage": "66.7",
    "average_percentage": "53.33",
    "median_percentage": "50",
    "stdev_percentage": "24.5",
    "histogram": [{"from": 0, "to": 10, "count": 0}],
    "grades": [{"grade": "A+", "count": 1}],
    "grades_basis": "paper",
    "papers": [
        {
            "paper_id": "p1",
            "course_code": "UCS301",
            "course_name": "Data Structures",
            "max_total": "100",
            "appeared": 3,
            "passed": 2,
            "pass_percentage": "66.7",
            "absent": 1,
            "incomplete": 0,
            "average": "53.33",
            "highest": "85",
            "lowest": "25",
            "median": "50",
            "stdev": "24.5",
        }
    ],
    "cohorts": [{"cohort_id": "c1", "code": "X-A", "name": "Class X A", "students": 4}],
}


def test_students_see_only_the_statistics_the_institution_allows() -> None:
    assert student_stats(STATS, "none") is None
    assert student_stats(STATS, "class_average") == {
        "average_percentage": "53.33",
        "papers": [{"course_code": "UCS301", "average": "53.33", "max_total": "100"}],
    }
    full = student_stats(STATS, "full")
    assert full is not None
    assert full["pass_percentage"] == "66.7" and full["histogram"] == STATS["histogram"]
    assert full["stdev_percentage"] == "24.5"
    assert full["papers"] == [
        {
            "course_code": "UCS301",
            "average": "53.33",
            "max_total": "100",
            "highest": "85",
            "median": "50",
            "pass_percentage": "66.7",
        }
    ]
    # Nothing beyond what's listed: no lowest score, no ids, and no section-by-section comparison.
    assert "lowest" not in str(full) and "paper_id" not in str(full)
    assert "cohorts" not in full and "X-A" not in str(full)
