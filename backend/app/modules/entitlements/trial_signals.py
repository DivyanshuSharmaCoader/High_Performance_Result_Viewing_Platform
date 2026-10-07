"""Identity signals that stop one institution from taking the free trial twice (docs/12 §6).

Pure functions. Each signal is normalised so that trivial variations collapse to one value — Gmail's dots
and ``+tags``, an email's case, a phone number's spacing and country code, an institution name's
punctuation — and then keyed-hashed (HMAC-SHA256), so the database only ever holds digests. The key must
stay the same for the life of the service: changing it would forget every trial ever taken.

*Hard* signals belong to one claimant and are verified (an email inbox, the email's institutional domain,
a device cookie the server set, the tenant itself): a second trial with any of them is refused. *Soft*
signals can be shared or typed by anyone (a phone number nobody verified, an institution's name, a network
range): they only add risk, so an attacker can't use them to block somebody else.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import unicodedata
from dataclasses import dataclass

HARD_KINDS = ("email", "domain", "device", "tenant")
SOFT_KINDS = ("phone", "name", "subnet")

# Mailbox providers that hand out addresses to anyone: their domain says nothing about the institution.
FREEMAIL = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.in",
        "ymail.com",
        "rocketmail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "pm.me",
        "zoho.com",
        "zohomail.in",
        "rediffmail.com",
        "gmx.com",
        "mail.com",
        "yandex.com",
        "tutanota.com",
        "fastmail.com",
        "hey.com",
    }
)
DOMAIN_ALIASES = {"googlemail.com": "gmail.com"}
DOTS_IGNORED = frozenset({"gmail.com"})  # j.o.h.n@gmail.com is john@gmail.com


def normalize_email(email: str) -> str:
    """``J.Ohn+trial@GoogleMail.com`` → ``john@gmail.com``. Plus-addressing is dropped everywhere: the
    providers that support it deliver ``a+x@`` to ``a@``, and the rest rarely issue such addresses."""
    local, _, domain = email.strip().lower().rpartition("@")
    domain = DOMAIN_ALIASES.get(domain, domain).rstrip(".")
    local = local.split("+", 1)[0]
    if domain in DOTS_IGNORED:
        local = local.replace(".", "")
    return f"{local}@{domain}"


def institutional_domain(email: str) -> str | None:
    """The email's domain when it identifies an organisation (not a free mailbox provider)."""
    domain = normalize_email(email).rpartition("@")[2]
    if not domain or domain in FREEMAIL:
        return None
    # school.edu.in and mail.school.edu.in are the same institution: keep the registrable-looking tail.
    parts = domain.split(".")
    second_level = {"ac", "edu", "co", "org", "gov", "net", "res", "nic"}
    keep = 3 if len(parts) >= 3 and parts[-2] in second_level else 2
    return ".".join(parts[-keep:])


def normalize_phone(phone: str | None, default_country: str = "91") -> str | None:
    """Digits only, with the country code; Indian numbers may be written with a leading 0 or none."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if phone.strip().startswith("00"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = default_country + digits[1:]
    elif len(digits) == 10:
        digits = default_country + digits
    return digits if 10 <= len(digits) <= 15 else None


_NAME_STOP = re.compile(r"[^a-z0-9 ]+")


def normalize_name(name: str) -> str | None:
    """``St. Mary's Sr. Sec. School,  Delhi`` → ``st marys sr sec school delhi``."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    text = text.replace("&", " and ").replace("'", "")
    text = " ".join(_NAME_STOP.sub(" ", text).split())
    return text if len(text) >= 4 else None


def network_of(ip: str | None) -> str | None:
    """The /24 (IPv4) or /48 (IPv6) the address belongs to: one office or home network, roughly."""
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.is_loopback or addr.is_link_local or any(addr in net for net in LOCAL_NETWORKS):
        return None  # a local network says nothing about who is asking
    prefix = 24 if addr.version == 4 else 48
    return str(ipaddress.ip_network(f"{addr}/{prefix}", strict=False))


LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7")
)


@dataclass(frozen=True, slots=True)
class Signal:
    kind: str
    digest: str


def digest(key: bytes, kind: str, value: str) -> str:
    return hmac.new(key, f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def collect(
    key: bytes,
    *,
    tenant_id: str,
    owner_email: str,
    device_id: str | None,
    phones: list[str | None],
    institution_name: str,
    ip: str | None,
) -> list[Signal]:
    """Every signal for one trial request, hashed. Duplicates (e.g. the same phone twice) collapse."""
    raw: list[tuple[str, str | None]] = [
        ("tenant", tenant_id),
        ("email", normalize_email(owner_email)),
        ("domain", institutional_domain(owner_email)),
        ("device", device_id if device_id and 16 <= len(device_id) <= 128 else None),
        ("name", normalize_name(institution_name)),
        ("subnet", network_of(ip)),
        *(("phone", normalize_phone(p)) for p in phones),
    ]
    seen: dict[tuple[str, str], Signal] = {}
    for kind, value in raw:
        if value:
            s = Signal(kind, digest(key, kind, value))
            seen.setdefault((kind, s.digest), s)
    return list(seen.values())
