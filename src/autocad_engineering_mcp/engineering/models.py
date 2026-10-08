"""Engineering parameters in millimetres; height is metadata, output is always 2D."""

import math
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, model_validator

from ..core.models import Coordinate, Model, Name, Point, Positive


def logical_point(values):
    if not isinstance(values, (list, tuple)) or len(values) not in {2, 3}:
        raise ValueError("Expected 2D/3D logical point")
    if any(not isinstance(v, (float, int)) or isinstance(v, bool) for v in values):
        raise ValueError("Coordinates must be numbers")
    if any(not math.isfinite(x) or abs(x) > 1e9 for x in values):
        raise ValueError("Invalid logical coordinates")
    return tuple(values) if len(values) == 3 else (*values, 0.0)


LogicalPoint = Annotated[
    tuple[Coordinate, Coordinate, Coordinate],
    BeforeValidator(
        logical_point,
        json_schema_input_type=tuple[Coordinate, Coordinate]
        | tuple[Coordinate, Coordinate, Coordinate],
    ),
]


class System(Model):
    name: Name
    discipline: Literal["hvac", "plumbing"]
    kind: Literal[
        "supply",
        "exhaust",
        "heating",
        "cold_water",
        "hot_water",
        "hot_water_return",
        "sanitary_sewer",
        "rainwater",
    ]
    projection: Literal["plan", "axonometric"] = "plan"

    @model_validator(mode="after")
    def discipline_kind(self):
        hvac = {"supply", "exhaust", "heating"}
        if (self.kind in hvac) != (self.discipline == "hvac"):
            raise ValueError("System kind does not match discipline")
        return self


class Duct(Model):
    system: Name
    points: list[Point] = Field(min_length=2, max_length=200)
    shape: Literal["rectangular", "round"] = "rectangular"
    width: Positive | None = None
    height: Positive | None = None
    diameter: Positive | None = None
    elevation: float = Field(default=0, allow_inf_nan=False, ge=-1e9, le=1e9)
    airflow: float | None = Field(default=None, ge=0, le=1e9, allow_inf_nan=False)
    mark: Name | None = None

    @model_validator(mode="after")
    def section(self):
        if self.shape == "rectangular":
            if self.width is None or self.height is None or self.diameter is not None:
                raise ValueError("Rectangular duct needs width/height only")
        elif self.diameter is None or self.width is not None or self.height is not None:
            raise ValueError("Round duct needs diameter only")
        if any(a == b for a, b in zip(self.points, self.points[1:], strict=False)):
            raise ValueError("Consecutive duct vertices must differ")
        return self


class Pipe(Model):
    system: Name
    points: list[LogicalPoint] = Field(min_length=2, max_length=200)
    diameter: Positive
    material: str = Field(default="unspecified", min_length=1, max_length=100)
    elevation: float = Field(default=0, allow_inf_nan=False, ge=-1e9, le=1e9)
    slope: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    direction: Literal["forward", "reverse"] = "forward"
    mark: Name | None = None

    @model_validator(mode="after")
    def route(self):
        if any(a == b for a, b in zip(self.points, self.points[1:], strict=False)):
            raise ValueError("Consecutive pipe vertices must differ")
        return self


class Equipment(Model):
    system: Name
    position: LogicalPoint
    mark: Name
    name: str = Field(default="", max_length=100)
    size: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=1000)
    rotation: float = Field(default=0, allow_inf_nan=False, ge=-1e6, le=1e6)


class Riser(Model):
    system: Name
    position: Point
    mark: Name
    diameter: Positive = 100
    elevation: float = Field(default=0, allow_inf_nan=False, ge=-1e9, le=1e9)
