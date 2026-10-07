"""Import rule engine (docs/13 §3–4): header detection, column mapping, row/file issues, and the
``ImportProfile`` contract that every import kind (students now, marks in Phase 8) implements.

The analysis step is pure and deterministic: ``analyse(sheet, profile, ctx, mapping)`` gives the same
result for the same inputs, which is what the golden-file tests pin down. Database access happens only
in ``profile.load_context`` (once per run, set-based) and ``profile.commit``.
"""

from __future__ import annotations

import difflib
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Protocol

from app.core.db import UnitOfWork
from app.modules.audit.service import Actor
from app.modules.ingestion.parsers import Sheet, Workbook

Severity = Literal["error", "warning", "info"]
SEVERITY_RANK = {"error": 3, "warning": 2, "info": 1}
HEADER_SCAN_ROWS = 20


def norm_header(value: str) -> str:
    """``"Enrollment No."`` → ``"enrollmentno"``; ``"Father's / Guardian Name"`` → ``"fathersguardianname"``."""
    return re.sub(r"[^a-z0-9]", "", value.lower().replace("&", "and"))


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    required: bool = False
    aliases: tuple[str, ...] = ()
    help: str = ""
    example: str = ""

    def matches(self) -> set[str]:
        return {norm_header(a) for a in (self.key, self.label, *self.aliases)}


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    message: str
    field: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "msg": self.message, "field": self.field}


@dataclass
class RowInput:
    row_no: int  # 1-based spreadsheet row number
    cells: list[str]
    values: dict[str, str]  # field key → cell text ("" when blank or unmapped)


@dataclass
class RowResult:
    row_no: int
    cells: list[str]
    normalized: dict[str, Any]
    issues: list[Issue] = field(default_factory=list)

    @property
    def status(self) -> str:
        worst = max((SEVERITY_RANK[i.severity] for i in self.issues), default=0)
        return "error" if worst == 3 else "warning" if worst == 2 else "valid"


@dataclass
class Analysis:
    header_row: int | None  # 1-based; None when no header was found
    columns: list[str]
    mapping: dict[str, int]
    missing: list[str]  # required fields with no column
    rows: list[RowResult]
    file_issues: list[Issue]
    summary: dict[str, Any]
    blank_rows: int = 0

    @property
    def needs_mapping(self) -> bool:
        return bool(self.missing)

    def counts(self) -> dict[str, int]:
        out = {"valid": 0, "warning": 0, "error": 0}
        for r in self.rows:
            out[r.status] += 1
        return out


