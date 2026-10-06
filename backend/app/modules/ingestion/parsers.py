"""Spreadsheet parsing (docs/13 §3 ③). Pure functions: bytes in, a grid of strings out.

Everything that varies between real-world files is normalised here so the rule engine sees one shape:

* CSV: UTF-8 (with or without BOM), UTF-16 with BOM, or Windows-1252; ``,`` ``;`` tab or ``|`` delimiters.
* XLSX: checked as a ZIP *before* openpyxl sees it (no macros, bounded uncompressed size and ratio, so a
  zip bomb is rejected cheaply), then read with ``read_only=True, data_only=True`` (cached values only —
  formulas are never evaluated).
* Cells become NFC-normalised strings with invisible characters removed; integral floats lose their
  ``.0`` (``102303001.0`` → ``"102303001"``); dates become ISO ``YYYY-MM-DD``.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from app.core.errors import DomainError

INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
SPACES = re.compile(r"[   \t\r\n]+")


class FileUnreadable(DomainError):
    """The file can't be turned into rows. ``code`` is shown to the user next to a plain explanation."""

    status = 422
    code = "import-file-unreadable"
    title = "We couldn't read this file"

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail, reason=reason)
        self.reason = reason


@dataclass(frozen=True)
class Limits:
    max_rows: int = 50_000
    max_columns: int = 200
    max_cell_chars: int = 1_000
    max_uncompressed_bytes: int = 100 * 1024 * 1024
    max_compression_ratio: int = 200


@dataclass
class Sheet:
    """A rectangular-ish grid. ``rows[i]`` is spreadsheet row ``i + 1``; trailing empty cells trimmed."""

    name: str
    rows: list[list[str]]
    truncated_cells: int = 0


@dataclass
class Workbook:
    format: str  # csv | xlsx
    sheets: list[Sheet]
    encoding: str | None = None
    delimiter: str | None = None
    notes: list[str] = field(default_factory=list)

    def sheet(self, name: str | None) -> Sheet:
        if name:
            for s in self.sheets:
                if s.name == name:
                    return s
            raise FileUnreadable("sheet-not-found", f"The workbook has no sheet called “{name}”.")
        for s in self.sheets:  # first sheet that has any content
            if any(any(c for c in row) for row in s.rows):
                return s
        raise FileUnreadable("empty", "The file has no data in it.")


def clean_text(value: str, max_chars: int | None = None) -> tuple[str, bool]:
    text = unicodedata.normalize("NFC", value).translate(INVISIBLE)
    text = SPACES.sub(" ", text).strip()
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars], True
    return text, False


def cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0) else value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return format(Decimal(repr(value)).normalize(), "f")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def _finish(raw_rows: list[list[Any]], name: str, limits: Limits) -> Sheet:
    rows: list[list[str]] = []
    truncated = 0
    for raw in raw_rows:
        cells = []
        for v in raw[: limits.max_columns]:
            text, cut = clean_text(cell_to_text(v), limits.max_cell_chars)
            truncated += cut
            cells.append(text)
        while cells and cells[-1] == "":
            cells.pop()
        rows.append(cells)
    while rows and not rows[-1]:
        rows.pop()
    return Sheet(name=name, rows=rows, truncated_cells=truncated)


def _too_many_rows(limits: Limits) -> FileUnreadable:
    return FileUnreadable(
        "too-many-rows", f"The file has more than {limits.max_rows:,} rows. Split it into smaller files."
    )


# ---- CSV ----------------------------------------------------------------------------------------


def decode_text(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    # Excel on Windows saves "CSV" as Windows-1252; it decodes every byte except 5 unused ones.
    try:
        return data.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def sniff_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:50])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in ",;\t|"}
        best = max(counts, key=lambda d: counts[d])
        return best if counts[best] else ","


def parse_csv(data: bytes, limits: Limits) -> Workbook:
    text, encoding = decode_text(data)
    if "\x00" in text:
        raise FileUnreadable("binary", "This doesn't look like a text CSV file.")
    delimiter = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    raw: list[list[Any]] = []
    try:
        for row in reader:
            if len(raw) >= limits.max_rows + 50:  # allow a few title/header rows above the data
                raise _too_many_rows(limits)
            raw.append(row)
    except csv.Error as exc:
        raise FileUnreadable(
            "malformed-csv", f"The CSV file is malformed near line {reader.line_num}."
        ) from exc
    return Workbook("csv", [_finish(raw, "CSV", limits)], encoding=encoding, delimiter=delimiter)


# ---- XLSX ---------------------------------------------------------------------------------------


def check_xlsx_container(data: bytes, limits: Limits) -> None:
    """Reject non-workbooks, macro-enabled files and zip bombs before any XML is parsed."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise FileUnreadable("not-xlsx", "This file isn't a valid .xlsx workbook.") from exc
    with zf:
        names = set(zf.namelist())
        if "[Content_Types].xml" not in names or not any(n.startswith("xl/workbook") for n in names):
            raise FileUnreadable(
                "not-xlsx", "This file isn't an Excel workbook. Save it as .xlsx or .csv and upload again."
            )
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            raise FileUnreadable(
                "macros", "Workbooks with macros aren't accepted. Save it as a plain .xlsx and upload again."
            )
        total = 0
        for info in zf.infolist():
            total += info.file_size
            ratio = info.file_size / max(info.compress_size, 1)
            if info.file_size > 1_000_000 and ratio > limits.max_compression_ratio:
                raise FileUnreadable("too-large", "This workbook expands to an unusually large size.")
        if total > limits.max_uncompressed_bytes:
            raise FileUnreadable("too-large", "This workbook is too large once uncompressed. Split it up.")


def parse_xlsx(data: bytes, limits: Limits) -> Workbook:
    check_xlsx_container(data, limits)
    import openpyxl  # imported lazily: only the worker parses spreadsheets

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for corrupt parts
        raise FileUnreadable("corrupt", "This workbook is damaged or uses an unsupported format.") from exc
    sheets: list[Sheet] = []
    try:
        for ws in wb.worksheets:
            raw: list[list[Any]] = []
            for row in ws.iter_rows(values_only=True):
                if len(raw) >= limits.max_rows + 50:
                    raise _too_many_rows(limits)
                raw.append(list(row))
            sheets.append(_finish(raw, ws.title, limits))
    finally:
        wb.close()
    return Workbook("xlsx", sheets)


def parse_workbook(data: bytes, file_format: str, limits: Limits) -> Workbook:
    if file_format == "xlsx":
        return parse_xlsx(data, limits)
    if file_format == "csv":
        return parse_csv(data, limits)
    raise FileUnreadable("unsupported", "Upload an .xlsx or .csv file.")
