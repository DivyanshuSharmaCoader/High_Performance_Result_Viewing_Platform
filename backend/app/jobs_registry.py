"""Imports every module that registers background job handlers."""

from __future__ import annotations


def load_job_handlers() -> None:
    from app.modules.notifications import emails  # noqa: F401