class ImportProfile(Protocol):
    kind: ClassVar[str]

    # Fixed per kind (students) or built per import (marks: the exam's papers and components).
    @property
    def fields(self) -> tuple[FieldSpec, ...]: ...

    def missing_fields(self, mapping: dict[str, int]) -> list[str]: ...

    def validate(
        self, rows: list[RowInput], ctx: Any
    ) -> tuple[list[RowResult], list[Issue], dict[str, Any]]: ...

    async def load_context(self, uow: UnitOfWork, params: dict[str, Any]) -> Any: ...

    async def commit(
        self,
        uow: UnitOfWork,
        actor: Actor,
        job_id: uuid.UUID,
        params: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


# ---- header & mapping ---------------------------------------------------------------------------


def _header_scores(rows: Sequence[Sequence[str]], fields: Sequence[FieldSpec]) -> list[int]:
    targets = set().union(*(f.matches() for f in fields))
    return [sum(1 for c in row if c and norm_header(c) in targets) for row in rows[:HEADER_SCAN_ROWS]]


def detect_header(rows: Sequence[Sequence[str]], fields: Sequence[FieldSpec]) -> int | None:
    """Index of the row that looks most like a header (most cells naming a known field)."""
    best, best_score = None, 0
    for i, score in enumerate(_header_scores(rows, fields)):
        if score > best_score:
            best, best_score = i, score
    return best


def pick_sheet(workbook: Workbook, fields: Sequence[FieldSpec], name: str | None) -> Sheet:
    """The chosen sheet, else the one whose header names the most known fields (so an instructions sheet
    in front of the data doesn't get imported), else the first sheet with content."""
    if name:
        return workbook.sheet(name)
    scored = [(max(_header_scores(s.rows, fields), default=0), -i, s) for i, s in enumerate(workbook.sheets)]
    best = max(scored, key=lambda t: (t[0], t[1]), default=None)
    if best is not None and best[0] > 0:
        return best[2]
    return workbook.sheet(None)


def auto_map(header: Sequence[str], fields: Sequence[FieldSpec]) -> dict[str, int]:
    """Exact alias matches first, then close fuzzy matches; each column maps to at most one field."""
    mapping: dict[str, int] = {}
    used: set[int] = set()
    normed = [norm_header(h) for h in header]
    for f in fields:
        names = f.matches()
        for i, h in enumerate(normed):
            if h and i not in used and h in names:
                mapping[f.key] = i
                used.add(i)
                break
    for f in fields:
        if f.key in mapping:
            continue
        candidates = sorted(f.matches())
        for i, h in enumerate(normed):
            if not h or i in used or len(h) < 4:
                continue
            if difflib.get_close_matches(h, candidates, n=1, cutoff=0.85):
                mapping[f.key] = i
                used.add(i)
                break
    return mapping


def clean_mapping(mapping: dict[str, Any], fields: Sequence[FieldSpec], n_columns: int) -> dict[str, int]:
    known = {f.key for f in fields}
    out: dict[str, int] = {}
    seen: set[int] = set()
    for key, col in mapping.items():
        if key not in known or col is None:
            continue
        idx = int(col)
        if not 0 <= idx < n_columns or idx in seen:
            continue
        out[key] = idx
        seen.add(idx)
    return out


def analyse(
    sheet: Sheet,
    profile: ImportProfile,
    ctx: Any,
    *,
    mapping: dict[str, Any] | None = None,
    header_row: int | None = None,
) -> Analysis:
    rows = sheet.rows
    header_idx = header_row - 1 if header_row else detect_header(rows, profile.fields)
    if header_idx is None or header_idx >= len(rows):
        header_idx = next((i for i, r in enumerate(rows) if any(r)), 0)
    header = rows[header_idx] if rows else []
    n_cols = max((len(r) for r in rows), default=0)
    columns = [header[i] if i < len(header) else "" for i in range(n_cols)]
    resolved = (
        clean_mapping(mapping, profile.fields, n_cols)
        if mapping is not None
        else auto_map(columns, profile.fields)
    )
    missing = profile.missing_fields(resolved)
    file_issues: list[Issue] = []
    if sheet.truncated_cells:
        file_issues.append(
            Issue(
                "CELL_TOO_LONG",
                "warning",
                f"{sheet.truncated_cells} cell(s) were longer than 1,000 characters and were cut short.",
            )
        )
    if missing:
        labels = {f.key: f.label for f in profile.fields}
        for key in missing:
            file_issues.append(
                Issue(
                    "MISSING_COLUMN", "error", f"No column for “{labels[key]}”. Map it or add a column.", key
                )
            )
        return Analysis(header_idx + 1, columns, resolved, missing, [], file_issues, {})

    inputs: list[RowInput] = []
    blank = 0
    for i in range(header_idx + 1, len(rows)):
        cells = rows[i]
        if not any(cells):
            blank += 1
            continue
        values = {k: (cells[c] if c < len(cells) else "") for k, c in resolved.items()}
        inputs.append(RowInput(i + 1, cells, values))
    if not inputs:
        file_issues.append(Issue("NO_DATA", "error", "There are no data rows below the header row."))
    results, extra_issues, summary = profile.validate(inputs, ctx)
    summary = {**summary, "blank_rows": blank}
    return Analysis(
        header_idx + 1, columns, resolved, [], results, file_issues + extra_issues, summary, blank
    )


def suggest(value: str, candidates: Sequence[str]) -> str | None:
    """Closest candidate, catching the classic O/0 and I/1 swaps first (docs/13 §4 UNKNOWN_STUDENT)."""
    swapped = value.replace("O", "0").replace("I", "1").replace("L", "1")
    for c in candidates:
        if c.replace("O", "0").replace("I", "1").replace("L", "1") == swapped:
            return c
    close = difflib.get_close_matches(value, list(candidates), n=1, cutoff=0.8)
    return close[0] if close else None
