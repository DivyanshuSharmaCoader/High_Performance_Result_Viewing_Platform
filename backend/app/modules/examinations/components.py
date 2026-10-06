"""Paper components (docs/07 §2.5): e.g. Internal 40 + External 60 with a 21-mark minimum in External.

Stored on ``exam_papers.components`` as JSON with decimal strings, so values never pass through floats.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from app.core.errors import ValidationFailed

Marks = Annotated[Decimal, Field(ge=0, le=1000, max_digits=6, decimal_places=2)]


class ComponentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=12)
    label: str = Field(min_length=1, max_length=40)
    max: Marks
    min_pass: Marks | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        code = v.strip().upper()
        if not code.replace("_", "").isalnum() or not code.isascii():
            raise ValueError("Use letters, digits or _ for component codes (e.g. INT, EXT).")
        return code

    @model_validator(mode="after")
    def _limits(self) -> ComponentSpec:
        if self.max <= 0:
            raise ValueError("Maximum marks must be more than 0.")
        if self.min_pass is not None and self.min_pass > self.max:
            raise ValueError(f"The minimum to pass {self.code} can't be more than its maximum.")
        return self


_LIST = TypeAdapter(list[ComponentSpec])


def parse_components(raw: list[dict[str, Any]]) -> list[ComponentSpec]:
    try:
        comps = _LIST.validate_python(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise ValidationFailed(
            str(first["msg"]).removeprefix("Value error, "),
            field=f"components.{where}" if where else "components",
        ) from exc
    if not 1 <= len(comps) <= 10:
        raise ValidationFailed("A paper needs between 1 and 10 components.", field="components")
    codes = [c.code for c in comps]
    if len(set(codes)) != len(codes):
        raise ValidationFailed("Each component needs its own code.", field="components")
    return comps


def to_json(comps: list[ComponentSpec]) -> list[dict[str, Any]]:
    return [
        {
            "code": c.code,
            "label": c.label,
            "max": str(c.max),
            "min_pass": str(c.min_pass) if c.min_pass is not None else None,
        }
        for c in comps
    ]


def max_total(comps: list[ComponentSpec]) -> Decimal:
    return sum((c.max for c in comps), Decimal(0))
