"""Value parsers shared by import profiles. Each returns ``(value, problem)``; ``problem`` is a short
human sentence or ``None``. Day-first dates by default (the convention in India, the UK and most of the
world); ISO dates are always accepted."""

from __future__ import annotations

import re
from datetime import date, timedelta

MANGLED_NUMBER = re.compile(r"^\d+(?:\.\d+)?[eE][+]?\d+$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]{2,}$")
EXCEL_EPOCH = date(1899, 12, 30)
MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}


def is_mangled_number(text: str) -> bool:
    """``1.02303E+11``: Excel displayed a long number in scientific notation and the CSV kept only that."""
    return bool(MANGLED_NUMBER.match(text.strip()))


def looks_like_formula(text: str) -> bool:
    """Text a spreadsheet would execute (``=``, ``+``, ``@``, or ``-`` followed by a non-digit)."""
    t = text.strip()
    return bool(t) and (t[0] in "=+@" or (t[0] == "-" and len(t) > 1 and not t[1].isdigit()))


def _year(y: int) -> int:
    if y >= 100:
        return y
    pivot = (date.today().year % 100) + 1
    return 2000 + y if y < pivot else 1900 + y


def _make(y: int, m: int, d: int) -> date | None:
    try:
        return date(_year(y), m, d)
    except ValueError:
        return None


def parse_date(text: str, *, day_first: bool = True) -> tuple[date | None, str | None]:
    raw = text.strip()
    if not raw:
        return None, None
    bad = f"“{raw}” isn't a date we recognise. Use DD/MM/YYYY or YYYY-MM-DD."
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?", raw):
        d = _make(int(m[1]), int(m[2]), int(m[3]))
        return (d, None) if d else (None, bad)
    if m := re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})", raw):
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        day, month = (a, b) if day_first else (b, a)
        if month > 12 and day <= 12:  # obviously the other order
            day, month = month, day
        d = _make(y, month, day)
        return (d, None) if d else (None, bad)
    if m := re.fullmatch(r"(\d{1,2})[\s\-/]+([A-Za-z]{3,9})[\s\-/,]+(\d{2}|\d{4})", raw):
        named = MONTHS.get(m[2].lower())
        d = _make(int(m[3]), named, int(m[1])) if named else None
        return (d, None) if d else (None, bad)
    if m := re.fullmatch(r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})", raw):
        named = MONTHS.get(m[1].lower())
        d = _make(int(m[3]), named, int(m[2])) if named else None
        return (d, None) if d else (None, bad)
    if re.fullmatch(r"\d{4,5}", raw):  # an Excel serial date that lost its formatting
        serial = int(raw)
        if 1 <= serial <= 80_000:
            return EXCEL_EPOCH + timedelta(days=serial), None
    return None, bad


def parse_int(text: str) -> int | None:
    raw = text.strip().replace(",", "")
    if re.fullmatch(r"[+-]?\d+(?:\.0+)?", raw):
        return int(float(raw))
    return None


def parse_year(text: str) -> tuple[int | None, str | None]:
    raw = text.strip()
    if not raw:
        return None, None
    m = re.match(r"^(\d{4})(?:\s*[-/–]\s*\d{2,4})?$", raw)  # "2021" or "2021-22"
    if not m:
        return None, f"“{raw}” isn't a year. Use four digits, e.g. 2024."
    year = int(m[1])
    if not 1950 <= year <= 2100:
        return None, f"{year} is outside the accepted range (1950–2100)."
    return year, None


def parse_email(text: str) -> tuple[str | None, str | None]:
    raw = text.strip().lower()
    if not raw:
        return None, None
    if not EMAIL.match(raw) or len(raw) > 254:
        return None, f"“{text.strip()}” isn't a valid email address."
    return raw, None


def parse_phone(text: str) -> tuple[str | None, str | None]:
    raw = " ".join(text.split())
    if not raw:
        return None, None
    digits = re.sub(r"\D", "", raw)
    if not re.fullmatch(r"[+\d][\d\s\-().]*", raw) or not 7 <= len(digits) <= 15:
        return raw[:32], f"“{raw}” doesn't look like a phone number."
    return raw[:32], None
