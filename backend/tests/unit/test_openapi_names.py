"""Schema names in the OpenAPI contract must be unique: when two modules define the same model name,
FastAPI silently renames *both* (``app__modules__…__CohortOut``), which breaks the generated client types."""

from __future__ import annotations

from app.core.config import get_settings
from app.main import create_app


def test_no_colliding_schema_names() -> None:
    schemas = create_app(get_settings()).openapi()["components"]["schemas"]
    clashes = sorted(name for name in schemas if name.startswith("app__"))
    assert not clashes, f"rename these models so each schema name is unique: {clashes}"
