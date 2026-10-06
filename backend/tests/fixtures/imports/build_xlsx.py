"""Builds the XLSX members of the import golden corpus in memory (deterministic content, no binaries in git)."""

from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook


def _save(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def messy_students_xlsx() -> bytes:
    """Instructions sheet first, merged title, header on row 3, numbers stored as numbers, real date cells,
    an uncached formula, a formula-looking name, a hidden row and trailing spaces."""
    wb = Workbook()
    notes = wb.active
    assert notes is not None
    notes.title = "Instructions"
    notes["A1"] = "Fill in one student per row. Do not change the column names."
    notes["A2"] = "Questions? Ask the exam cell."

    ws = wb.create_sheet("Students")
    ws["A1"] = "Class list — 2025-26"
    ws.merge_cells("A1:F1")
    ws.append([])
    ws.append(["S.No", "Enrollment Number", "Name of Student", "Date of Birth", "Class", "Total"])
    ws.append([1, 102303401, "Arjun Nair", datetime(2005, 1, 9), "CSE-G1", "=1+1"])
    ws.append([2, 102303402.0, "Sara Khan  ", "09/01/2005", "CSE-G2", None])
    ws.append([3, "102303403", None, None, "CSE-G1", None])
    name = ws.cell(row=6, column=3, value='=HYPERLINK("http://evil.example","click")')
    name.data_type = "s"  # stored as text, the way a pasted value arrives
    ws.append([4, 102303404, "Hidden Row Student", datetime(2004, 12, 31), "cse-g2", None])
    ws.row_dimensions[7].hidden = True
    ws.append([5, 102303405, "Vikram  Rao", "2004-02-29", "CSE-G1", None])
    ws.append([6, 102303406, "Leap Day Typo", "2005-02-29", "CSE-G1", None])
    return _save(wb)


XLSX_FIXTURES = {"05_messy_workbook.xlsx": messy_students_xlsx}
