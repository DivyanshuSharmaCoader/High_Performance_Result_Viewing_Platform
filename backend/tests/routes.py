"""Route-table introspection shared by the isolation suite and the authorization matrix."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import fastapi.routing as fr

from app.core.http import ACCESS_POLICY_ATTR

PARAM_RE = re.compile(r"{([a-z_]+)(?::[a-z]+)?}")


@dataclass(frozen=True)
class RouteInfo:
    method: str
    path: str
    policy: str  # "tenant:perm,…" | "platform:…" | "public:realm,…"
    params: tuple[str, ...]

    @property
    def realm(self) -> str:
        return self.policy.split(":", 1)[0]

    @property
    def permissions(self) -> frozenset[str]:
        """All-of permissions (``tenant:a,b``); for any-of routes (``tenant:a|b``) see ``allows``."""
        _, _, rest = self.policy.partition(":")
        return frozenset(p for p in rest.split(",") if p) if self.realm == "tenant" else frozenset()

    def allows(self, granted: frozenset[str]) -> bool:
        _, _, rest = self.policy.partition(":")
        if "|" in rest:
            return any(p in granted for p in rest.split("|"))
        return self.permissions <= granted

    def url(self, values: dict[str, Any]) -> str:
        return PARAM_RE.sub(lambda m: str(values[m.group(1)]), self.path)


def _policies(dependant: Any) -> list[str]:
    found: list[str] = []
    for dep in dependant.dependencies:
        if dep.call is not None and hasattr(dep.call, ACCESS_POLICY_ATTR):
            found.append(getattr(dep.call, ACCESS_POLICY_ATTR))
        found.extend(_policies(dep))
    return found


def api_routes(app: Any) -> list[RouteInfo]:
    out = []
    for ctx in fr.iter_route_contexts(app.routes):
        route = ctx.route
        if not isinstance(route, fr.APIRoute) or not route.path.startswith("/api/v1"):
            continue
        policies = _policies(route.dependant)
        if not policies:
            continue
        for method in sorted(route.methods - {"HEAD"}):
            out.append(RouteInfo(method, route.path, policies[0], tuple(PARAM_RE.findall(route.path))))
    return out
