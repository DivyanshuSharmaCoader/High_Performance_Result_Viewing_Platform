"""Starter grading schemes an admin can begin from (then edit freely).

All are generic and illustrative — none claims to be a specific board's or university's official policy.
The first three reproduce the hand-checked golden tables in ``tests/fixtures/grading`` exactly (a test
grades those tables with the templates), so their behaviour is pinned by worked examples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    description: str
    config: dict[str, Any]


def _bands(rows: list[tuple[str, str, str | None]]) -> list[dict[str, str]]:
    return [
        {"grade": g, "min_percentage": m, **({"grade_point": p} if p is not None else {})} for g, m, p in rows
    ]


TEMPLATES: tuple[Template, ...] = (
    Template(
        "board_9_point",
        "9-band scale (CBSE-style)",
        "A1–E grades from percentage bands with 10–4 grade points; 33% to pass each subject.",
        {
            "strategy": "percentage_bands",
            "bands": _bands(
                [
                    ("A1", "91", "10"),
                    ("A2", "81", "9"),
                    ("B1", "71", "8"),
                    ("B2", "61", "7"),
                    ("C1", "51", "6"),
                    ("C2", "41", "5"),
                    ("D", "33", "4"),
                    ("E", "0", "0"),
                ]
            ),
            "fail_grade": "E",
            "pass_rules": {"paper_pass_percentage": "33", "require_all_papers": True},
            "rounding": {"mode": "half_up", "percentage_places": 2, "gpa_places": 2},
        },
    ),
    Template(
        "credit_10_point",
        "10-point credit scale with SGPA (CBCS-style)",
        "O, A+, A, B+, B, C, P, F letter grades with credit-weighted SGPA; 40% to pass each course.",
        {
            "strategy": "credit_gpa",
            "bands": _bands(
                [
                    ("O", "90", "10"),
                    ("A+", "80", "9"),
                    ("A", "70", "8"),
                    ("B+", "60", "7"),
                    ("B", "50", "6"),
                    ("C", "45", "5"),
                    ("P", "40", "4"),
                    ("F", "0", "0"),
                ]
            ),
            "fail_grade": "F",
            "absent_grade": "AB",
            "count_absent_as_attempted": True,
            "pass_rules": {"paper_pass_percentage": "40", "require_all_papers": True},
            "rounding": {"mode": "half_up", "percentage_places": 2, "gpa_places": 2},
        },
    ),
    Template(
        "marks_with_ranks",
        "Marks and ranks (coaching tests)",
        "Totals and percentages only, with ranks; equal scores share a rank.",
        {
            "strategy": "marks_only",
            "ranking": "competition",
            "rounding": {"mode": "half_up", "percentage_places": 2},
        },
    ),
    Template(
        "simple_letters",
        "Simple letter grades (A–F)",
        "A ≥ 80%, B ≥ 65%, C ≥ 50%, D ≥ 35%, otherwise F; 35% to pass each paper.",
        {
            "strategy": "percentage_bands",
            "bands": _bands(
                [("A", "80", None), ("B", "65", None), ("C", "50", None), ("D", "35", None), ("F", "0", None)]
            ),
            "fail_grade": "F",
            "pass_rules": {"paper_pass_percentage": "35", "require_all_papers": True},
            "rounding": {"mode": "half_up", "percentage_places": 2},
        },
    ),
)

BY_KEY = {t.key: t for t in TEMPLATES}
