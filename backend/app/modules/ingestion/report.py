"""Spreadsheets we *generate*: the annotated error report and blank templates (docs/13 §3 ⑥).

Every value is written as a plain string with Excel's quote prefix where it could be read as a formula
(``= + - @``, tab, CR), so a malicious cell from an uploaded file can never become a live formula in the
report (CSV/formula injection, docs/10 §6).
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Sequence
from typing import Any

from openpyxl import Workbook
from openpyxl.cell import Cell, WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from app.modules.ingestion.engine import FieldSpec

FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
ERROR_FILL = PatternFill("solid", fgColor="FFC7CE")
WARNING_FILL = PatternFill("solid", fgColor="FFEB9C")
HEADER_FILL = PatternFill("solid", fgColor="E8EAED")
BOLD = Font(bold=True)


def safe_cell(ws: Worksheet, value: Any, *, fill: PatternFill | None = None, bold: bool = False) -> Cell:
    text = "" if value is None else str(value)
    cell: Cell = WriteOnlyCell(ws, value=text)
    cell.data_type = "s"  # never "f", whatever the text starts with
    if text.startswith(FORMULA_TRIGGERS):
        cell.quotePrefix = True
    if fill is not None:
        cell.fill = fill
    if bold:
        cell.font = BOLD
    return cell


def _bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def error_report(
    *,
    columns: Sequence[str],
    mapping: dict[str, int],
    rows: Iterable[dict[str, Any]],
    file_issues: Sequence[dict[str, Any]],
    title: str,
) -> bytes:
    """All staged rows with a *Problems* column and highlighted cells. The data sheet keeps the original
    columns, so the corrected report itself can be uploaded again."""
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Checked rows")
    ws.freeze_panes = "A2"
    col_of_field = dict(mapping)
    n = len(columns)
    ws.append(
        [
            *(safe_cell(ws, c, fill=HEADER_FILL, bold=True) for c in columns),
            safe_cell(ws, "Row", fill=HEADER_FILL, bold=True),
            safe_cell(ws, "Problems", fill=HEADER_FILL, bold=True),
        ]
    )
    for row in rows:
        cells = list(row["raw"]) + [""] * max(0, n - len(row["raw"]))
        fills: dict[int, PatternFill] = {}
        notes = []
        for issue in row.get("issues") or []:
            sev = issue.get("severity")
            if sev == "info":
                continue
            notes.append(("Error: " if sev == "error" else "Check: ") + issue.get("msg", ""))
            col = col_of_field.get(issue.get("field") or "")
            if col is not None and (sev == "error" or col not in fills):
                fills[col] = ERROR_FILL if sev == "error" else WARNING_FILL
        out = [safe_cell(ws, v, fill=fills.get(i)) for i, v in enumerate(cells[: max(n, len(cells))])]
        status_fill = (
            ERROR_FILL if row["status"] == "error" else WARNING_FILL if row["status"] == "warning" else None
        )
        out.append(safe_cell(ws, row["row_no"]))
        out.append(safe_cell(ws, " · ".join(notes), fill=status_fill))
        ws.append(out)

    summary = wb.create_sheet("Summary")
    summary.append([safe_cell(summary, title, bold=True)])
    summary.append([])
    if file_issues:
        summary.append([safe_cell(summary, "Problems with the whole file", bold=True)])
        for issue in file_issues:
            summary.append([safe_cell(summary, issue.get("msg", ""))])
    summary.append([])
    summary.append([safe_cell(summary, "Red cells must be fixed; yellow cells are worth checking.")])
    summary.append(
        [safe_cell(summary, "Fix the rows in this sheet (or your original file) and upload it again.")]
    )
    return _bytes(wb)


def template(
    fields: Sequence[FieldSpec], *, title: str, choices: dict[str, list[str]] | None = None
) -> bytes:
    """A blank import template: one header row, text-formatted identifier columns (so Excel can't turn
    long numbers into 1.0E+11), dropdowns where the valid values are known, and an instructions sheet."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Data"
    visible = [f for f in fields if f.key not in ("first_name", "last_name")]
    for i, f in enumerate(visible, start=1):
        cell = ws.cell(row=1, column=i, value=f.label)
        cell.font = BOLD
        cell.fill = HEADER_FILL
        letter = cell.column_letter
        ws.column_dimensions[letter].width = max(14, len(f.label) + 4)
        if f.key in ("enrollment_no", "phone"):
            for r in range(2, 2002):
                ws.cell(row=r, column=i).number_format = "@"
        values = (choices or {}).get(f.key)
        if values:
            joined = ",".join(values)
            if len(joined) <= 250:  # Excel's limit for inline list validations
                dv = DataValidation(type="list", formula1=f'"{joined}"', allow_blank=True)
                dv.error = f"Choose one of the existing {f.label.lower()} codes."
                ws.add_data_validation(dv)
                dv.add(f"{letter}2:{letter}2001")
    ws.freeze_panes = "A2"

    info = wb.create_sheet("How to fill")
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 70
    info.append([title])
    info["A1"].font = Font(bold=True, size=13)
    info.append([])
    info.append(["Column", "What to enter"])
    for c in info[3]:
        c.font = BOLD
    for f in visible:
        need = "Required. " if f.required else "Optional. "
        example = f" Example: {f.example}" if f.example else ""
        info.append([f.label, f"{need}{f.help}{example}".strip()])
    info.append([])
    info.append(["", "Column names don't have to match exactly — you can map columns after uploading."])
    for row in info.iter_rows(min_row=4):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    return _bytes(wb)
