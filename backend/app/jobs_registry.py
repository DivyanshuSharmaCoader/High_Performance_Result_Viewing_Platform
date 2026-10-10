"""Imports every module that registers background job handlers."""

from __future__ import annotations


def load_job_handlers() -> None:
    from app.modules.documents import jobs as _documents  # noqa: F401
    from app.modules.entitlements import trial as _trials  # noqa: F401
    from app.modules.exports import jobs as _exports  # noqa: F401
    from app.modules.ingestion import jobs as _imports  # noqa: F401
    from app.modules.notifications import emails  # noqa: F401
    from app.modules.notifications import jobs as _notifications  # noqa: F401
    from app.modules.publishing import jobs as _publishing  # noqa: F401
    from app.modules.results import jobs as _results  # noqa: F401
