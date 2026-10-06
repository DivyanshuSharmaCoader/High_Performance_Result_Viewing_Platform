"""Golden-file tests for the import pipeline (P6.5, docs/13 §7).

Each file in ``tests/fixtures/imports/students`` (plus generated workbooks) is parsed and analysed against
a fixed context; the outcome — header row, mapping, file issues, and per-row status, issue codes and
normalised values — must equal the committed ``<name>.expected.json``.

Regenerate after a deliberate change with ``UPDATE_GOLDEN=1 uv run pytest tests/unit/test_import_golden.py``
and review the diff like code.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.modules.ingestion.engine import analyse, pick_sheet
from app.modules.ingestion.parsers import Limits, parse_workbook
from app.modules.ingestion.students import CohortRef, Existing, StudentsContext, StudentsProfile
from tests.fixtures.imports.build_xlsx import XLSX_FIXTURES

CORPUS = Path(__file__).resolve().parent.parent / "fixtures" / "imports" / "students"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def _ctx() -> StudentsContext:
    def ref(code: str, archived: bool = False) -> CohortRef:
        return CohortRef(uuid.uuid5(uuid.NAMESPACE_URL, code), code, archived)

    cohorts = {c.code: c for c in (ref("CSE-G1"), ref("CSE-G2"), ref("ECE-A"), ref("OLD-X", archived=True))}
    existing = {
        "102303050": Existing(
            uuid.uuid5(uuid.NAMESPACE_URL, "102303050"),
            "active",
            {
                "full_name": "Existing Student",
                "email": "existing@example.com",
                "phone": None,
                "date_of_birth": None,
                "guardian_name": None,
                "admission_year": 2022,
            },
        )
    }
    return StudentsContext(existing=existing, cohorts=cohorts, session_code="2025-26", remaining=100)


def _cases() -> list[tuple[str, bytes, str]]:
    cases = [(p.name, p.read_bytes(), "csv") for p in sorted(CORPUS.glob("*.csv"))]
    cases += [(name, build(), "xlsx") for name, build in XLSX_FIXTURES.items()]
    return sorted(cases)


def _outcome(data: bytes, fmt: str) -> dict[str, Any]:
    profile = StudentsProfile()
    workbook = parse_workbook(data, fmt, Limits())
    sheet = pick_sheet(workbook, profile.fields, None)
    result = analyse(sheet, profile, _ctx())
    keep = (
        "enrollment_no",
        "full_name",
        "email",
        "phone",
        "date_of_birth",
        "guardian_name",
        "admission_year",
    )
    return {
        "encoding": workbook.encoding,
        "delimiter": workbook.delimiter,
        "sheet": sheet.name,
        "header_row": result.header_row,
        "mapping": {k: result.columns[v] for k, v in sorted(result.mapping.items())},
        "missing": result.missing,
        "file_issues": [i.code for i in result.file_issues],
        "summary": result.summary,
        "rows": [
            {
                "row": r.row_no,
                "status": r.status,
                "issues": [i.code for i in r.issues],
                "values": {k: r.normalized.get(k) for k in keep if r.normalized.get(k) is not None},
                "cohort": r.normalized.get("cohort_code"),
                "action": r.normalized.get("action"),
            }
            for r in result.rows
        ],
    }


@pytest.mark.parametrize(("name", "data", "fmt"), _cases(), ids=lambda v: v if isinstance(v, str) else "")
def test_golden(name: str, data: bytes, fmt: str) -> None:
    outcome = _outcome(data, fmt)
    expected_path = CORPUS / f"{name}.expected.json"
    rendered = json.dumps(outcome, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if UPDATE or not expected_path.exists():
        expected_path.write_text(rendered, encoding="utf-8")
        if not UPDATE:
            pytest.fail(f"wrote new golden file {expected_path.name}; review it and re-run")
    assert rendered == expected_path.read_text(encoding="utf-8")


def test_analysis_is_deterministic() -> None:
    for _name, data, fmt in _cases():
        assert _outcome(data, fmt) == _outcome(data, fmt)
