"""Exam lifecycle (P7.5): every status × every action, checked against the state diagram."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import InvalidState, ValidationFailed
from app.modules.examinations.components import max_total, parse_components, to_json
from app.modules.examinations.states import ADMIN_ACTIONS, ExamAction, ExamStatus, available, transition_for

S, A = ExamStatus, ExamAction

# The state diagram (docs/diagrams/state-diagrams.md §1), written out independently of the code's table.
EXPECTED: dict[tuple[ExamStatus, ExamAction], ExamStatus] = {
    (S.DRAFT, A.OPEN_ENTRY): S.MARKS_ENTRY_OPEN,
    (S.MARKS_ENTRY_OPEN, A.CLOSE_ENTRY): S.MARKS_ENTRY_CLOSED,
    (S.MARKS_ENTRY_CLOSED, A.REOPEN_ENTRY): S.MARKS_ENTRY_OPEN,
    (S.MARKS_ENTRY_CLOSED, A.PROCESS): S.PROCESSED,
    (S.PROCESSED, A.PROCESS): S.PROCESSED,
    (S.PROCESSED, A.MARK_STALE): S.MARKS_ENTRY_CLOSED,
    (S.PROCESSED, A.APPROVE): S.APPROVED,
    (S.APPROVED, A.REVOKE_APPROVAL): S.PROCESSED,
    (S.APPROVED, A.SCHEDULE): S.SCHEDULED,
    (S.APPROVED, A.PUBLISH): S.PUBLISHED,
    (S.SCHEDULED, A.CANCEL_SCHEDULE): S.APPROVED,
    (S.SCHEDULED, A.PUBLISH): S.PUBLISHED,
    (S.PUBLISHED, A.START_CORRECTION): S.CORRECTION_DRAFT,
    (S.CORRECTION_DRAFT, A.PROCESS): S.PROCESSED,
    (S.CORRECTION_DRAFT, A.CANCEL_CORRECTION): S.PUBLISHED,
    (S.MARKS_ENTRY_OPEN, A.CANCEL_CORRECTION): S.PUBLISHED,
    (S.MARKS_ENTRY_CLOSED, A.CANCEL_CORRECTION): S.PUBLISHED,
    (S.PROCESSED, A.CANCEL_CORRECTION): S.PUBLISHED,
    (S.APPROVED, A.CANCEL_CORRECTION): S.PUBLISHED,
    (S.PUBLISHED, A.WITHDRAW): S.WITHDRAWN,
    (S.WITHDRAWN, A.REAPPROVE): S.APPROVED,
    (S.PUBLISHED, A.ARCHIVE): S.ARCHIVED,
}
NEEDS_REASON = {A.REOPEN_ENTRY, A.REVOKE_APPROVAL, A.START_CORRECTION, A.WITHDRAW}


@pytest.mark.parametrize("status", list(ExamStatus))
@pytest.mark.parametrize("action", list(ExamAction))
def test_every_status_and_action(status: ExamStatus, action: ExamAction) -> None:
    target = EXPECTED.get((status, action))
    if target is None:
        with pytest.raises(InvalidState):
            transition_for(status.value, action.value, "a good reason")
        return
    if action in NEEDS_REASON:
        with pytest.raises(ValidationFailed) as exc:
            transition_for(status.value, action.value, "  ")
        assert exc.value.extra["field"] == "reason"
    t = transition_for(status.value, action.value, "a good reason")
    assert t.target is target and t.needs_reason == (action in NEEDS_REASON)


def test_unknown_actions_and_admin_menu() -> None:
    with pytest.raises(ValidationFailed):
        transition_for("draft", "teleport", None)
    assert [t.action for t in available("draft")] == [A.OPEN_ENTRY]
    assert [t.action for t in available("marks_entry_closed")] == [A.REOPEN_ENTRY]  # processing comes later
    assert available("published") == []
    assert {t.action for s in ExamStatus for t in available(s.value)} == set(ADMIN_ACTIONS)


def test_every_status_is_reachable_from_draft() -> None:
    seen, frontier = {S.DRAFT}, [S.DRAFT]
    while frontier:
        current = frontier.pop()
        for (source, _action), target in EXPECTED.items():
            if source is current and target not in seen:
                seen.add(target)
                frontier.append(target)
    assert seen == set(ExamStatus)


# ---- paper components ---------------------------------------------------------------------------


def test_components_are_normalised_and_totalled() -> None:
    comps = parse_components(
        [
            {"code": " int ", "label": "Internal", "max": "40"},
            {"code": "ext", "label": "External", "max": "60", "min_pass": "21"},
        ]
    )
    assert [c.code for c in comps] == ["INT", "EXT"] and max_total(comps) == Decimal(100)
    assert to_json(comps)[1] == {"code": "EXT", "label": "External", "max": "60", "min_pass": "21"}


@pytest.mark.parametrize(
    ("components", "field", "message"),
    [
        ([], "components", "between 1 and 10"),
        ([{"code": "A", "label": "A", "max": "10"}] * 2, "components", "its own code"),
        ([{"code": "A-1", "label": "A", "max": "10"}], "components.0.code", "letters, digits or _"),
        ([{"code": "A", "label": "A", "max": "0"}], "components.0", "more than 0"),
        ([{"code": "A", "label": "A", "max": "10", "min_pass": "11"}], "components.0", "can't be more than"),
        ([{"code": "A", "label": "A", "max": "10.125"}], "components.0.max", "decimal places"),
        ([{"code": "A", "label": "A", "max": "10", "extra": 1}], "components.0.extra", "Extra inputs"),
    ],
)
def test_invalid_components(components: list[dict[str, object]], field: str, message: str) -> None:
    with pytest.raises(ValidationFailed) as exc:
        parse_components(components)  # type: ignore[arg-type]
    assert exc.value.extra["field"] == field and message in exc.value.detail
