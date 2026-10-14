"""The operator's production checks (P18.10): `scorecode storage-test` and `scorecode email-test`, which
`scorecode-ctl` runs inside the API container on the server."""

from __future__ import annotations

import argparse
import asyncio
import io
import uuid

import pytest

from tests.helpers import mailpit_latest

pytestmark = pytest.mark.integration


async def test_storage_test_writes_links_refuses_unsigned_and_deletes(infra, monkeypatch, capsys) -> None:
    from app import cli

    monkeypatch.setattr(cli, "get_settings", lambda: infra.settings)
    await asyncio.to_thread(cli.cmd_storage_test, argparse.Namespace())
    out = capsys.readouterr().out
    for line in (
        "write",
        "read back",
        "signed link",
        "unsigned link refused",
        "tampered link refused",
        "delete",
    ):
        assert f"ok   {line}" in out, out
    assert "http" not in out.lower().replace("http 2", "").replace("http 4", "")  # no URLs printed


async def test_email_test_sends_one_message_to_the_address_on_stdin(infra, monkeypatch, capsys) -> None:
    from app import cli

    to = f"ops-{uuid.uuid4().hex[:8]}@example.org"
    monkeypatch.setattr(cli, "get_settings", lambda: infra.settings)
    monkeypatch.setattr("sys.stdin", io.StringIO(to + "\n"))
    await asyncio.to_thread(cli.cmd_email_test, argparse.Namespace())
    assert "accepted by the SMTP provider" in capsys.readouterr().out
    assert (await mailpit_latest(to))["subject"] == "ScoreCode email test"
    monkeypatch.setattr("sys.stdin", io.StringIO("not-an-address\n"))
    with pytest.raises(SystemExit):
        await asyncio.to_thread(cli.cmd_email_test, argparse.Namespace())
