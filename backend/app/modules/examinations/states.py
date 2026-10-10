"""Examination lifecycle (docs/diagrams/state-diagrams.md §1) as data.

Every allowed move is one row of ``TRANSITIONS``; anything else is refused. Admin-facing actions are
exposed by the exams API now; processing, approval and publication actions are performed by the result
and publishing services in later phases through the same table, so the rules live in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.errors import InvalidState, ValidationFailed


class ExamStatus(StrEnum):
    DRAFT = "draft"
    MARKS_ENTRY_OPEN = "marks_entry_open"
    MARKS_ENTRY_CLOSED = "marks_entry_closed"
    PROCESSED = "processed"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    CORRECTION_DRAFT = "correction_draft"
    WITHDRAWN = "withdrawn"
    ARCHIVED = "archived"


class ExamAction(StrEnum):
    OPEN_ENTRY = "open_entry"
    CLOSE_ENTRY = "close_entry"
    REOPEN_ENTRY = "reopen_entry"
    PROCESS = "process"
    MARK_STALE = "mark_stale"
    APPROVE = "approve"
    REVOKE_APPROVAL = "revoke_approval"
    SCHEDULE = "schedule"
    CANCEL_SCHEDULE = "cancel_schedule"
    PUBLISH = "publish"
    START_CORRECTION = "start_correction"
    CANCEL_CORRECTION = "cancel_correction"
    WITHDRAW = "withdraw"
    REAPPROVE = "reapprove"
    ARCHIVE = "archive"


# Actions an administrator triggers directly from the exams API (the rest belong to later services).
ADMIN_ACTIONS = frozenset({ExamAction.OPEN_ENTRY, ExamAction.CLOSE_ENTRY, ExamAction.REOPEN_ENTRY})


@dataclass(frozen=True)
class Transition:
    source: ExamStatus
    action: ExamAction
    target: ExamStatus
    needs_reason: bool = False
    label: str = ""


S, A = ExamStatus, ExamAction
TRANSITIONS: tuple[Transition, ...] = (
    Transition(S.DRAFT, A.OPEN_ENTRY, S.MARKS_ENTRY_OPEN, label="Open marks entry"),
    Transition(S.MARKS_ENTRY_OPEN, A.CLOSE_ENTRY, S.MARKS_ENTRY_CLOSED, label="Close marks entry"),
    Transition(
        S.MARKS_ENTRY_CLOSED,
        A.REOPEN_ENTRY,
        S.MARKS_ENTRY_OPEN,
        needs_reason=True,
        label="Reopen marks entry",
    ),
    Transition(S.MARKS_ENTRY_CLOSED, A.PROCESS, S.PROCESSED, label="Process results"),
    Transition(S.PROCESSED, A.PROCESS, S.PROCESSED, label="Process again"),
    Transition(S.PROCESSED, A.MARK_STALE, S.MARKS_ENTRY_CLOSED, label="Marks changed"),
    Transition(S.PROCESSED, A.APPROVE, S.APPROVED, label="Approve results"),
    Transition(S.APPROVED, A.REVOKE_APPROVAL, S.PROCESSED, needs_reason=True, label="Revoke approval"),
    Transition(S.APPROVED, A.SCHEDULE, S.SCHEDULED, label="Schedule publication"),
    Transition(S.APPROVED, A.PUBLISH, S.PUBLISHED, label="Publish now"),
    Transition(S.SCHEDULED, A.CANCEL_SCHEDULE, S.APPROVED, label="Cancel schedule"),
    Transition(S.SCHEDULED, A.PUBLISH, S.PUBLISHED, label="Publish (scheduled time)"),
    Transition(
        S.PUBLISHED, A.START_CORRECTION, S.CORRECTION_DRAFT, needs_reason=True, label="Start correction"
    ),
    Transition(S.CORRECTION_DRAFT, A.PROCESS, S.PROCESSED, label="Process corrected marks"),
    # Cancelling a correction returns to the live version from any step of the correction. The publishing
    # service allows it only while a correction is in progress and no mark has changed.
    *(
        Transition(src, A.CANCEL_CORRECTION, S.PUBLISHED, label="Cancel the correction")
        for src in (S.CORRECTION_DRAFT, S.MARKS_ENTRY_OPEN, S.MARKS_ENTRY_CLOSED, S.PROCESSED, S.APPROVED)
    ),
    Transition(S.PUBLISHED, A.WITHDRAW, S.WITHDRAWN, needs_reason=True, label="Withdraw results"),
    Transition(S.WITHDRAWN, A.REAPPROVE, S.APPROVED, label="Approve again"),
    Transition(S.PUBLISHED, A.ARCHIVE, S.ARCHIVED, label="Archive"),
)

_BY_KEY = {(t.source, t.action): t for t in TRANSITIONS}
if len(_BY_KEY) != len(TRANSITIONS):  # pragma: no cover - a programming error caught at import
    raise RuntimeError("duplicate exam transition")

# States in which the exam's setup (papers, components, cohorts added) may still change.
SETUP_EDITABLE = frozenset({S.DRAFT, S.MARKS_ENTRY_OPEN, S.MARKS_ENTRY_CLOSED})


def transition_for(current: str, action: str, reason: str | None) -> Transition:
    try:
        source, act = ExamStatus(current), ExamAction(action)
    except ValueError as exc:
        raise ValidationFailed("Unknown exam action.", field="action") from exc
    t = _BY_KEY.get((source, act))
    if t is None:
        raise InvalidState(
            f"This exam is {source.value.replace('_', ' ')}; it can't “{act.value.replace('_', ' ')}” now."
        )
    if t.needs_reason and len((reason or "").strip()) < 3:
        raise ValidationFailed("Give a reason; it is recorded in the audit log.", field="reason")
    return t


def available(current: str) -> list[Transition]:
    """Admin actions available from ``current`` (what the UI offers)."""
    return [t for t in TRANSITIONS if t.source.value == current and t.action in ADMIN_ACTIONS]
