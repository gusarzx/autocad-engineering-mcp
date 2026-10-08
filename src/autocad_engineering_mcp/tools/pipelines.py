"""Additional tools on the existing server; all new distances use drawing units."""

from typing import Literal

from ..core.models import Name, Point, Result
from ..pipelines import models
from .registration import annotations, model_tool


def register(server, service):
    @server.tool(annotations=annotations(read_only=True))
    def get_pipelines(
        color: models.ColorFilter = "all",
        layer: Name | None = None,
        selection: Literal["all", "selected"] = "all",
        region: models.Region | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Result:
        """Read red/blue LINE and 2D polyline candidates, with a raw-position cursor.
        Region=[xmin,ymin,xmax,ymax]. Exact ACI 1/5 or RGB, including ByLayer.
        Candidate colours do not identify heating/water systems.
        Coordinates are WCS XY and all distances are drawing units, without millimetre conversion.
        """
        return service.query(
            color=color, layer=layer, selection=selection, region=region, offset=offset, limit=limit
        )

    @server.tool(annotations=annotations(read_only=True))
    def get_selected_pipelines(
        color: models.ColorFilter = "all",
        layer: Name | None = None,
        region: models.Region | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Result:
        """Read only current Pickfirst preselection; never open an interactive selection prompt."""
        return service.query(
            color=color,
            layer=layer,
            selection="selected",
            region=region,
            offset=offset,
            limit=limit,
        )

    @server.tool(annotations=annotations(read_only=True))
    def analyze_pipeline_connections(
        tolerance: float = 1,
        color: models.ColorFilter = "all",
        layer: Name | None = None,
        selection: Literal["all", "selected"] = "all",
        region: models.Region | None = None,
        offset: int = 0,
        limit: int = 100,
        max_pipelines: int = 500,
    ) -> Result:
        """Find CONNECTED exact ends, INTERSECTION crossings, OPEN_END, NEAR_CONNECTION.
        TURN and CURVED_SEGMENT. Tolerance in drawing units detects gaps, never joins automatically.
        Offset pages findings; narrow filters if geometry budgets are exceeded.
        """
        return service.analyze(
            tolerance=tolerance,
            color=color,
            layer=layer,
            selection=selection,
            region=region,
            offset=offset,
            limit=limit,
            max_pipelines=max_pipelines,
        )

    @server.tool(annotations=annotations(read_only=True))
    def find_pipe_diameter_labels(
        max_distance: float = 1000,
        color: models.ColorFilter = "all",
        layer: Name | None = None,
        selection: Literal["all", "selected"] = "all",
        region: models.Region | None = None,
        offset: int = 0,
        limit: int = 100,
        max_pipelines: int = 500,
    ) -> Result:
        """Recognise Ø/⌀/DN/Ду/D labels in TEXT/MTEXT; nearest-pipe links are unconfirmed.
        max_distance uses drawing units; no diameter sizing.
        Layer/region filter labels and candidates; selection filters candidate pipes.
        Cursor pages the raw ModelSpace scan, including unmatched text.
        """
        return service.labels(
            max_distance=max_distance,
            color=color,
            layer=layer,
            selection=selection,
            region=region,
            offset=offset,
            limit=limit,
            max_pipelines=max_pipelines,
        )

    @server.tool(annotations=annotations(read_only=True))
    def get_nearby_blocks(point: Point, radius: float, offset: int = 0, limit: int = 100) -> Result:
        """Find block names and insertion points within an XY radius in drawing units.
        Uses raw ModelSpace cursor; does not classify blocks as plumbing fixtures.
        """
        return service.blocks(point=point, radius=radius, offset=offset, limit=limit)

    model_tool(
        server,
        "create_pipeline",
        models.Create,
        service.create,
        "Create one ACI-coloured LWPOLYLINE in drawing units. Default MCP_PIPE_RED/BLUE layer "
        "is created if absent. Missing named layers need allow_create_layer=true. No auto-save.",
    )
    model_tool(
        server,
        "modify_pipeline",
        models.Modify,
        service.modify,
        "Edit route on the same Handle. LINE retains two endpoints; arc changes and unsafe widths "
        "are rejected. Geometry stays in WCS XY, drawing units. dry_run previews without changes.",
        destructive=True,
    )
    model_tool(
        server,
        "extend_pipeline",
        models.Extend,
        service.extend,
        "Continue the chosen end, points ordered outward. Start continuation is reversed. "
        "Retains Handle. Closed/curved route changes and bent LINE extensions are rejected.",
        destructive=True,
    )
    model_tool(
        server,
        "connect_pipelines",
        models.Connect,
        service.connect,
        "Bridge two open candidates via connection_point. Uses nearest ends unless endpoints "
        "are supplied. Mixed colours need allow_mixed_colors=true. Connects endpoints only.",
    )
    for name, model, action, selected, description in [
        (
            "move_pipeline",
            models.Move,
            "move",
            False,
            "Move one candidate by dx/dy in drawing units, retaining Handle and arcs.",
        ),
        (
            "delete_pipeline",
            models.Delete,
            "delete",
            False,
            "Delete only the given candidate Handle; requires confirm=true. dry_run previews. "
            "Deleted Handle recovery is not guaranteed; inspect DWG and use AutoCAD Undo.",
        ),
        (
            "set_pipeline_color",
            models.Recolor,
            "color",
            False,
            "Set explicit red ACI 1 or blue ACI 5 on one candidate.",
        ),
        (
            "move_selected_pipelines",
            models.SelectedMove,
            "move",
            True,
            "Move preselected red/blue candidates in drawing units. "
            "Above max_change requires confirm=true. Use dry_run for preview.",
        ),
        (
            "set_selected_pipelines_color",
            models.SelectedColor,
            "color",
            True,
            "Recolour preselected red/blue candidates. "
            "Above max_change requires confirm=true; dry_run previews. No interactive prompt.",
        ),
    ]:

        def handler(request, dry_run, action=action, selected=selected):
            return service.mutate(request, action, dry_run, selected)

        model_tool(server, name, model, handler, description, destructive=True)
