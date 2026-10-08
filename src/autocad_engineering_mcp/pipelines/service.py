"""Colour candidate workflows sharing the existing CAD lock, envelope and STA adapter."""

import math
from functools import wraps

from pydantic import TypeAdapter, ValidationError

from ..core.exceptions import CadError
from ..core.models import Point, Result
from . import models
from .common import editable
from .geometry import cross, same, sub

POINT_ADAPTER = TypeAdapter(Point)


def workflow(function):
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        with self.cad.lock:
            try:
                return self.cad.bound(function(self, *args, **kwargs))
            except (CadError, ValidationError, OSError) as exc:
                return Result(status="error", error=str(exc))

    return wrapped


class PipelineService:
    def __init__(self, cad):
        self.cad = cad

    def page_args(self, request):
        if request.limit > self.cad.settings.page_size:
            raise CadError("Pagination exceeds ACAD_MCP_PAGE_SIZE")
        return {**request.model_dump(), "scan_limit": self.cad.settings.scan_limit}

    @workflow
    def query(self, **kwargs):
        request = models.Query.model_validate(kwargs)
        result = self.cad.require("pipeline_query", **self.page_args(request))
        result.count = len(result.data["pipelines"])
        if request.selection == "selected" and not result.count and "message" not in result.data:
            result.data["message"] = (
                "No matching red/blue pipeline candidates in this selection page"
            )
        result.warnings.append(
            "Colour matches are candidates, not confirmed pipes; units are drawing units"
        )
        return result

    def collect(self, request, maximum=500):
        """Bound total scan and vertices across pages; never silently return partial analysis."""
        pipes, offset, document = [], 0, None
        while True:
            query = models.Query(
                color=request.color,
                layer=request.layer,
                selection=request.selection,
                region=request.region,
                offset=offset,
                limit=min(100, self.cad.settings.page_size),
            )
            result = self.cad.require("pipeline_query", **self.page_args(query))
            document = document or result.data["document_id"]
            if document != result.data["document_id"]:
                raise CadError("Active document changed during scan")
            if result.data["unsupported_count"]:
                raise CadError(
                    "Analysis includes unsupported geometry; narrow selection/layer/region. "
                    + "; ".join(result.data["unsupported_examples"])
                )
            pipes.extend(result.data["pipelines"])
            if len(pipes) > maximum or sum(len(p["vertices"]) for p in pipes) > 20000:
                raise CadError("Candidate/vertex budget exceeded; narrow selection/layer/region")
            offset = result.data["next_offset"]
            if offset is None:
                return pipes, document, result.data["insunits"]
            if offset >= self.cad.settings.scan_limit:
                raise CadError(
                    "Total drawing scan budget exceeded; narrow selection or raise scan_limit"
                )

    def read(self, handle):
        return self.cad.require("pipeline_get", handle=handle.upper()).data

    def plan(self, action, pipes=(), document=None, **kwargs):
        return {
            "action": action,
            "handles": [p["handle"] for p in pipes],
            "expected": {p["handle"]: p["stamp"] for p in pipes},
            "expected_document": document,
            "max_change": self.cad.settings.max_change,
            "confirm": False,
            **kwargs,
        }

    def apply(self, plan, dry_run):
        if dry_run:
            return Result(
                status="dry_run",
                data={"plan": plan, "units": "drawing_units"},
                warnings=["Read-only preflight; COM-specific failures remain possible"],
            )
        return self.cad.call("pipeline_mutate", **plan)

    def destination(self, color, layer, allow):
        name = layer or f"MCP_PIPE_{color.upper()}"
        info = self.cad.require("pipeline_layer", name=name).data
        if info["locked"] or info["is_xref"]:
            raise CadError("Destination layer is locked or XREF-dependent")
        if not info["exists"] and layer is not None and not allow:
            raise CadError("Missing named layer requires allow_create_layer=true")
        return {"layer": name, "create_layer": not info["exists"], "color": color}

    @workflow
    def create(self, request, dry_run=False):
        document = self.cad.require("active_document").data["document_id"]
        return self.apply(
            self.plan(
                "create",
                document=document,
                points=request.points,
                **self.destination(request.color, request.layer, request.allow_create_layer),
            ),
            dry_run,
        )

    @staticmethod
    def route(pipe, points):
        editable(pipe, geometry_change=True)
        points = [POINT_ADAPTER.validate_python(p) for p in points]
        models.route_points(points)
        if not 2 <= len(points) <= 2000:
            raise CadError("Route must contain 2..2000 vertices")
        if pipe["type"] == "LINE" and len(points) != 2:
            raise CadError("A LINE must retain two endpoints; a bent route requires a polyline")
        if any(pipe["bulges"]):
            raise CadError(
                "Route editing of arc segments is unsupported; move/recolour preserves arcs"
            )
        if pipe["closed"] and (len(set(points)) < 3 or same(points[0], points[-1])):
            raise CadError(
                "Closed route requires three distinct vertices, without repeating the first"
            )
        if len(points) != len(pipe["vertices"]) and len({tuple(w) for w in pipe["widths"]}) > 1:
            raise CadError("Vertex count change would lose varying segment widths")
        return points

    @workflow
    def modify(self, request, dry_run=False):
        data = self.read(request.handle)
        pipe = data["pipeline"]
        points = self.route(pipe, request.points)
        return self.apply(self.plan("modify", [pipe], data["document_id"], points=points), dry_run)

    @workflow
    def extend(self, request, dry_run=False):
        data = self.read(request.handle)
        pipe = data["pipeline"]
        if pipe["closed"]:
            raise CadError("Closed pipelines have no extendable ends")
        extra = list(request.points)
        if same(extra[0], pipe[request.endpoint]):
            extra = extra[1:]
        if not extra:
            raise CadError("Continuation adds no new points")
        if pipe["type"] == "LINE":
            end = pipe[request.endpoint]
            other = pipe["end" if request.endpoint == "start" else "start"]
            direction = sub(end, other)
            previous = end
            for point in extra:
                delta = sub(point, previous)
                if (
                    abs(cross(direction, delta)) > 1e-9
                    or sum(a * b for a, b in zip(direction, delta, strict=True)) <= 0
                ):
                    raise CadError(
                        "A LINE can only extend straight outward; bends require a polyline"
                    )
                previous = point
            points = (
                [extra[-1], pipe["end"]]
                if request.endpoint == "start"
                else [pipe["start"], extra[-1]]
            )
        else:
            points = (
                list(reversed(extra)) + pipe["vertices"]
                if request.endpoint == "start"
                else pipe["vertices"] + extra
            )
        points = self.route(pipe, points)
        return self.apply(self.plan("modify", [pipe], data["document_id"], points=points), dry_run)

    @workflow
    def mutate(self, request, action, dry_run=False, selected=False):
        if selected:
            pipes, document, _ = self.collect(models.Query(selection="selected"), maximum=1000)
            if not pipes:
                raise CadError(
                    "No red/blue pipeline candidates preselected; select objects in AutoCAD first"
                )
        else:
            data = self.read(request.handle)
            pipes, document = [data["pipeline"]], data["document_id"]
        confirm = getattr(request, "confirm", False)
        if (
            not dry_run
            and (action == "delete" or len(pipes) > self.cad.settings.max_change)
            and not confirm
        ):
            raise CadError("Deletion/mass modification requires confirm=true")
        for pipe in pipes:
            editable(pipe, geometry_change=action == "move")
            if action == "delete" and pipe["engineering_metadata"]:
                raise CadError(
                    "Linked engineering elements cannot be deleted through candidate tools"
                )
            if action == "move":
                for point in pipe["vertices"]:
                    POINT_ADAPTER.validate_python([point[0] + request.dx, point[1] + request.dy])
        arguments = request.model_dump(exclude={"handle", "confirm"})
        return self.apply(self.plan(action, pipes, document, confirm=confirm, **arguments), dry_run)

    @workflow
    def connect(self, request, dry_run=False):
        first, second = self.read(request.first_handle), self.read(request.second_handle)
        if first["document_id"] != second["document_id"]:
            raise CadError("Active document changed during connection preflight")
        pipes = [first["pipeline"], second["pipeline"]]
        endpoints = []
        for pipe, selected in zip(
            pipes, [request.first_endpoint, request.second_endpoint], strict=True
        ):
            editable(pipe)
            if pipe["closed"]:
                raise CadError("Closed pipelines have no connection endpoints")
            if pipe["color"] != request.color and not request.allow_mixed_colors:
                raise CadError("Mixed colours require allow_mixed_colors=true")
            distances = {
                end: math.dist(pipe[end], request.connection_point[:2]) for end in ("start", "end")
            }
            if selected is None:
                if distances["start"] == distances["end"]:
                    raise CadError("Ambiguous connection: specify first_endpoint/second_endpoint")
                selected = min(distances, key=distances.get)
            endpoints.append(pipe[selected])
        if same(endpoints[0], endpoints[1]):
            if not same(endpoints[0], request.connection_point):
                raise CadError("Endpoints already coincide; an outward loop is not a connection")
            return Result(status="dry_run" if dry_run else "ok", data={"already_connected": True})
        points = []
        for point in [endpoints[0], request.connection_point, endpoints[1]]:
            if not points or not same(points[-1], point):
                points.append(POINT_ADAPTER.validate_python(point))
        return self.apply(
            self.plan(
                "create",
                pipes,
                first["document_id"],
                points=points,
                **self.destination(request.color, request.layer, request.allow_create_layer),
            ),
            dry_run,
        )

    @workflow
    def analyze(self, **kwargs):
        from .analysis import analyze

        request = models.Analysis.model_validate(kwargs)
        self.page_args(request)
        return analyze(self, request)

    @workflow
    def labels(self, **kwargs):
        from .analysis import diameter_labels

        request = models.Labels.model_validate(kwargs)
        self.page_args(request)
        return diameter_labels(self, request)

    @workflow
    def blocks(self, **kwargs):
        request = models.Nearby.model_validate(kwargs)
        result = self.cad.require("pipeline_aux", kind="blocks", **self.page_args(request))
        result.data["blocks"] = result.data.pop("objects")
        result.count = len(result.data["blocks"])
        return result
