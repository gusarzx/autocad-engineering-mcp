"""Coordinate transformations; explicit input units and WCS output."""

import math

from .exceptions import CadError

MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
INSUNITS = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}


def normalize(operation: dict, insunits: int) -> dict:
    """Convert length parameters to drawing units; reject ambiguous unitless DWGs."""
    data = dict(operation)
    source = data.pop("units", None)
    if source is None:
        return data
    if insunits not in INSUNITS:
        raise CadError("Set drawing INSUNITS to mm/cm/m/in/ft before creating geometry")
    factor = MM[source] / MM[INSUNITS[insunits]]
    for key in ("start", "end", "center", "position", "base", "target"):
        if key in data:
            data[key] = tuple(v * factor for v in data[key])
    if "points" in data:
        data["points"] = [tuple(v * factor for v in p) for p in data["points"]]
    for key in ("radius", "height", "width", "distance"):
        if key in data:
            data[key] *= factor
            if abs(data[key]) > 1e9:
                raise CadError("Converted dimension exceeds drawing coordinate budget")
    for key in ("start", "end", "center", "position", "base", "target"):
        if key in data and any(abs(v) > 1e9 for v in data[key]):
            raise CadError("Converted coordinate exceeds drawing coordinate budget")
    if "points" in data and any(abs(v) > 1e9 for p in data["points"] for v in p):
        raise CadError("Converted coordinate exceeds drawing coordinate budget")
    return data


def axonometric(point: tuple[float, float, float]) -> tuple[float, float, float]:
    """Isometric schematic projection, 30 degree axes, lengths expressed in mm."""
    x, y, z = point
    return ((x - y) * math.sqrt(3) / 2, (x + y) / 2 + z, 0.0)
