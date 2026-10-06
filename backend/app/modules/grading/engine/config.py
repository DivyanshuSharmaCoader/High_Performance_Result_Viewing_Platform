"""Grading scheme configuration (stored as ``grading_scheme_versions.config``), validated before use.

Every config is explicit: rounding mode and places, pass rules, bands. Unknown keys are rejected, so a
typo can never silently change how results are computed.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP, Decimal
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=6, decimal_places=3)]
GradePoint = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
GradeLabel = Annotated[str, Field(min_length=1, max_length=8, pattern=r"^[A-Za-z0-9+\-]+$")]

ROUNDING = {"half_up": ROUND_HALF_UP, "half_even": ROUND_HALF_EVEN, "down": ROUND_DOWN, "up": ROUND_UP}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rounding(Strict):
    """How computed figures are rounded. ``half_up`` (0.5 → up) is what most marksheets expect."""

    mode: Literal["half_up", "half_even", "down", "up"] = "half_up"
    total_places: int = Field(default=2, ge=0, le=3)
    percentage_places: int = Field(default=2, ge=0, le=3)
    gpa_places: int = Field(default=2, ge=0, le=3)

    def q(self, value: Decimal, places: int) -> Decimal:
        return value.quantize(Decimal(1).scaleb(-places), rounding=ROUNDING[self.mode])


class PassRules(Strict):
    paper_pass_percentage: Percent | None = None  # used when a paper has no own pass total
    overall_pass_percentage: Percent | None = None
    require_all_papers: bool = True  # a single failed or absent paper fails the exam


class Band(Strict):
    grade: GradeLabel
    min_percentage: Percent  # inclusive lower bound, compared with the rounded percentage
    grade_point: GradePoint | None = None
    label: str | None = Field(default=None, max_length=40)


def _check_bands(bands: tuple[Band, ...]) -> None:
    if not bands:
        raise ValueError("Add at least one grade band.")
    mins = [b.min_percentage for b in bands]
    if any(a <= b for a, b in pairwise(mins)):
        raise ValueError("List bands from highest to lowest, each starting below the previous one.")
    if mins[-1] != 0:
        raise ValueError("The lowest band must start at 0% so every percentage gets a grade.")
    grades = [b.grade for b in bands]
    if len(set(grades)) != len(grades):
        raise ValueError("Each grade can appear only once.")


class _Common(Strict):
    rounding: Rounding = Rounding()
    pass_rules: PassRules = PassRules()
    absent_grade: GradeLabel | None = "AB"


class PercentageBandsConfig(_Common):
    """Percentage → grade bands (e.g. CBSE-style A1…E)."""

    strategy: Literal["percentage_bands"] = "percentage_bands"
    bands: tuple[Band, ...]
    fail_grade: GradeLabel | None = None  # shown for a failed paper/exam instead of its band grade

    @model_validator(mode="after")
    def _valid(self) -> Self:
        _check_bands(self.bands)
        return self


class CreditGpaConfig(_Common):
    """Credit-weighted grade points → SGPA (e.g. a 10-point CBCS-style scale)."""

    strategy: Literal["credit_gpa"] = "credit_gpa"
    bands: tuple[Band, ...]
    fail_grade: GradeLabel = "F"
    count_absent_as_attempted: bool = True  # an absent paper's credits count, with 0 points

    @model_validator(mode="after")
    def _valid(self) -> Self:
        _check_bands(self.bands)
        if any(b.grade_point is None for b in self.bands):
            raise ValueError("Every band needs grade points in a credit scheme.")
        points = [b.grade_point for b in self.bands]
        if any(a is not None and b is not None and a < b for a, b in pairwise(points)):
            raise ValueError("Grade points must not increase as percentages go down.")
        return self

    @property
    def max_grade_point(self) -> Decimal:
        return max(b.grade_point or Decimal(0) for b in self.bands)


class MarksOnlyConfig(_Common):
    """Totals and percentages only — typical for coaching tests, usually with ranks."""

    strategy: Literal["marks_only"] = "marks_only"
    ranking: Literal["none", "competition", "dense"] = "competition"


GradingConfig = Annotated[
    PercentageBandsConfig | CreditGpaConfig | MarksOnlyConfig, Field(discriminator="strategy")
]
