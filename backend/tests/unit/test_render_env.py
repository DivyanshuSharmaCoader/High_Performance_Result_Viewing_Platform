"""infra/ops/server/render-env.py: the edge's image policy follows the object store (logo regression)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RENDER_ENV = Path(__file__).resolve().parents[3] / "infra" / "ops" / "server" / "render-env.py"


def _module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("render_env", RENDER_ENV)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("https://0123abcd.r2.cloudflarestorage.com", "https://0123abcd.r2.cloudflarestorage.com"),
        ("https://0123abcd.r2.cloudflarestorage.com/", "https://0123abcd.r2.cloudflarestorage.com"),
        ("http://s3:8333", "http://s3:8333"),
        ("https://files.example.org/bucket?x=1", "https://files.example.org"),
    ],
)
def test_files_origin_is_the_object_stores_scheme_and_host(endpoint: str, expected: str) -> None:
    assert _module().origin(endpoint) == expected


def test_files_origin_refuses_what_isnt_a_url() -> None:
    with pytest.raises(SystemExit):
        _module().origin("r2.cloudflarestorage.com")


def test_the_template_has_the_line_render_env_fills() -> None:
    template = (RENDER_ENV.parents[1] / "env" / "deploy.env.example").read_text()
    assert any(line.startswith("FILES_ORIGIN=") for line in template.splitlines())
    compose = (RENDER_ENV.parents[3] / "compose.prod.yml").read_text()
    assert "FILES_ORIGIN: ${FILES_ORIGIN:-" in compose
