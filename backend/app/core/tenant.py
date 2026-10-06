"""Request realm and tenant context (isolation layer L1, docs/06 §3).

The realm is derived only from the ``Host`` header:

* ``<slug>.<base>`` or a verified custom domain → ``tenant`` realm
* ``admin.<base>`` → ``platform`` realm (no tenant)
* ``verify.<base>`` → ``verify`` realm (tenant derived from the verification code, never the host)
* ``<base>`` / ``www.<base>`` → ``site`` realm (marketing & sign-up)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import Settings


class Realm(StrEnum):
    TENANT = "tenant"
    PLATFORM = "platform"
    VERIFY = "verify"
    SITE = "site"


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: uuid.UUID
    slug: str
    name: str
    status: str
    host: str

    def cache_key(self, *parts: object) -> str:
        """Tenant-prefixed cache key (L5). The only way modules build tenant cache keys."""
        return "t:" + str(self.tenant_id) + ":" + ":".join(str(p) for p in parts)


@dataclass(frozen=True, slots=True)
class HostInfo:
    realm: Realm
    host: str
    slug: str | None = None  # tenant subdomain, when the host is <slug>.<base>
    custom_domain: bool = False


SLUG_RE = re.compile(r"^[a-z0-9](?:-?[a-z0-9]){2,30}$")
_HOST_RE = re.compile(r"^[a-z0-9.-]{1,253}$")


def normalise_host(raw: str | None) -> str | None:
    if not raw:
        return None
    host = raw.strip().lower().rstrip(".")
    if host.startswith("["):  # IPv6 literal — never a tenant host
        return None
    host = host.split(":", 1)[0]
    if not _HOST_RE.match(host):
        return None
    return host


def classify_host(raw: str | None, settings: Settings) -> HostInfo | None:
    host = normalise_host(raw)
    if host is None:
        return None
    base = settings.base_domain.lower()
    if host in (base, f"www.{base}"):
        return HostInfo(Realm.SITE, host)
    if host == settings.platform_host:
        return HostInfo(Realm.PLATFORM, host)
    if host == settings.verify_host:
        return HostInfo(Realm.VERIFY, host)
    suffix = "." + base
    if host.endswith(suffix):
        label = host[: -len(suffix)]
        if "." in label or not SLUG_RE.match(label):
            return None
        return HostInfo(Realm.TENANT, host, slug=label)
    return HostInfo(Realm.TENANT, host, custom_domain=True)
