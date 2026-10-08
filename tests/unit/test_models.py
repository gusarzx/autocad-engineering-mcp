import math

import pytest
from pydantic import ValidationError

from autocad_engineering_mcp.config import Settings
from autocad_engineering_mcp.core.geometry import axonometric, normalize
from autocad_engineering_mcp.core.models import Arc, Batch, Circle, Line, Polyline, Result
from autocad_engineering_mcp.engineering.models import Duct, Pipe, System


@pytest.mark.parametrize("end", [[math.nan, 1], [math.inf, 0], [1e10, 0], [0, 0], [1, 2, 3], [1]])
def test_invalid_coordinates(end):
    with pytest.raises(ValidationError):
        Line(start=[0, 0], end=end)


def test_2d_normalized_and_unknown_keys_rejected():
    line = Line(start=[0, 0], end=[100, 20])
    assert line.start == (0, 0, 0)
    with pytest.raises(ValidationError):
        Line(start=[0, 0], end=[1, 0], command="erase")


@pytest.mark.parametrize(
    "points,closed",
    [([[0, 0], [0, 0]], False), ([[0, 0], [1, 1]], True), ([[0, 0], [2, 0, 3]], False)],
)
def test_invalid_polyline(points, closed):
    with pytest.raises(ValidationError):
        Polyline(points=points, closed=closed)


def test_invalid_circle_and_arc():
    with pytest.raises(ValidationError):
        Circle(center=[0, 0], radius=-10)
    with pytest.raises(ValidationError):
        Arc(center=[0, 0], radius=10, start_angle=0, end_angle=math.tau)


@pytest.mark.parametrize(
    "source,drawing,expected", [("m", 4, 1000), ("mm", 6, 0.001), ("in", 4, 25.4)]
)
def test_units(source, drawing, expected):
    op = normalize(Line(start=[0, 0], end=[1, 0], units=source).model_dump(), drawing)
    assert op["end"][0] == expected


def test_axonometry_is_2d():
    assert axonometric((0, 0, 500)) == (0, 500, 0)
    assert axonometric((100, 100, 0)) == (0, 100, 0)


@pytest.mark.parametrize(
    "data",
    [
        {"shape": "rectangular"},
        {"shape": "round", "width": 1},
        {"width": 500, "height": 300, "diameter": 20},
        {"width": -1, "height": 10},
    ],
)
def test_duct_section_rejected(data):
    with pytest.raises(ValidationError):
        Duct(system="P1", points=[[0, 0], [10, 0]], **data)


def test_pipe_models_and_system_discipline():
    for params in (
        {"diameter": 0},
        {"diameter": 100, "slope": -0.1},
        {"diameter": 100, "slope": math.nan},
    ):
        with pytest.raises(ValidationError):
            Pipe(system="W1", points=[[0, 0], [10, 0]], **params)
    with pytest.raises(ValidationError):
        System(name="W1", discipline="hvac", kind="cold_water")
    assert Pipe(system="W1", points=[[0, 0, 100], [10, 0, 100]], diameter=50).points[0][2] == 100


def test_configuration_and_unknown_batch_operations():
    with pytest.raises(ValidationError):
        Settings(max_batch=0)
    with pytest.raises(ValidationError):
        Batch(operations=[{"type": "send_command", "command": "ERASE"}])
    assert (
        Result.model_validate_json(Result(object_ids=["A"], count=1).model_dump_json()).count == 1
    )
