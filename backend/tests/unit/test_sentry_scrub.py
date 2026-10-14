"""Sentry receives errors with nothing personal in them (P18.6).

The scrubber is checked on its own, then end to end through the real SDK with a transport that keeps the
envelopes in memory: what these tests see is exactly what would leave the process.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from app.cli import SENTRY_TEST
from app.core.config import Settings
from app.core.sentry import init_sentry, scrub_breadcrumb, scrub_event, scrub_text

PERSONAL = (
    "test.parent@example.com",
    "9876543210",
    "102401001",
    "45.5",
    "abcdefghijklmnopqrstuvwxyz0123456789",
    "0192f1c6-3b6e-7a2c-9d1e-123456789abc",
    "sc_session=",
    "hunter2-secret",
)


def test_scrub_text_removes_people_and_secrets_and_keeps_the_sentence() -> None:
    out = scrub_text(SENTRY_TEST)
    assert out == (
        "ScoreCode Sentry test: student [email], phone [phone], enrollment [number], marks [n], token [token]"
    )
    assert scrub_text("+91 98765 43210 called") == "[phone] called"
    assert scrub_text("password=hunter2 token: abc") == "password=[secret] token: [secret]"
    assert scrub_text("Authorization: Bearer eyJhbGciOi.xyz") == "Authorization: Bearer [secret]"
    assert scrub_text("student 0192f1c6-3b6e-7a2c-9d1e-123456789abc") == "student [id]"
    assert scrub_text("Division by zero in grading") == "Division by zero in grading"


@pytest.mark.parametrize(
    "roll", ["2021UCS0042", "21BCS101", "CS2101", "102UCS", "21-BCS-101", "UCS-2021-0042"]
)
def test_scrub_text_removes_enrollment_numbers_with_letters(roll: str) -> None:
    assert scrub_text(f"no result for student {roll} in cohort") == "no result for student [id] in cohort"


@pytest.mark.parametrize(
    "kept",
    [
        "GET /api/v1/me/results stats",
        "retry 3 of 5 on worker-1",
        "exam held on 2026-10-14",
        "utf-8 decode failed",
        "HTTP 503 from storage",
        "S3 bucket unavailable",
    ],
)
def test_scrub_text_keeps_ordinary_words_numbers_and_dates(kept: str) -> None:
    assert scrub_text(kept) == kept


def _event() -> dict[str, Any]:
    return {
        "message": "Login failed for test.parent@example.com",
        "user": {"email": "test.parent@example.com", "ip_address": "10.0.0.1"},
        "extra": {"payload": {"marks": "45.5"}},
        "tags": {"component": "api", "student": "102401001"},
        "request": {
            "url": "https://demo.scorecode.test/api/v1/students/0192f1c6-3b6e-7a2c-9d1e-123456789abc?dob=2010-01-01",
            "query_string": "dob=2010-01-01",
            "cookies": {"sc_session": "abc"},
            "data": {"password": "hunter2-secret"},
            "headers": {
                "Cookie": "sc_session=abc",
                "Authorization": "Bearer x",
                "User-Agent": "Mozilla",
                "X-CSRF-Token": "t",
            },
            "env": {"REMOTE_ADDR": "10.0.0.1"},
        },
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": "bad mark 45.5 for 102401001",
                    "stacktrace": {
                        "frames": [{"filename": "x.py", "lineno": 3, "vars": {"password": "hunter2-secret"}}]
                    },
                }
            ]
        },
        "breadcrumbs": {
            "values": [
                {
                    "category": "httplib",
                    "data": {"url": "https://api.example.com/x?token=abc", "method": "GET", "body": "x"},
                },
                {"category": "log", "message": "sent to test.parent@example.com"},
            ]
        },
    }


def test_scrub_event_keeps_the_trace_and_drops_everything_personal() -> None:
    out = scrub_event(_event())
    assert out is not None
    text = json.dumps(out)
    for value in (*PERSONAL, "10.0.0.1", "dob=", "Bearer x", "hunter2"):
        assert value not in text, value
    assert out["request"]["url"] == "https://demo.scorecode.test/api/v1/students/[id]"
    assert out["request"]["headers"] == {"User-Agent": "Mozilla"}
    assert out["tags"] == {"component": "api"}
    frame = out["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert frame == {"filename": "x.py", "lineno": 3}
    assert out["exception"]["values"][0]["value"] == "bad mark [n] for [number]"
    crumbs = out["breadcrumbs"]["values"]
    assert crumbs[0]["data"] == {"method": "GET", "url": "https://api.example.com/x"}
    assert crumbs[1]["message"] == "sent to [email]"


def test_a_scrubber_failure_drops_the_event() -> None:
    assert (
        scrub_event(
            {"exception": {"values": [{"value": "x", "stacktrace": {"frames": "not-a-list-of-dicts"}}]}}
        )
        is None
    )
    assert scrub_breadcrumb({"message": object()}) is not None  # str() of anything is fine


class _Keep(Transport):
    def __init__(self, options: Any = None) -> None:
        super().__init__(options)
        self.items: list[bytes] = []

    def capture_envelope(self, envelope: Any) -> None:
        self.items.append(envelope.serialize())


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    keep = _Keep()
    real_init = sentry_sdk.init

    def init(*args: Any, **kwargs: Any) -> Any:
        return real_init(*args, **{**kwargs, "transport": keep})

    monkeypatch.setattr(sentry_sdk, "init", init)
    yield keep.items
    sentry_sdk.get_client().close()
    sentry_sdk.init()  # back to no client


def test_what_leaves_the_process_has_no_locals_no_personal_data_and_no_traces(sent: list[bytes]) -> None:
    settings = Settings(sentry_dsn="https://public@example.invalid/1", release="v1.2.3")  # type: ignore[arg-type]
    assert init_sentry(settings, "cli")

    def handler(pw: str = "hunter2-secret", email: str = "test.parent@example.com") -> None:
        raise RuntimeError(SENTRY_TEST)

    try:
        handler()
    except RuntimeError as exc:
        sentry_sdk.capture_exception(exc)
    sentry_sdk.flush(timeout=5)
    assert len(sent) == 1
    body = sent[0].decode()
    for value in (*PERSONAL, "hunter2"):
        assert value not in body, value
    event = json.loads(body.splitlines()[-1])
    assert event["environment"] == "development" and event["release"] == "v1.2.3"
    assert event["tags"]["component"] == "cli"
    assert "user" not in event and "extra" not in event
    frames = event["exception"]["values"][0]["stacktrace"]["frames"]
    assert frames and all(not ({"vars", "context_line", "pre_context"} & set(f)) for f in frames)
    assert frames[-1]["function"] == "handler" and frames[-1]["lineno"] > 0  # still a usable trace
    assert '"type":"event"' in body and '"type":"transaction"' not in body  # errors only
