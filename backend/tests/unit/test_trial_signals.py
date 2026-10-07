"""Trial identity signals (docs/12 §6): normalisation collapses look-alikes, hashing hides the values."""

from __future__ import annotations

import pytest

from app.modules.entitlements.trial_signals import (
    collect,
    digest,
    institutional_domain,
    network_of,
    normalize_email,
    normalize_name,
    normalize_phone,
)

KEY = b"k" * 32


@pytest.mark.parametrize(
    ("raw", "normal"),
    [
        ("John.Smith@gmail.com", "johnsmith@gmail.com"),
        ("j.o.h.n.s.m.i.t.h+trial2@GoogleMail.com", "johnsmith@gmail.com"),
        ("  principal+scorecode@StMarys.edu.in ", "principal@stmarys.edu.in"),
        ("first.last@school.org", "first.last@school.org"),  # dots matter outside Gmail
        ("a@outlook.com.", "a@outlook.com"),
    ],
)
def test_email_variants_collapse(raw: str, normal: str) -> None:
    assert normalize_email(raw) == normal


@pytest.mark.parametrize(
    ("email", "domain"),
    [
        ("head@gmail.com", None),
        ("head@rediffmail.com", None),
        ("head@stmarys.edu.in", "stmarys.edu.in"),
        ("exams@mail.stmarys.edu.in", "stmarys.edu.in"),
        ("registrar@thapar.edu", "thapar.edu"),
        ("registrar@cs.thapar.edu", "thapar.edu"),
        ("office@academy.co.uk", "academy.co.uk"),
    ],
)
def test_institutional_domains(email: str, domain: str | None) -> None:
    assert institutional_domain(email) == domain


@pytest.mark.parametrize(
    ("raw", "normal"),
    [
        ("98765 43210", "919876543210"),
        ("+91-98765-43210", "919876543210"),
        ("09876543210", "919876543210"),
        ("0091 98765 43210", "919876543210"),
        ("+1 (415) 555-0100", "14155550100"),
        ("12345", None),
        (None, None),
    ],
)
def test_phone_numbers(raw: str | None, normal: str | None) -> None:
    assert normalize_phone(raw) == normal


def test_institution_names() -> None:
    assert normalize_name("St. Mary's Sr. Sec. School,  Delhi") == "st marys sr sec school delhi"
    assert normalize_name("ST MARYS SR SEC SCHOOL DELHI") == "st marys sr sec school delhi"
    assert normalize_name("Ârya & Sons Academy") == "arya and sons academy"
    assert normalize_name("A.B") is None  # too short to mean anything


def test_networks() -> None:
    assert network_of("203.0.113.77") == "203.0.113.0/24"
    assert network_of("2001:db8:abcd:12::1") == "2001:db8:abcd::/48"
    assert network_of("10.1.2.3") is None and network_of("127.0.0.1") is None
    assert network_of("not-an-ip") is None and network_of(None) is None


def test_signals_are_keyed_hashes_and_never_contain_the_values() -> None:
    signals = collect(
        KEY,
        tenant_id="t1",
        owner_email="J.Ohn+x@gmail.com",
        device_id="d" * 32,
        phones=["98765 43210", "+91 98765 43210", None],
        institution_name="Green Valley School",
        ip="203.0.113.9",
    )
    kinds = sorted(s.kind for s in signals)
    assert kinds == ["device", "email", "name", "phone", "subnet", "tenant"]  # gmail: no domain signal
    email = next(s for s in signals if s.kind == "email")
    assert email.digest == digest(KEY, "email", "john@gmail.com") and len(email.digest) == 64
    assert all("john" not in s.digest and "9876" not in s.digest for s in signals)
    assert digest(b"other" * 8, "email", "john@gmail.com") != email.digest  # the key matters


def test_untrusted_device_ids_are_ignored() -> None:
    def kinds(device: str | None) -> set[str]:
        return {
            s.kind
            for s in collect(
                KEY,
                tenant_id="t",
                owner_email="a@school.org",
                device_id=device,
                phones=[],
                institution_name="Name here",
                ip=None,
            )
        }

    assert "device" not in kinds("short") and "device" not in kinds("x" * 500) and "device" in kinds("x" * 40)
