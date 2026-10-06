"""Print the OpenAPI document (``make openapi`` → backend/openapi.json → TypeScript types)."""

from __future__ import annotations

import json
import sys

from app.core.config import Settings
from app.core.container import Infra
from app.main import create_app


def main() -> None:
    settings = Settings(log_json=False, log_level="ERROR")
    app = create_app(settings, Infra.build(settings, app_name="scorecode-openapi"))
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
