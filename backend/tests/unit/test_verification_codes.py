"""Verification codes and masking (P11.4, docs/10 §10)."""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from app.modules.verification.codes import (
    ALPHABET,
    LENGTH,
    grouped,
    mask_identifier,
    mask_name,
    new_code,
    normalize,
)
from app.modules.verification.models import CODE_PATTERN


def test_codes_are_26_crockford_characters_carrying_128_random_bits() -> None:
    codes = {new_code() for _ in range(20_000)}
    assert len(codes) == 20_000
    assert all(re.fullmatch(CODE_PATTERN, c) for c in codes)
    assert LENGTH == 26 and len(ALPHABET) == 32 and not set("ILOU") & set(ALPHABET)
    # 26 × 5 = 130 bits of room for 128: the first character carries the top 3 bits only (0–7).
    assert {c[0] for c in codes} == set("01234567")
    # Every other position uses the whole alphabet (a sign the bits aren't biased or truncated).
    assert all({c[i] for c in codes} == set(ALPHABET) for i in range(1, LENGTH))


@given(st.integers(min_value=0, max_value=2**128 - 1), st.sampled_from(["", "-", " "]), st.booleans())
def test_what_people_type_normalizes_back_to_the_code(value: int, sep: str, lower: bool) -> None:
    code = "".join(ALPHABET[(value >> (5 * (LENGTH - 1 - i))) & 31] for i in range(LENGTH))
    typed = grouped(code).replace("-", sep)
    assert normalize(typed.lower() if lower else typed) == code


def test_crockford_look_alikes_and_rejects() -> None:
    code = "7KQ3M9XDPA2F8RTCWV6HQ7MN2B"
    assert normalize("7kq3-m9xd-pa2f-8rtc-wv6h-q7mn-2b") == code
    assert normalize(code.replace("1", "x")) == code  # nothing to replace: unchanged
    assert normalize("0" * 25 + "O") == "0" * 26  # O reads as zero
    assert normalize("1" * 25 + "I") == normalize("1" * 25 + "L") == "1" * 26  # I and L read as one
    for bad in ("", "7KQ3", code + "0", code[:-1] + "U", code[:-1] + "!", "<script>" * 4):
        assert normalize(bad) is None
    assert grouped(code) == "7KQ3-M9XD-PA2F-8RTC-WV6H-Q7MN-2B"


def test_masking_keeps_only_what_a_verifier_needs_to_match_a_person() -> None:
    assert mask_name("Aarav Gupta") == "Aa*** Gu***"
    assert mask_name("Priya K. Sharma") == "Pr*** K.*** Sh***"
    assert mask_name("A B") == "A B"
    assert mask_name("   ") == "***"
    assert mask_identifier("102401001") == "10*****01"
    assert mask_identifier("A001") == "****"
    assert mask_identifier("AB12C") == "AB***2C"
