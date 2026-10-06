"""Every process entrypoint must register every table before touching the ORM; otherwise a foreign key
to a module the process never imported fails at runtime (this broke `scorecode seed` once)."""

from __future__ import annotations

import subprocess
import sys

import pytest

CHECK = """
import importlib, sys
importlib.import_module(sys.argv[1])
from app.core.models import Base
registered = set(Base.metadata.tables)
import app.models_registry
missing = set(Base.metadata.tables) - registered
assert not missing, f"{sys.argv[1]} does not import: {sorted(missing)}"
"""


@pytest.mark.parametrize("entrypoint", ["app.cli", "app.worker", "app.main"])
def test_entrypoint_registers_every_table(entrypoint: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, "-c", CHECK, entrypoint], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr[-2000:]
