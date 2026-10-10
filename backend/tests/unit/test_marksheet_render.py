"""Marksheet template and renderer (P11.1). Tests marked ``pdf`` need WeasyPrint with Pango: they run in
CI and in the Docker test image, and are skipped (and reported as skipped) elsewhere."""

from __future__ import annotations

import copy
import http.server
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

from app.modules.documents.render import (
    Branding,
    html_to_pdf,
    logo_uri,
    render_html,
    render_marksheet,
    view_model,
)
from app.modules.documents.service import download_name

PAYLOAD: dict[str, Any] = {
    "schema": 1,
    "institution": {"name": "Demo Public School Society", "display_name": "Demo Public School"},
    "exam": {"name": "Half-yearly", "kind": "term", "term": "Term 1", "session": "2025-26"},
    "scheme": {"name": "Board 9-point", "strategy": "percentage_bands"},
    "student": {
        "enrollment_no": "102401001",
        "full_name": "Aarav Gupta",
        "cohort": {"code": "X-A", "name": "Class X A"},
        "program": None,
    },
    "result": {
        "outcome": "pass",
        "total": "170",
        "max_total": "200",
        "percentage": "85",
        "grade": "A2",
        "grade_point": "9",
        "sgpa": None,
        "credits_attempted": None,
        "credits_earned": None,
        "rank": None,
        "notes": ["Grace of 2 marks applied in Science"],
    },
    "papers": [
        {
            "course_code": "MATH",
            "course_name": "Mathematics",
            "credits": None,
            "attendance": "present",
            "outcome": "pass",
            "total": "88",
            "max_total": "100",
            "percentage": "88",
            "grade": "A2",
            "grade_point": "9",
            "failed_components": [],
            "missing_components": [],
            "components": [
                {"code": "INT", "label": "Internal", "max": "20", "marks": "18"},
                {"code": "TH", "label": "Theory", "max": "80", "marks": "70"},
            ],
        },
        {
            "course_code": "SCI",
            "course_name": "Science",
            "credits": None,
            "attendance": "present",
            "outcome": "fail",
            "total": "32",
            "max_total": "100",
            "percentage": "32",
            "grade": "E",
            "grade_point": None,
            "failed_components": ["TH"],
            "missing_components": [],
            "components": [{"code": "TH", "label": "Theory", "max": "100", "marks": "32"}],
        },
    ],
}
CONTEXT: dict[str, Any] = {
    "branding": Branding(color="#0f766e", footer_text="Office of the Controller of Examinations"),
    "verify_url": "https://verify.scorecode.in/v/7KQ3M9XDPA2F8RTCWV6HQ7MN2B",
    "code_display": "7KQ3-M9XD-PA2F-8RTC-WV6H-Q7MN-2B",
    "version": 1,
    "issued_at": datetime(2026, 10, 7, 20, 30, tzinfo=UTC),  # 8 October in India
    "timezone": "Asia/Kolkata",
}
HOSTILE = '<img src="http://127.0.0.1:9/x"><script>alert(1)</script>'
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def _html(payload: dict[str, Any] = PAYLOAD, **overrides: Any) -> str:
    return render_html(view_model(payload, **{**CONTEXT, **overrides}))


def test_the_marksheet_prints_the_snapshot_and_how_to_verify_it() -> None:
    html = _html()
    for text in (
        "Demo Public School",
        "Demo Public School Society",  # the official name, when it differs
        "Statement of marks",
        "Half-yearly",
        "Term 1 · 2025-26",
        "Aarav Gupta",
        "102401001",
        "Class X A",
        "Mathematics",
        "Internal 18/20 · Theory 70/80",
        "88 / 100",
        "Passed",
        "170 / 200",
        "85%",
        "Grace of 2 marks applied in Science",
        "verify.scorecode.in/v/7KQ3M9XDPA2F8RTCWV6HQ7MN2B",
        "7KQ3-M9XD-PA2F-8RTC-WV6H-Q7MN-2B",
        "Issued 8 October 2026",
        "Office of the Controller of Examinations",
        "through ScoreCode",
    ):
        assert text in html, text
    assert '<td class="fail">Fail</td>' in html  # the failed paper stands out
    assert "#0f766e" in html
    assert "data:image/svg+xml" in html  # the QR code is embedded, not fetched
    assert "Revised statement" not in html
    revised = _html(version=2)
    assert "Revised statement (version 2)" in revised


def test_data_in_the_snapshot_is_printed_never_interpreted() -> None:
    payload = copy.deepcopy(PAYLOAD)
    payload["student"]["full_name"] = HOSTILE
    payload["institution"]["display_name"] = HOSTILE
    payload["papers"][0]["course_name"] = HOSTILE
    payload["result"]["notes"] = [HOSTILE]
    html = _html(payload, branding=Branding(footer_text=HOSTILE, address=HOSTILE))
    assert "<script>" not in html and '<img src="http' not in html
    assert html.count("&lt;script&gt;alert(1)&lt;/script&gt;") >= 5
    # The only sources in the document are our own embedded images.
    assert all(src.startswith("data:") for src in _attr_values(html, "src"))


def _attr_values(html: str, attr: str) -> list[str]:
    import re

    return re.findall(rf'{attr}="([^"]*)"', html)


