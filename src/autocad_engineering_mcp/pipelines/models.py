"""Bounded pipeline requests, using drawing units directly rather than millimetres."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..core.models import Coordinate, Handle, Model, Name, Point

Color = Literal["red", "blue"]
ColorFilter = Literal["red", "blue", "all"]
Route = Annotated[list[Point], Field(min_length=2, max_length=2000)]
Continuation = Annotated[list[Point], Field(min_length=1, max_length=1998)]
Region = tuple[Coordinate, Coordinate, Coordinate, Coordinate]


def route_points(points):
    """Reject zero-length segments without rejecting nonadjacent repeated vertices."""
    if any(a == b for a, b in zip(points, points[1:], strict=False)):
        raise ValueError("Consecutive route points must differ")
    return points


class Create(Model):
    color: Color
    points: Route
    layer: Name | None = None
    allow_create_layer: bool = False

    @model_validator(mode="after")
    def validate_route(self):
        route_points(self.points)
        return self


class Modify(Model):
    handle: Handle
    points: Route

    @model_validator(mode="after")
    def validate_route(self):
        route_points(self.points)
        return self


class Move(Model):
    handle: Handle
    dx: Coordinate
    dy: Coordinate


class Extend(Model):
    handle: Handle
    endpoint: Literal["start", "end"]
    points: Continuation


class Delete(Model):
    handle: Handle
    confirm: bool = False


class Recolor(Model):
    handle: Handle
    color: Color


class SelectedMove(Model):
    dx: Coordinate
    dy: Coordinate
    confirm: bool = False


class SelectedColor(Model):
    color: Color
    confirm: bool = False


class Connect(Model):
    first_handle: Handle
    second_handle: Handle
    connection_point: Point
    color: Color
    first_endpoint: Literal["start", "end"] | None = None
    second_endpoint: Literal["start", "end"] | None = None
    allow_mixed_colors: bool = False
    layer: Name | None = None
    allow_create_layer: bool = False

    @model_validator(mode="after")
    def distinct_handles(self):
        if self.first_handle.upper() == self.second_handle.upper():
            raise ValueError("Select two different objects")
        return self


class Query(Model):
    color: ColorFilter = "all"
    layer: Name | None = None
    selection: Literal["all", "selected"] = "all"
    region: Region | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def ordered_region(self):
        if self.region and (self.region[0] > self.region[2] or self.region[1] > self.region[3]):
            raise ValueError("Region must be [xmin,ymin,xmax,ymax]")
        return self


class Analysis(Query):
    tolerance: float = Field(default=1, ge=0, le=1e9)
    max_pipelines: int = Field(default=500, ge=1, le=1000)


class Labels(Query):
    max_distance: float = Field(default=1000, ge=0, le=1e9)
    max_pipelines: int = Field(default=500, ge=1, le=1000)


class Nearby(Model):
    point: Point
    radius: float = Field(gt=0, le=1e9)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)
