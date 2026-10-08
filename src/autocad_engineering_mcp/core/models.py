"""Strict bounded operation models shared by tools, batch and both adapters."""

import math
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter, model_validator


def finite_point(value: tuple[float, ...]) -> tuple[float, float, float]:
    """Accept 2D/3D finite points, normalize to WCS triples."""
    if not isinstance(value, (list, tuple)) or len(value) not in {2, 3}:
        raise ValueError("Expected a 2D point")
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in value):
        raise ValueError("Coordinates must be numbers")
    if any(not math.isfinite(v) or abs(v) > 1e9 for v in value):
        raise ValueError("Coordinates must be finite and within +/-1e9")
    if len(value) == 3 and value[2] != 0:
        raise ValueError("Only 2D drawings: CAD coordinates must have z=0")
    return (value[0], value[1], value[2] if len(value) == 3 else 0.0)


Coordinate = Annotated[float, Field(ge=-1e9, le=1e9, allow_inf_nan=False)]
Point = Annotated[
    tuple[Coordinate, Coordinate, Literal[0.0]],
    BeforeValidator(
        finite_point,
        json_schema_input_type=tuple[Coordinate, Coordinate]
        | tuple[Coordinate, Coordinate, Literal[0.0]],
    ),
]
Name = Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[^<>/\\":;?*|=,`]+$')]
Handle = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[0-9A-Fa-f]+$")]
Positive = Annotated[float, Field(gt=0, le=1e9, allow_inf_nan=False)]
Angle = Annotated[float, Field(allow_inf_nan=False, ge=-1e6, le=1e6)]
Units = Literal["mm", "cm", "m", "in", "ft"]
Points = Annotated[list[Point], Field(min_length=2, max_length=1000)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Result(Model):
    """Common MCP response envelope; handles are scoped to one DWG."""

    status: Literal["ok", "error", "dry_run"] = "ok"
    object_ids: list[str] = Field(default_factory=list)
    count: int = 0
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class Drawing(Model):
    layer: Name = "0"
    units: Units = "mm"


class Line(Drawing):
    type: Literal["draw_line"] = "draw_line"
    start: Point
    end: Point

    @model_validator(mode="after")
    def nonzero(self):
        if self.start == self.end:
            raise ValueError("Line endpoints must differ")
        return self


class Polyline(Drawing):
    type: Literal["draw_polyline"] = "draw_polyline"
    points: Points
    closed: bool = False

    @model_validator(mode="after")
    def planar(self):
        if len(set(self.points)) < (3 if self.closed else 2):
            raise ValueError("Not enough distinct vertices")
        if len({p[2] for p in self.points}) != 1:
            raise ValueError("Lightweight polyline requires a constant WCS elevation")
        if any(a == b for a, b in zip(self.points, self.points[1:], strict=False)):
            raise ValueError("Consecutive vertices must differ")
        return self


class Circle(Drawing):
    type: Literal["draw_circle"] = "draw_circle"
    center: Point
    radius: Positive


class Arc(Circle):
    type: Literal["draw_arc"] = "draw_arc"
    start_angle: Angle
    end_angle: Angle

    @model_validator(mode="after")
    def sweep(self):
        if math.isclose((self.end_angle - self.start_angle) % (2 * math.pi), 0):
            raise ValueError("Arc sweep must be nonzero; use circle for a full revolution")
        return self


class Text(Drawing):
    type: Literal["draw_text"] = "draw_text"
    text: str = Field(min_length=1, max_length=4000)
    position: Point
    height: Positive = 150
    rotation: Angle = 0


class MText(Text):
    type: Literal["draw_mtext"] = "draw_mtext"
    width: Positive = 2000


class Dimension(Drawing):
    type: Literal["draw_dimension"] = "draw_dimension"
    start: Point
    end: Point
    position: Point

    @model_validator(mode="after")
    def nonzero(self):
        if self.start == self.end:
            raise ValueError("Dimension endpoints must differ")
        return self


class Spline(Drawing):
    type: Literal["draw_spline"] = "draw_spline"
    points: list[Point] = Field(min_length=3, max_length=200)

    @model_validator(mode="after")
    def distinct(self):
        if any(a == b for a, b in zip(self.points, self.points[1:], strict=False)):
            raise ValueError("Consecutive spline fit points must differ")
        return self


class Hatch(Drawing):
    type: Literal["draw_hatch"] = "draw_hatch"
    boundary_ids: list[Handle] = Field(min_length=1, max_length=20)
    pattern: Literal["SOLID", "ANSI31"] = "SOLID"
    scale: Positive = 1


class Layer(Model):
    type: Literal["create_layer"] = "create_layer"
    name: Name
    color: int = Field(default=7, ge=1, le=255)
    linetype: Name = "Continuous"
    lineweight: Literal[
        -3,
        -2,
        -1,
        0,
        5,
        9,
        13,
        15,
        18,
        20,
        25,
        30,
        35,
        40,
        50,
        53,
        60,
        70,
        80,
        90,
        100,
        106,
        120,
        140,
        158,
        200,
        211,
    ] = -3


class Block(Model):
    type: Literal["create_block"] = "create_block"
    name: Name
    width: Positive = 600
    height: Positive = 400
    tags: list[Literal["MARK", "NAME", "TYPE", "SIZE", "SYSTEM", "DESCRIPTION"]] = Field(
        default_factory=lambda: ["MARK", "NAME", "TYPE", "SIZE", "SYSTEM", "DESCRIPTION"],
        max_length=6,
    )


class InsertBlock(Drawing):
    type: Literal["insert_block"] = "insert_block"
    name: str = Field(min_length=1, max_length=1024)
    position: Point
    scale: Positive = 1
    rotation: Angle = 0
    attributes: dict[str, str] = Field(default_factory=dict, max_length=6)

    @model_validator(mode="after")
    def bounded_attributes(self):
        allowed = {"MARK", "NAME", "TYPE", "SIZE", "SYSTEM", "DESCRIPTION"}
        if any(k not in allowed or len(v) > 1000 for k, v in self.attributes.items()):
            raise ValueError("Use standard attribute tags with values up to 1000 characters")
        return self


Creation = Annotated[
    Line
    | Polyline
    | Circle
    | Arc
    | Text
    | MText
    | Dimension
    | Spline
    | Hatch
    | Layer
    | Block
    | InsertBlock,
    Field(discriminator="type"),
]
CREATION_ADAPTER = TypeAdapter(Creation)


class Batch(Model):
    operations: list[Creation] = Field(min_length=1, max_length=500)
    dry_run: bool = True
    rollback_on_error: bool = True


class Transform(Model):
    type: Literal["move", "copy", "rotate", "scale", "delete", "offset", "mirror"]
    object_ids: list[Handle] = Field(min_length=1, max_length=1000)
    base: Point = (0, 0, 0)
    target: Point = (0, 0, 0)
    angle: Angle = 0
    factor: Positive = 1
    distance: float = Field(default=1, allow_inf_nan=False)
    confirm: bool = False
    units: Units = "mm"

    @model_validator(mode="after")
    def geometry(self):
        if len(set(self.object_ids)) != len(self.object_ids):
            raise ValueError("Duplicate object handles")
        if self.type == "mirror" and self.base == self.target:
            raise ValueError("Mirror axis needs two distinct points")
        if self.type == "offset" and self.distance == 0:
            raise ValueError("Offset distance cannot be zero")
        return self
