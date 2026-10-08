"""One /metrics for every API worker process (docs/14 §Q): counters from all processes are summed, so a
scrape that reaches any worker reports the same totals."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import metrics

BACKEND = Path(__file__).resolve().parents[2]
COUNT = "from app.core.metrics import HTTP_REQUESTS; HTTP_REQUESTS.labels('student_read', 'GET', '200').inc()"
RENDER = "import sys; from app.core.metrics import render; sys.stdout.write(render().decode())"


def _run(code: str, directory: Path) -> str:
    env = {**os.environ, metrics.MULTIPROC_ENV: str(directory)}
    done = subprocess.run(  # noqa: S603 - our own interpreter and code
        [sys.executable, "-c", code], env=env, cwd=BACKEND, capture_output=True, text=True, check=True
    )
    return done.stdout


def test_requests_counted_in_two_worker_processes_are_reported_together(tmp_path: Path) -> None:
    _run(COUNT, tmp_path)
    _run(COUNT, tmp_path)
    out = _run(RENDER, tmp_path)
    assert 'scorecode_http_requests_total{method="GET",route_class="student_read",status="200"} 2.0' in out


def test_the_api_starts_its_workers_with_a_fresh_shared_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import uvicorn

    from app import cli

    directory = tmp_path / "metrics"
    directory.mkdir()
    (directory / "counter_123.db").write_bytes(b"left over from the last run")
    monkeypatch.setenv(metrics.MULTIPROC_ENV, str(directory))
    started: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: started.update(kw))
    cli.cmd_api(argparse.Namespace(host="127.0.0.1", port=8000, workers=2, reload=False))
    assert started["workers"] == 2
    assert directory.is_dir() and list(directory.iterdir()) == []  # stale samples never added in
    assert os.environ[metrics.MULTIPROC_ENV] == str(directory)


def test_a_single_process_api_keeps_plain_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    from app import cli

    monkeypatch.delenv(metrics.MULTIPROC_ENV, raising=False)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: None)
    cli.cmd_api(argparse.Namespace(host="127.0.0.1", port=8000, workers=1, reload=False))
    assert metrics.MULTIPROC_ENV not in os.environ
    assert b"scorecode_http_requests_total" in metrics.render()
