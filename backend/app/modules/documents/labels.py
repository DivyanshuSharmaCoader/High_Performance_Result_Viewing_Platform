"""Marksheet labels in English, Hindi and Punjabi (decision D29, P18.4).

A marksheet is bilingual when the institution's language is Hindi or Punjabi: every label is English with
the translation beside it, as Indian statements of marks usually are, so the same PDF reads for an
employer anywhere and for a parent at home. The second language is marked up with its ``lang`` and no
letter-spacing or upper-casing (both break Devanagari and Gurmukhi shaping).

The translations were written for ScoreCode and should be checked by a native speaker before a school
relies on them (docs/user-guide/README.md). Adding a language is a new column here and in the student
catalogue (frontend/apps/tenant/src/lib/i18n).
"""

from __future__ import annotations

from markupsafe import Markup, escape

LANGUAGES = ("en", "hi", "pa")

LABELS: dict[str, dict[str, str]] = {
    "statement": {"en": "Statement of marks", "hi": "अंक विवरण", "pa": "ਅੰਕ ਵੇਰਵਾ"},
    "name": {"en": "Name", "hi": "नाम", "pa": "ਨਾਮ"},
    "enrollment_no": {"en": "Enrollment no.", "hi": "नामांकन संख्या", "pa": "ਦਾਖਲਾ ਨੰਬਰ"},
    "class_section": {"en": "Class / section", "hi": "कक्षा / वर्ग", "pa": "ਜਮਾਤ / ਸੈਕਸ਼ਨ"},
    "programme": {"en": "Programme", "hi": "कार्यक्रम", "pa": "ਪ੍ਰੋਗਰਾਮ"},
    "code": {"en": "Code", "hi": "कोड", "pa": "ਕੋਡ"},
    "paper": {"en": "Paper", "hi": "विषय", "pa": "ਵਿਸ਼ਾ"},
    "credits": {"en": "Credits", "hi": "क्रेडिट", "pa": "ਕ੍ਰੈਡਿਟ"},
    "marks": {"en": "Marks", "hi": "अंक", "pa": "ਅੰਕ"},
    "grade": {"en": "Grade", "hi": "ग्रेड", "pa": "ਗ੍ਰੇਡ"},
    "result": {"en": "Result", "hi": "परिणाम", "pa": "ਨਤੀਜਾ"},
    "total": {"en": "Total", "hi": "कुल", "pa": "ਕੁੱਲ"},
    "percentage": {"en": "Percentage", "hi": "प्रतिशत", "pa": "ਪ੍ਰਤੀਸ਼ਤ"},
    "sgpa": {"en": "SGPA", "hi": "एसजीपीए", "pa": "ਐੱਸਜੀਪੀਏ"},
    "grade_point": {"en": "Grade point", "hi": "ग्रेड पॉइंट", "pa": "ਗ੍ਰੇਡ ਪੁਆਇੰਟ"},
    "rank": {"en": "Rank", "hi": "स्थान", "pa": "ਸਥਾਨ"},
    "verify_title": {"en": "Verify this statement", "hi": "इस विवरण का सत्यापन करें", "pa": "ਇਸ ਵੇਰਵੇ ਦੀ ਪੁਸ਼ਟੀ ਕਰੋ"},
    "verify_scan": {
        "en": "Scan the code, or visit",
        "hi": "कोड स्कैन करें, या यहाँ जाएँ",
        "pa": "ਕੋਡ ਸਕੈਨ ਕਰੋ, ਜਾਂ ਇੱਥੇ ਜਾਓ",
    },
    "verification_code": {"en": "Verification code", "hi": "सत्यापन कोड", "pa": "ਪੁਸ਼ਟੀ ਕੋਡ"},
    "issued": {"en": "Issued", "hi": "जारी", "pa": "ਜਾਰੀ"},
    "grading": {"en": "Grading", "hi": "ग्रेडिंग", "pa": "ਗ੍ਰੇਡਿੰਗ"},
    "revised": {
        "en": "Revised statement (version {version}). It replaces any earlier statement of marks for this exam.",
        "hi": "संशोधित विवरण (संस्करण {version})। यह इस परीक्षा के किसी भी पिछले अंक विवरण का स्थान लेता है।",
        "pa": "ਸੋਧਿਆ ਹੋਇਆ ਵੇਰਵਾ (ਸੰਸਕਰਣ {version})। ਇਹ ਇਸ ਪ੍ਰੀਖਿਆ ਦੇ ਕਿਸੇ ਵੀ ਪਹਿਲੇ ਅੰਕ ਵੇਰਵੇ ਦੀ ਥਾਂ ਲੈਂਦਾ ਹੈ।",
    },
}

# The overall result and each paper's result (codes of the result payload).
OUTCOMES: dict[str, dict[str, str]] = {
    "pass": {"en": "Passed", "hi": "उत्तीर्ण", "pa": "ਪਾਸ"},
    "fail": {"en": "Not passed", "hi": "अनुत्तीर्ण", "pa": "ਪਾਸ ਨਹੀਂ"},
    "absent": {"en": "Absent", "hi": "अनुपस्थित", "pa": "ਗੈਰਹਾਜ਼ਰ"},
    "withheld": {"en": "Result withheld", "hi": "परिणाम रोका गया", "pa": "ਨਤੀਜਾ ਰੋਕਿਆ ਗਿਆ"},
    "incomplete": {"en": "Incomplete", "hi": "अपूर्ण", "pa": "ਅਧੂਰਾ"},
}
PAPER_OUTCOMES: dict[str, dict[str, str]] = {
    "pass": {"en": "Pass", "hi": "उत्तीर्ण", "pa": "ਪਾਸ"},
    "fail": {"en": "Fail", "hi": "अनुत्तीर्ण", "pa": "ਫੇਲ੍ਹ"},
    "absent": {"en": "Absent", "hi": "अनुपस्थित", "pa": "ਗੈਰਹਾਜ਼ਰ"},
    "exempt": {"en": "Exempt", "hi": "छूट", "pa": "ਛੋਟ"},
    "withheld": {"en": "Withheld", "hi": "रोका गया", "pa": "ਰੋਕਿਆ ਗਿਆ"},
    "incomplete": {"en": "Incomplete", "hi": "अपूर्ण", "pa": "ਅਧੂਰਾ"},
}


def language_of(locale: str | None) -> str:
    """``hi-IN`` → ``hi``; anything unknown → ``en``."""
    lang = (locale or "en").split("-", 1)[0].lower()
    return lang if lang in LANGUAGES else "en"


def bilingual(texts: dict[str, str], lang: str, *, sep: str = " · ", **fmt: object) -> Markup:
    """English, plus the institution's language beside it when that isn't English (escaped either way:
    ``escape`` and ``Markup.format`` escape every argument)."""
    english = texts["en"].format(**fmt)
    if lang == "en" or lang not in texts:
        return escape(english)
    return Markup('{}<span class="alt" lang="{}">{}{}</span>').format(
        english, lang, sep, texts[lang].format(**fmt)
    )


def labels(lang: str) -> dict[str, Markup]:
    return {key: bilingual(texts, lang) for key, texts in LABELS.items() if key != "revised"}
