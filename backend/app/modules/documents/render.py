"""Marksheet PDFs (docs/10 §10, P11.1).

* **Template:** HTML and CSS rendered by Jinja's ``SandboxedEnvironment`` (no attribute access to Python
  internals, so a template can't reach the interpreter), with autoescaping. Every string comes from the
  published snapshot, so a student named ``<img src=…>`` is printed, never interpreted.
* **No external fetches:** WeasyPrint gets a fetcher that serves only the ``data:`` URIs we embed (the
  logo and the QR code). ``http``, ``https``, ``file`` and every other URL are refused, so neither a template
  nor data inside it can make the renderer reach the network or the disk (SSRF, local file reads).
* **Content:** only the snapshot payload (exactly what the student sees) plus the institution's branding.

WeasyPrint needs system libraries (Pango), which the Docker image has. It's imported lazily so the rest of
the app, and the unit tests, run without them.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import segno
from jinja2 import PackageLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from app.modules.files.service import IMAGE_TYPES, sniff

TEMPLATE_CODE = "standard"
TEMPLATE_VERSION = 1

OUTCOME = {
    "pass": ("Passed", "pass"),
    "fail": ("Not passed", "fail"),
    "absent": ("Absent", "neutral"),
    "withheld": ("Result withheld", "warn"),
    "incomplete": ("Incomplete", "warn"),
}
PAPER_OUTCOME = {
    "pass": "Pass",
    "fail": "Fail",
    "absent": "Absent",
    "exempt": "Exempt",
    "withheld": "Withheld",
    "incomplete": "Incomplete",
}

_env = SandboxedEnvironment(
    loader=PackageLoader("app.modules.documents", "templates"),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


class ExternalResourceRefused(ValueError):
    pass


def _fetcher_class() -> type:
    from weasyprint.urls import URLFetcher

    class DataOnlyFetcher(URLFetcher):  # type: ignore[misc]
        """Serves ``data:`` URIs only; records and refuses everything else."""

        def __init__(self) -> None:
            super().__init__(timeout=1, allowed_protocols={"data"}, allow_redirects=False)
            self.refused: list[str] = []

        def fetch(self, url: str, headers: dict[str, str] | None = None) -> Any:
            if not url.startswith("data:"):
                self.refused.append(url[:200])
                raise ExternalResourceRefused("marksheets may not load external resources")
            return super().fetch(url, headers)

    return DataOnlyFetcher


@dataclass(frozen=True)
class Branding:
    """Look of the marksheet. The names printed come from the snapshot, like everything else."""

    address: str | None = None
    affiliation: str | None = None
    color: str = "#2952cc"  # validated hex (database check constraint)
    logo: bytes | None = None
    footer_text: str | None = None
    show_powered_by: bool = True


@dataclass
class RenderResult:
    pdf: bytes
    refused: list[str] = field(default_factory=list)


def data_uri(data: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{base64.b64encode(data).decode()}"


def logo_uri(data: bytes | None) -> str | None:
    """Only bytes that really are PNG, JPEG or WebP become an image (never SVG, which can carry links)."""
    if not data:
        return None
    kind = sniff(data)
    return data_uri(data, kind.content_type) if kind in IMAGE_TYPES else None


def qr_uri(url: str) -> str:
    return str(segno.make_qr(url, error="m").svg_data_uri(scale=4, border=0, dark="#111111"))


def _num(value: Any) -> str:
    return "—" if value in (None, "") else str(value)


def view_model(
    payload: dict[str, Any],
    *,
    branding: Branding,
    verify_url: str,
    code_display: str,
    version: int,
    issued_at: datetime,
    timezone: str,
) -> dict[str, Any]:
    """Everything the template prints, from the snapshot alone (schema 1)."""
    result = payload["result"]
    student = payload["student"]
    names = payload["institution"]
    outcome_label, tone = OUTCOME.get(result["outcome"], (str(result["outcome"]).title(), "neutral"))
    papers = []
    for p in payload["papers"]:
        parts = [f"{c['label']} {_num(c['marks'])}/{_num(c['max'])}" for c in p.get("components", [])]
        papers.append(
            {
                "code": p["course_code"],
                "name": p["course_name"],
                "credits": p.get("credits"),
                "components": " · ".join(parts),
                "total": _num(p["total"]),
                "max": _num(p["max_total"]),
                "grade": _num(p["grade"]),
                "outcome": PAPER_OUTCOME.get(p["outcome"], str(p["outcome"]).title()),
                "failed": p["outcome"] == "fail",
            }
        )
    local = issued_at.astimezone(ZoneInfo(timezone))
    return {
        "institution": {
            "display_name": names["display_name"],
            "official_name": names["name"] if names["name"] != names["display_name"] else None,
            "address": branding.address,
            "affiliation": branding.affiliation,
            "logo": logo_uri(branding.logo),
            "color": branding.color,
        },
        "exam": payload["exam"],
        "student": {
            "name": student["full_name"],
            "enrollment_no": student["enrollment_no"],
            "cohort": student["cohort"]["name"] if student.get("cohort") else None,
            "program": student.get("program"),
        },
        "papers": papers,
        "has_credits": any(p["credits"] is not None for p in papers),
        "result": {
            "outcome": outcome_label,
            "tone": tone,
            "total": _num(result["total"]),
            "max": _num(result["max_total"]),
            "percentage": None if result["percentage"] is None else f"{result['percentage']}%",
            "grade": result["grade"],
            "grade_point": result["grade_point"],
            "sgpa": result["sgpa"],
            "credits": (
                f"{_num(result['credits_earned'])} of {_num(result['credits_attempted'])}"
                if result.get("credits_attempted") is not None
                else None
            ),
            "rank": result.get("rank"),
            "notes": list(result.get("notes") or []),
        },
        "scheme": payload["scheme"]["name"],
        "issued_on": f"{local.day} {local:%B %Y}",
        "version": version,
        "revised": version > 1,
        "verify": {
            "url": verify_url,
            "display": verify_url.split("://", 1)[-1],
            "code": code_display,
            "qr": qr_uri(verify_url),
        },
        "footer_text": branding.footer_text,
        "powered_by": branding.show_powered_by,
    }


def render_html(context: dict[str, Any], template: str = TEMPLATE_CODE) -> str:
    return _env.get_template(f"{template}.html.j2").render(**context)


def html_to_pdf(html: str) -> RenderResult:
    """Lay out ``html`` as a PDF with every external fetch refused. CPU-bound: call it in a thread."""
    from weasyprint import HTML

    fetcher = _fetcher_class()()
    pdf = HTML(string=html, base_url=None, url_fetcher=fetcher).write_pdf()
    return RenderResult(pdf=bytes(pdf or b""), refused=list(fetcher.refused))


def render_marksheet(payload: dict[str, Any], **context: Any) -> RenderResult:
    return html_to_pdf(render_html(view_model(payload, **context)))
