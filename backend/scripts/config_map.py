"""Print the settings → consumers → tests table for docs/configuration.md.

    cd backend && uv run python scripts/config_map.py > /tmp/map.md

Every field of ``app.core.config.Settings`` with the modules that read it (``settings.<field>`` or
``cfg.<field>`` in app/) and the test files that mention it (by attribute or ``SCORECODE_<FIELD>``).
``tests/unit/test_configuration_doc.py`` fails if docs/configuration.md misses a setting.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def _files(base: str) -> dict[str, str]:
    return {str(p.relative_to(ROOT)): p.read_text() for p in (ROOT / base).rglob("*.py")}


# Settings read through a derived property count as read wherever the property is.
VIA = {
    "platform_subdomain": ["platform_host"],
    "verify_subdomain": ["verify_host"],
    "public_port": ["public_origin", "tenant_origin"],
    "public_scheme": ["public_origin", "tenant_origin"],
    "base_domain": ["platform_host", "verify_host", "tenant_origin"],
    "cookie_secure": ["session_cookie_name", "csrf_cookie_name"],
    "worker_queues": ["queues"],
    "env": ["is_production_like"],
}


def main() -> None:
    app = {**_files("app"), **_files("migrations"), **_files("scripts")}
    tests = _files("tests")
    print("| Variable | Default | Read by | Tested in |")
    print("|---|---|---|---|")
    for name, field in Settings.model_fields.items():
        env = f"SCORECODE_{name.upper()}"
        attr = re.compile(rf"\.({'|'.join([name, *VIA.get(name, [])])})\b")
        kw = re.compile(rf"\b{name}\s*=")
        readers = sorted(
            {p.removeprefix("app/").removesuffix(".py") for p, t in app.items() if attr.search(t)}
            - {"core/config", "scripts/config_map"}
        )
        tested = sorted(
            {
                Path(p).name.removesuffix(".py")
                for p, t in tests.items()
                if attr.search(t) or kw.search(t) or env in t
            }
        )
        default = field.default
        if hasattr(default, "get_secret_value"):
            default = "(secret)"
        shown = "—" if default in (None, "") else f"`{default}`"
        if isinstance(default, str) and "@" in default:
            shown = "dev URL"
        print(
            f"| `{env}` | {shown} | {', '.join(f'`{r}`' for r in readers[:6]) or '—'}"
            f"{' …' if len(readers) > 6 else ''} | {', '.join(tested[:4]) or '—'}{' …' if len(tested) > 4 else ''} |"
        )


if __name__ == "__main__":
    main()