def test_the_template_engine_is_sandboxed() -> None:
    from app.modules.documents import render

    env = render._env
    assert isinstance(env, SandboxedEnvironment) and env.autoescape
    for source in (
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{ cycler.__init__.__globals__ }}",
        "{{ x.__class__ }}",
    ):
        with pytest.raises(SecurityError):
            env.from_string(source).render(x=1, cycler=object())


def test_only_real_images_become_the_logo() -> None:
    assert logo_uri(PNG_1PX) is not None and logo_uri(PNG_1PX).startswith("data:image/png;base64,")  # type: ignore[union-attr]
    assert logo_uri(b'<svg xmlns="http://www.w3.org/2000/svg"><a href="http://x"/></svg>') is None
    assert logo_uri(b"") is None and logo_uri(None) is None


def test_download_names_are_plain_ascii() -> None:
    payload = copy.deepcopy(PAYLOAD)
    payload["student"]["enrollment_no"] = "10/24 01"
    payload["exam"]["name"] = 'Mid-term "A" <exam>'
    assert download_name(payload, 1) == "Marksheet-10-24-01-Mid-term-A-exam-2025-26.pdf"
    assert download_name(payload, 3).endswith("-v3.pdf")


# ---- WeasyPrint -----------------------------------------------------------------------------------------


@pytest.fixture
def listener() -> Iterator[tuple[str, list[str]]]:
    """A local HTTP server that records every request made to it."""
    hits: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(PNG_1PX)

        def log_message(self, *args: Any) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", hits
    finally:
        server.shutdown()


@pytest.mark.pdf
def test_rendering_never_fetches_external_urls(listener: tuple[str, list[str]], tmp_path: Any) -> None:
    base, hits = listener
    secret = tmp_path / "secret.css"
    secret.write_text("body { background: red }")
    html = f"""<!doctype html><html><head>
      <link rel="stylesheet" href="{base}/sheet.css">
      <style>
        @import url("{base}/import.css");
        @font-face {{ font-family: X; src: url("{base}/font.woff2"); }}
        body {{ background: url("{base}/bg.png"); }}
        h1 {{ background: url("file://{secret}"); }}
      </style></head>
      <body><h1>x</h1><img src="{base}/img.png"><img src="file:///etc/passwd">
      <object data="{base}/object"></object><iframe src="{base}/frame"></iframe>
      <a href="{base}/link">link</a></body></html>"""
    result = html_to_pdf(html)
    assert result.pdf.startswith(b"%PDF-")
    assert hits == []  # nothing reached the network
    refused = " ".join(result.refused)
    for path in ("/sheet.css", "/import.css", "/bg.png", "/img.png", "file:///etc/passwd", str(secret)):
        assert path in refused, path
    # The control: the same server *is* reachable, so "no hits" means "refused", not "unreachable".
    import urllib.request

    with urllib.request.urlopen(f"{base}/control") as r:  # noqa: S310 - local test server
        assert r.status == 200
    assert hits == ["/control"]


@pytest.mark.pdf
def test_a_hostile_snapshot_renders_without_fetching(listener: tuple[str, list[str]]) -> None:
    base, hits = listener
    payload = copy.deepcopy(PAYLOAD)
    payload["student"]["full_name"] = f'<img src="{base}/name.png"><link rel=stylesheet href="{base}/n.css">'
    result = render_marksheet(payload, **CONTEXT)
    assert result.pdf.startswith(b"%PDF-") and hits == [] and result.refused == []


@pytest.mark.pdf
def test_a_marksheet_renders_with_logo_and_qr_code() -> None:
    result = render_marksheet(PAYLOAD, **{**CONTEXT, "branding": Branding(logo=PNG_1PX)})
    assert result.pdf.startswith(b"%PDF-") and result.refused == []
    assert 5_000 < len(result.pdf) < 400_000
    # Timing per PDF is measured on the Docker image: scripts/measure_marksheets.py.


@pytest.mark.pdf
def test_marksheets_lay_out_in_spawned_processes() -> None:
    """The worker's process pool (P14.3): arguments and results cross the process boundary intact."""
    from functools import partial

    from app.modules.documents.pool import pool, shutdown

    try:
        futures = [
            pool(2).submit(partial(render_marksheet, PAYLOAD, **{**CONTEXT, "code_display": f"CODE-{i}"}))
            for i in range(4)
        ]
        results = [f.result(timeout=120) for f in futures]
    finally:
        shutdown()
    assert all(r.pdf.startswith(b"%PDF-") and r.refused == [] for r in results)
    assert len({r.pdf for r in results}) == 4  # each one its own document


def _pdf_text(pdf: bytes) -> bytes:
    """The PDF with its compressed streams (object streams included) inflated, for searching."""
    import contextlib
    import re
    import zlib

    out = [pdf]
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        with contextlib.suppress(zlib.error):
            out.append(zlib.decompress(m.group(1)))
    return b"\n".join(out)


@pytest.mark.pdf
def test_hindi_and_punjabi_marksheets_embed_fonts_for_their_scripts() -> None:
    """Without a Devanagari or Gurmukhi font the bilingual labels would print as boxes (P18.4)."""
    for lang, script in (("hi", b"Devanagari"), ("pa", b"Gurmukhi")):
        result = render_marksheet(PAYLOAD, **{**CONTEXT, "language": lang})
        assert result.pdf.startswith(b"%PDF-") and result.refused == []
        assert script in _pdf_text(result.pdf), f"no {script.decode()} font in the {lang} marksheet"
