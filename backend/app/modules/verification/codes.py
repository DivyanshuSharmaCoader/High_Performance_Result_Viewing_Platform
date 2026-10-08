"""Verification codes and the masking used on the public page (docs/10 §10).

* A code is 16 bytes from ``secrets`` (128 bits) in Crockford base32: 26 characters, no I, L, O or U, so
  it survives being read aloud or typed from paper. It is random, so it says nothing about the student,
  exam or institution, and 2^128 possibilities make guessing hopeless.
* ``normalize`` accepts what people actually type: lower case, spaces or dashes between groups, and the
  look-alikes Crockford defines (I and L read as 1, O as 0).
* The public page shows identity only masked: ``Aarav Gupta`` → ``Aa*** Gu***``.
"""

from __future__ import annotations

import secrets

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LENGTH = 26  # ceil(128 / 5)
_LOOKALIKES = str.maketrans({"I": "1", "L": "1", "O": "0"})
_VALID = frozenset(ALPHABET)


def new_code() -> str:
    value = int.from_bytes(secrets.token_bytes(16), "big")
    chars = []
    for _ in range(LENGTH):
        value, digit = divmod(value, 32)
        chars.append(ALPHABET[digit])
    return "".join(reversed(chars))


def normalize(raw: str) -> str | None:
    """The canonical code for user input, or ``None`` when it cannot be one (no lookup needed)."""
    cleaned = "".join(raw.split()).replace("-", "").upper().translate(_LOOKALIKES)
    if len(cleaned) != LENGTH or not set(cleaned) <= _VALID:
        return None
    return cleaned


def grouped(code: str) -> str:
    """``7KQ3-M9XD-PA2F-8RTC-WV6H-Q7MN-2B`` style, for print and screen."""
    return "-".join(code[i : i + 4] for i in range(0, len(code), 4))


def mask_name(name: str) -> str:
    """First two letters of each word, then ``***``; one-letter words stay as they are."""
    parts = []
    for word in name.split():
        parts.append(word if len(word) <= 1 else f"{word[:2]}***")
    return " ".join(parts) or "***"


def mask_identifier(value: str) -> str:
    """Keep the first two and last two characters; mask the rest (at least three stars)."""
    if len(value) <= 4:
        return "*" * max(3, len(value))
    return f"{value[:2]}{'*' * max(3, len(value) - 4)}{value[-2:]}"
