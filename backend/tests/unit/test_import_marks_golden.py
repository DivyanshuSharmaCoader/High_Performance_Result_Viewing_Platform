"""Golden files for the marks import profile (P8.5): every rule in docs/13 §4 against a fixed context.

Regenerate after a deliberate change with ``UPDATE_GOLDEN=1`` and review the diff like code.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.modules.ingestion.engine import analyse, pick_sheet
from app.modules.ingestion.marks import MarksContext, MarksProfile, PaperRef, StudentRef, names_disagree
from app.modules.ingestion.parsers import Limits, parse_workbook

CORPUS = Path(__file__).resolve().parent.parent / "fixtures" / "imports" / "marks"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"
U = lambda name: uuid.uuid5(uuid.NAMESPACE_URL, name)  # noqa: E731 - stable ids for readable goldens

UCS301 = PaperRef(
    U("UCS301"),
    "UCS301",
    (
        {"code": "INT", "label": "Internal", "max": "40", "min_pass": None},
        {"code": "EXT", "label": "External", "max": "60", "min_pass": "21"},
    ),
)
UHU005 = PaperRef(U("UHU005"), "UHU005", ({"code": "T", "label": "Total", "max": "100", "min_pass": None},))
X, Y = U("cohort-X"), U("cohort-Y")


def _ctx(single: PaperRef | None) -> MarksContext:
    students = {
        "A001": StudentRef(U("A001"), "A001", "Asha Rao", X),
        "A002": StudentRef(U("A002"), "A002", "Bilal Khan", X),
        "A003": StudentRef(U("A003"), "A003", "Chitra Iyer", Y),
        "B999": StudentRef(U("B999"), "B999", "Not Sitting", None),
    }
    return MarksContext(
        exam_status="marks_entry_open",
        papers={"UCS301": UCS301, "UHU005": UHU005},
        students=students,
        existing={(UCS301.id, U("A001")): ({"INT": "30", "EXT": "40"}, "present", 2)},
        submissions={(UHU005.id, Y): "locked"},
        allowed=None,
        single=single,
        roster={X: {U("A001"), U("A002")}, Y: {U("A003")}},
        cohort_codes={X: "COE-2A", Y: "COE-2B"},
    )


def _outcome(path: Path) -> dict[str, Any]:
    single = UCS301 if "single_paper" in path.stem else None
    profile = MarksProfile(None, [UCS301, UHU005], single)
    sheet = pick_sheet(parse_workbook(path.read_bytes(), "csv", Limits()), profile.fields, None)
    result = analyse(sheet, profile, _ctx(single))
    return {
        "mapping": {k: result.columns[c] for k, c in sorted(result.mapping.items())},
        "missing": result.missing,
        "file_issues": [f"{i.code}: {i.message}" for i in result.file_issues],
        "summary": result.summary,
        "rows": [
            {
                "row": r.row_no,
                "status": r.status,
                "issues": [f"{i.code}: {i.message}" for i in r.issues],
                "items": [
                    {k: item[k] for k in ("course_code", "attendance", "components", "action", "version")}
                    for item in r.normalized.get("items", [])
                ],
            }
            for r in result.rows
        ],
    }


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.csv")), ids=lambda p: p.stem)
def test_marks_golden(path: Path) -> None:
    rendered = json.dumps(_outcome(path), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    expected = path.with_suffix(".expected.json")
    if UPDATE or not expected.exists():
        expected.write_text(rendered, encoding="utf-8")
        if not UPDATE:
            pytest.fail(f"wrote new golden file {expected.name}; review it and re-run")
    assert rendered == expected.read_text(encoding="utf-8")


def test_name_check_tolerates_initials_and_typos_but_catches_shifted_rows() -> None:
    assert not names_disagree("A. Rao", "Asha Rao")
    assert not names_disagree("Asha  RAO", "Asha Rao")
    assert names_disagree("Bilal Khan", "Asha Rao")


def test_faculty_scope_and_closed_entry() -> None:
    from app.modules.ingestion.engine import RowInput

    profile = MarksProfile(None, [UCS301, UHU005], UCS301)
    ctx = _ctx(UCS301)
    ctx.allowed = {(UCS301.id, X)}
    rows = [
        RowInput(2, [], {"enrollment_no": "A002", "c:INT": "12", "c:EXT": "30"}),
        RowInput(3, [], {"enrollment_no": "A003", "c:INT": "12", "c:EXT": "30"}),
    ]
    results, file_issues, _ = profile.validate(rows, ctx)
    assert [r.status for r in results] == ["valid", "error"]
    assert results[1].issues[0].code == "NOT_ASSIGNED"
    ctx.exam_status = "marks_entry_closed"
    _results, file_issues, _ = profile.validate(rows, ctx)
    codes = [i.code for i in file_issues]
    assert "EXAM_NOT_OPEN" in codes  # faculty can't import once entry closes
    assert "MISSING_STUDENTS" in codes  # A001 (same cohort, in scope) has no row
    ctx.allowed = None
    _results, file_issues, _ = profile.validate(rows, ctx)
    assert "EXAM_NOT_OPEN" not in [i.code for i in file_issues]  # administrators still can
