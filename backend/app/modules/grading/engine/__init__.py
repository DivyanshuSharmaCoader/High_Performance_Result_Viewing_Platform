"""ScoreCode grading engine: pure, deterministic, ``Decimal`` only (docs/08 §7).

    cfg = parse_config(version.config)
    result = grade_exam(papers, marks_by_paper_id, cfg)
    ranks = assign_ranks({student_id: result, ...}, "competition")

Nothing here performs I/O or imports the rest of the application; an import-linter contract keeps it
that way, so every rule can be tested exhaustively with plain unit and property tests.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Literal

from pydantic import TypeAdapter, ValidationError

from app.modules.grading.engine.config import (
    Band,
    CreditGpaConfig,
    GradingConfig,
    MarksOnlyConfig,
    PassRules,
    PercentageBandsConfig,
    Rounding,
)
from app.modules.grading.engine.strategies import REGISTRY, GradingStrategy
from app.modules.grading.engine.types import (
    Attendance,
    Component,
    ExamOutcome,
    ExamResult,
    GradingInputError,
    MarkInput,
    PaperOutcome,
    PaperResult,
    PaperSpec,
)

__all__ = [
    "REGISTRY",
    "Attendance",
    "Band",
    "Component",
    "CreditGpaConfig",
    "ExamOutcome",
    "ExamResult",
    "GradingConfig",
    "GradingConfigError",
    "GradingInputError",
    "GradingStrategy",
    "MarkInput",
    "MarksOnlyConfig",
    "PaperOutcome",
    "PaperResult",
    "PaperSpec",
    "PassRules",
    "PercentageBandsConfig",
    "Rounding",
    "assign_ranks",
    "grade_exam",
    "parse_config",
]

_ADAPTER: TypeAdapter[GradingConfig] = TypeAdapter(GradingConfig)
RANKED = (ExamOutcome.PASS, ExamOutcome.FAIL)


class GradingConfigError(ValueError):
    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        first = errors[0] if errors else {"msg": "Invalid grading configuration"}
        where = ".".join(
            str(p) for p in first.get("loc", ()) if p not in ("percentage_bands", "credit_gpa", "marks_only")
        )
        super().__init__(f"{where}: {first.get('msg')}" if where else str(first.get("msg")))


def parse_config(data: Mapping[str, Any]) -> GradingConfig:
    """Validate a stored/submitted config; the ``strategy`` key selects the schema."""
    if data.get("strategy") not in REGISTRY:
        raise GradingConfigError([{"loc": ("strategy",), "msg": "Choose a grading strategy."}])
    try:
        return _ADAPTER.validate_python(dict(data))
    except ValidationError as exc:
        raise GradingConfigError(
            [{"loc": e["loc"], "msg": str(e["msg"]).removeprefix("Value error, ")} for e in exc.errors()]
        ) from exc


def config_to_json(cfg: GradingConfig) -> dict[str, Any]:
    return cfg.model_dump(mode="json")


def grade_exam(
    papers: Sequence[PaperSpec], marks: Mapping[str, MarkInput | None], cfg: GradingConfig
) -> ExamResult:
    """Grade one student's exam. ``marks`` maps paper ids to inputs; a missing key means no marks."""
    strategy = REGISTRY[cfg.strategy]
    graded = tuple(strategy.grade_paper(p, marks.get(p.paper_id), cfg) for p in papers)
    return strategy.aggregate(graded, cfg)


def assign_ranks(
    results: Mapping[str, ExamResult], method: Literal["competition", "dense", "none"] = "competition"
) -> dict[str, int | None]:
    """Rank students by percentage, then total (both descending). Equal scores share a rank:
    ``competition`` gives 1, 2, 2, 4; ``dense`` gives 1, 2, 2, 3. Absent, withheld and incomplete
    results are not ranked. The output never depends on input order."""
    out: dict[str, int | None] = dict.fromkeys(results)
    if method == "none":
        return out
    ranked = sorted(
        ((k, r) for k, r in results.items() if r.outcome in RANKED and r.percentage is not None),
        key=lambda kr: (-(kr[1].percentage or Decimal(0)), -(kr[1].total or Decimal(0)), kr[0]),
    )
    previous: tuple[Decimal | None, Decimal | None] | None = None
    rank = 0
    for position, (key, r) in enumerate(ranked, start=1):
        score = (r.percentage, r.total)
        if score != previous:
            rank = position if method == "competition" else rank + 1
            previous = score
        out[key] = rank
    return out
