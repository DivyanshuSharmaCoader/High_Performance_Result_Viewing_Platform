"""Onboarding checklist (docs/03 W2, P4.6) — computed from data, never stored as flags.

Each module registers the steps it owns; the checklist simply evaluates them in order. A step is done
when the underlying data exists, so the list stays truthful if data is later removed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import func, select

from app.core.db import UnitOfWork
from app.modules.branding.models import TenantBranding
from app.modules.identity.models import User
from app.modules.tenancy.models import TenantSettings


@dataclass(frozen=True)
class StepResult:
    done: bool
    detail: str | None = None


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    description: str
    href: str
    required_for_publishing: bool
    order: int
    check: Callable[[UnitOfWork], Awaitable[StepResult]]


_steps: dict[str, Step] = {}


def register_step(step: Step) -> None:
    _steps[step.key] = step


def steps() -> list[Step]:
    return sorted(_steps.values(), key=lambda s: s.order)


async def _profile(uow: UnitOfWork) -> StepResult:
    s = (await uow.session.scalars(select(TenantSettings))).one()
    done = bool(s.address and s.contact_email)
    return StepResult(
        done, None if done else "Add your address and contact email — they appear on marksheets."
    )


async def _logo(uow: UnitOfWork) -> StepResult:
    b = (await uow.session.scalars(select(TenantBranding))).one()
    return StepResult(b.logo_file_id is not None)


async def _staff(uow: UnitOfWork) -> StepResult:
    n = (
        await uow.session.execute(select(func.count()).select_from(User).where(User.kind == "staff"))
    ).scalar_one()
    return StepResult(n > 1, f"{n} staff account{'s' if n != 1 else ''}")


register_step(
    Step(
        "profile",
        "Complete your institution profile",
        "Official name, address and contact details used on marksheets.",
        "/admin/settings",
        True,
        10,
        _profile,
    )
)
register_step(
    Step(
        "logo",
        "Upload your logo",
        "Shown on the portal, emails and marksheets.",
        "/admin/settings/branding",
        False,
        20,
        _logo,
    )
)
register_step(
    Step(
        "staff",
        "Invite your team",
        "Add administrators and faculty who enter marks.",
        "/admin/staff",
        False,
        30,
        _staff,
    )
)
