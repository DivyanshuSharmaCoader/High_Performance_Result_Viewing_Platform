"""docs/configuration.md lists every application setting (P18.2)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings

DOC = Path(__file__).resolve().parents[3] / "docs" / "configuration.md"


def test_every_setting_is_in_the_configuration_map() -> None:
    text = DOC.read_text()
    missing = [
        f"SCORECODE_{n.upper()}" for n in Settings.model_fields if f"`SCORECODE_{n.upper()}`" not in text
    ]
    assert not missing, f"add these to docs/configuration.md (scripts/config_map.py): {missing}"


def _documented(name: str, text: str) -> bool:
    """`SCORECODE_A_B_C`, or a shorthand row like `SCORECODE_A_X` / `_B_C` (shared prefix, own suffix)."""
    tokens = name.upper().split("_")
    if f"SCORECODE_{name.upper()}" in text:
        return True
    return any(
        f"`SCORECODE_{'_'.join(tokens[:k])}" in text and f"`_{'_'.join(tokens[k:])}`" in text
        for k in range(len(tokens))
    )


def test_environment_reference_lists_every_setting() -> None:
    text = (DOC.parent / "ENVIRONMENT.md").read_text()
    missing = [n for n in Settings.model_fields if not _documented(n, text)]
    assert not missing, f"document these in docs/ENVIRONMENT.md: {missing}"
