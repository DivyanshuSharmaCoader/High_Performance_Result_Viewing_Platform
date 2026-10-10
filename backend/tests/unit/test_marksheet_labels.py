"""Bilingual marksheet labels (P18.4)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.documents.labels import LABELS, OUTCOMES, PAPER_OUTCOMES, bilingual, language_of
from app.modules.documents.render import Branding, render_html, view_model
from tests.unit.test_marksheet_render import PAYLOAD  # the schema-1 sample


def test_every_label_has_every_language() -> None:
    for table in (LABELS, OUTCOMES, PAPER_OUTCOMES):
        for key, texts in table.items():
            assert set(texts) == {"en", "hi", "pa"}, key
            assert all(t.strip() for t in texts.values()), key


def test_language_of_locales() -> None:
    assert [language_of(x) for x in ("hi-IN", "pa-IN", "en-IN", "ta-IN", None, "")] == [
        "hi",
        "pa",
        "en",
        "en",
        "en",
        "en",
    ]


def test_bilingual_is_english_alone_or_english_with_the_translation_escaped() -> None:
    assert str(bilingual({"en": "Name", "hi": "नाम"}, "en")) == "Name"
    assert (
        str(bilingual({"en": "Name", "hi": "नाम"}, "hi")) == 'Name<span class="alt" lang="hi"> · नाम</span>'
    )
    assert "&lt;b&gt;" in str(bilingual({"en": "<b>", "hi": "<b>"}, "hi"))


def _html(language: str) -> str:
    ctx = view_model(
        PAYLOAD,
        branding=Branding(),
        verify_url="https://verify.scorecode.test/v/ABCD",
        code_display="ABCD-EFGH",
        version=2,
        issued_at=datetime(2026, 10, 10, tzinfo=UTC),
        timezone="Asia/Kolkata",
        language=language,
    )
    return render_html(ctx)


def test_hindi_and_punjabi_marksheets_carry_both_languages() -> None:
    hi, pa, en = _html("hi"), _html("pa"), _html("en")
    assert "Statement of marks" in hi and "अंक विवरण" in hi and 'lang="hi"' in hi
    assert "ਅੰਕ ਵੇਰਵਾ" in pa and 'lang="pa"' in pa
    assert "संशोधित विवरण (संस्करण 2)" in hi  # the revised notice, translated with its version
    assert "अंक विवरण" not in en and 'class="alt"' not in en
