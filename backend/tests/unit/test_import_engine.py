"""Import engine units (P6.4/P6.5): hostile files, value parsing, mapping, and generated-report safety."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date

import pytest
from openpyxl import Workbook, load_workbook

from app.core.errors import PayloadTooLarge, UnsupportedMedia
from app.modules.files.service import CSV, IMAGE_TYPES, PNG, SPREADSHEET_TYPES, XLSX, sniff, validate_upload
from app.modules.ingestion.engine import analyse, auto_map, norm_header, suggest
from app.modules.ingestion.parsers import FileUnreadable, Limits, parse_workbook
from app.modules.ingestion.report import error_report, template
from app.modules.ingestion.students import StudentsContext, StudentsProfile
from app.modules.ingestion.values import (
    is_mangled_number,
    looks_like_formula,
    parse_date,
    parse_phone,
    parse_year,
)


def _xlsx(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _zip(members: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ---- upload checks (P6.4) -------------------------------------------------------------------------


def test_sniffing_trusts_content_not_names() -> None:
    assert sniff(b"\x89PNG\r\n\x1a\n" + b"0" * 20) == PNG
    assert sniff(_xlsx([["a"]])) == XLSX
    assert sniff("Roll No,Name\n1,Zoë\n".encode()) == CSV
    assert sniff(b"<svg onload=alert(1)>") is None  # markup is never accepted
    assert sniff(b"<!DOCTYPE html><script>") is None
    assert sniff(b"MZ\x90\x00\x03\x00\x00\x00") is None  # Windows executable (NUL bytes)


def test_upload_validation_rejects_wrong_type_empty_and_oversize() -> None:
    with pytest.raises(UnsupportedMedia):
        validate_upload(b"", SPREADSHEET_TYPES, 1000)
    with pytest.raises(UnsupportedMedia):
        validate_upload(b"\x89PNG\r\n\x1a\n" + b"0" * 20, SPREADSHEET_TYPES, 1000)  # an image renamed .csv
    with pytest.raises(UnsupportedMedia):
        validate_upload(b"a,b\n1,2\n", IMAGE_TYPES, 1000)
    with pytest.raises(PayloadTooLarge):
        validate_upload(b"a" * 1001, SPREADSHEET_TYPES, 1000)
    assert validate_upload(b"a,b\n1,2\n", SPREADSHEET_TYPES, 1000) == CSV


# ---- hostile workbooks (docs/13 §7 security tests) ------------------------------------------------


def test_zip_bomb_is_rejected_before_parsing() -> None:
    bomb = _zip(
        {
            "[Content_Types].xml": b"<Types/>",
            "xl/workbook.xml": b"<workbook/>",
            "xl/worksheets/sheet1.xml": b"\x00" * 50_000_000,  # 50 MB of zeros compresses ~1000:1
        }
    )
    assert len(bomb) < 200_000
    with pytest.raises(FileUnreadable) as exc:
        parse_workbook(bomb, "xlsx", Limits())
    assert exc.value.reason == "too-large"


def test_total_uncompressed_size_is_capped() -> None:
    data = _xlsx([["Enrollment", "Name"], ["1", "A"]])
    with pytest.raises(FileUnreadable) as exc:
        parse_workbook(data, "xlsx", Limits(max_uncompressed_bytes=1_000))
    assert exc.value.reason == "too-large"


def test_macro_workbooks_and_non_workbook_zips_are_rejected() -> None:
    real = zipfile.ZipFile(io.BytesIO(_xlsx([["a"]])))
    members = {n: real.read(n) for n in real.namelist()}
    with pytest.raises(FileUnreadable) as exc:
        parse_workbook(_zip({**members, "xl/vbaProject.bin": b"macro"}), "xlsx", Limits())
    assert exc.value.reason == "macros"
    with pytest.raises(FileUnreadable) as exc:
        parse_workbook(
            _zip({"word/document.xml": b"<doc/>", "[Content_Types].xml": b"<Types/>"}), "xlsx", Limits()
        )
    assert exc.value.reason == "not-xlsx"
    with pytest.raises(FileUnreadable) as exc:
        parse_workbook(b"PK\x03\x04garbage", "xlsx", Limits())
    assert exc.value.reason == "not-xlsx"


def test_row_and_cell_limits() -> None:
    many = ("Enrollment,Name\n" + "".join(f"{i},N{i}\n" for i in range(200))).encode()
    with pytest.raises(FileUnreadable) as exc:
        parse_workbook(many, "csv", Limits(max_rows=100))
    assert exc.value.reason == "too-many-rows"
    long_cell = ("Enrollment,Name\n1," + "x" * 5000 + "\n").encode()
    sheet = parse_workbook(long_cell, "csv", Limits()).sheets[0]
    assert len(sheet.rows[1][1]) == 1000 and sheet.truncated_cells == 1


def test_formulas_are_never_evaluated_only_cached_values_read() -> None:
    data = _xlsx([["Enrollment", "Name", "Total"], ["1", "A", "=1+1"]])
    rows = parse_workbook(data, "xlsx", Limits()).sheets[0].rows
    assert rows[1] == ["1", "A"]  # no cached value → blank, and never "2"


# ---- values ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2005-03-14", date(2005, 3, 14)),
        ("2005-03-14 00:00:00", date(2005, 3, 14)),
        ("14/03/2005", date(2005, 3, 14)),
        ("14-03-2005", date(2005, 3, 14)),
        ("14.3.2005", date(2005, 3, 14)),
        ("03/14/2005", date(2005, 3, 14)),  # month > 12 in the day slot → unambiguous
        ("14 Mar 2005", date(2005, 3, 14)),
        ("14-March-2005", date(2005, 3, 14)),
        ("March 14, 2005", date(2005, 3, 14)),
        ("38425", date(2005, 3, 14)),  # Excel serial
    ],
)
def test_parse_date_accepts_common_forms(text: str, expected: date) -> None:
    assert parse_date(text) == (expected, None)


@pytest.mark.parametrize("text", ["31/02/2005", "2005-13-01", "yesterday", "14/14/2005", "1/2"])
def test_parse_date_rejects_impossible_or_unknown(text: str) -> None:
    value, problem = parse_date(text)
    assert value is None and problem


def test_other_value_parsers() -> None:
    assert parse_year("2021-22") == (2021, None)
    assert parse_year("21")[0] is None
    assert parse_phone("+91 98100 12345") == ("+91 98100 12345", None)
    assert parse_phone("12")[1]
    assert (
        is_mangled_number("1.02303E+11") and is_mangled_number("1E+11") and not is_mangled_number("102303001")
    )
    assert looks_like_formula("=SUM(A1)") and looks_like_formula("@cmd") and looks_like_formula("-x")
    assert not looks_like_formula("-5") and not looks_like_formula("Asha")


def test_header_matching_and_suggestions() -> None:
    assert norm_header("Father's / Guardian Name") == "fathersguardianname"
    mapping = auto_map(
        ["S.No", "Enrolment No.", "Name of Student", "E-mail", "Sectoin"], StudentsProfile.fields
    )
    assert mapping == {
        "enrollment_no": 1,
        "full_name": 2,
        "email": 3,
        "cohort": 4,
    }  # "Sectoin" fuzzy → section
    assert suggest("1023O3001", ["102303001", "102303002"]) == "102303001"
    assert suggest("CSE-G9", ["CSE-G1", "ECE-A"]) == "CSE-G1"


def test_create_only_mode_skips_existing_and_limit_is_a_file_error() -> None:
    from app.modules.ingestion.parsers import Sheet
    from app.modules.ingestion.students import Existing

    sheet = Sheet("CSV", [["Enrollment", "Name"], ["A1", "Existing"], ["A2", "New"], ["A3", "New 2"]])
    ctx = StudentsContext(
        existing={"A1": Existing(uuid.uuid4(), "active", {"full_name": "Existing"})},
        cohorts={},
        session_code=None,
        remaining=1,
        mode="create_only",
    )
    result = analyse(sheet, StudentsProfile(), ctx)
    assert [r.normalized["action"] for r in result.rows] == ["skip", "create", "create"]
    assert [i.code for i in result.file_issues] == ["LIMIT_EXCEEDED"]


# ---- generated spreadsheets -----------------------------------------------------------------------


def test_error_report_never_contains_live_formulas_and_highlights_cells() -> None:
    evil = ['=HYPERLINK("http://evil.example","x")', "+cmd|' /C calc'!A0", "@SUM(1)", "-2+3", "\t=1"]
    data = error_report(
        columns=["Enrollment", "Name"],
        mapping={"enrollment_no": 0, "full_name": 1},
        rows=[
            {
                "row_no": i + 2,
                "raw": ["E1", v],
                "issues": [{"severity": "error", "msg": v, "field": "full_name"}],
                "status": "error",
            }
            for i, v in enumerate(evil)
        ],
        file_issues=[{"msg": "=1+1", "severity": "error"}],
        title="=cmd",
    )
    wb = load_workbook(io.BytesIO(data))  # formulas would load as data_type "f"
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                assert cell.data_type != "f", f"{ws.title}!{cell.coordinate} is a formula"
    ws = wb["Checked rows"]
    assert ws["B2"].value == evil[0] and ws["B2"].fill.fgColor.rgb.endswith("FFC7CE")
    assert ws["D2"].value.startswith("Error: ")


def test_template_formats_identifier_columns_as_text_and_offers_cohort_choices() -> None:
    data = template(StudentsProfile.fields, title="Students", choices={"cohort": ["CSE-G1", "CSE-G2"]})
    wb = load_workbook(io.BytesIO(data))
    ws = wb["Data"]
    headers = [c.value for c in ws[1]]
    assert headers[:2] == ["Enrollment no.", "Full name"] and "First name" not in headers
    assert ws["A2"].number_format == "@"
    assert any('"CSE-G1,CSE-G2"' in (dv.formula1 or "") for dv in ws.data_validations.dataValidation)
    assert "How to fill" in wb.sheetnames


def test_spreadsheets_are_parsed_with_defused_xml() -> None:
    """XXE and entity-expansion protection (ASVS 5.5.2): openpyxl uses defusedxml when it's installed,
    so it must be a runtime dependency (it used to arrive only through a dev tool)."""
    import openpyxl.xml

    assert openpyxl.xml.DEFUSEDXML is True
