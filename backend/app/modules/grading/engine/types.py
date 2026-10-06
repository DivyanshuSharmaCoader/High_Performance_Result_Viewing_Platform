"""Inputs and outputs of the grading engine (docs/08 §7). Plain frozen dataclasses on ``Decimal``; no I/O."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class Attendance(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    EXEMPT = "exempt"
    MALPRACTICE = "malpractice"
    WITHHELD = "withheld"


class PaperOutcome(StrEnum):
    PASS = "pass"  # noqa: S105 - an outcome, not a password
    FAIL = "fail"
    ABSENT = "absent"
    EXEMPT = "exempt"  # excluded from every total
    WITHHELD = "withheld"  # result held back (withheld or malpractice)
    INCOMPLETE = "incomplete"  # marks missing


class ExamOutcome(StrEnum):
    PASS = "pass"  # noqa: S105 - an outcome, not a password
    FAIL = "fail"
    ABSENT = "absent"
    WITHHELD = "withheld"
    INCOMPLETE = "incomplete"


class GradingInputError(ValueError):
    """Marks that can't be graded (e.g. above the component maximum). Validation upstream should
    make this unreachable; the engine still refuses rather than produce a wrong result."""


@dataclass(frozen=True, slots=True)
class Component:
    code: str
    max: Decimal
    min_pass: Decimal | None = None
    label: str = ""


@dataclass(frozen=True, slots=True)
class PaperSpec:
    paper_id: str
    components: tuple[Component, ...]
    credits: Decimal | None = None
    pass_total: Decimal | None = None  # marks needed out of max_total, if the paper has a total rule
    title: str = ""

    @property
    def max_total(self) -> Decimal:
        return sum((c.max for c in self.components), Decimal(0))


@dataclass(frozen=True, slots=True)
class MarkInput:
    components: Mapping[str, Decimal | None]
    attendance: Attendance = Attendance.PRESENT


@dataclass(frozen=True, slots=True)
class PaperResult:
    paper_id: str
    outcome: PaperOutcome
    max_total: Decimal
    total: Decimal | None = None
    percentage: Decimal | None = None
    grade: str | None = None
    grade_point: Decimal | None = None
    credits: Decimal | None = None
    failed_components: tuple[str, ...] = ()
    missing_components: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.outcome is PaperOutcome.PASS


@dataclass(frozen=True, slots=True)
class ExamResult:
    outcome: ExamOutcome
    papers: tuple[PaperResult, ...]
    total: Decimal | None = None
    max_total: Decimal | None = None
    percentage: Decimal | None = None
    grade: str | None = None
    grade_point: Decimal | None = None  # average of paper grade points (band schemes that define them)
    sgpa: Decimal | None = None
    credits_attempted: Decimal | None = None
    credits_earned: Decimal | None = None
    notes: tuple[str, ...] = field(default=())
