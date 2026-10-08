"""CAD connection, editable 2D geometry, safe transforms, layers and drawing queries."""

import math
from typing import Annotated, Literal

from pydantic import Field

from ..core.exceptions import CadError
from ..core.models import (
    Arc,
    Batch,
    Block,
    Circle,
    Creation,
    Dimension,
    Handle,
    Hatch,
    InsertBlock,
    Layer,
    Line,
    MText,
    Name,
    Point,
    Polyline,
    Positive,
    Result,
    Spline,
    Text,
    Transform,
    Units,
)
from .registration import annotations, model_tool


def register(server, cad):
    def tool(read_only=False, destructive=False):
        return server.tool(annotations=annotations(read_only, destructive))

    @tool()
    def autocad_connect(allow_launch: bool = False, allow_other_version: bool = False) -> Result:
        """Attach to AutoCAD 2027. Starting a new process needs explicit allow_launch."""
        return cad.call(
            "connect", allow_launch=allow_launch, allow_other_version=allow_other_version
        )

    @tool()
    def autocad_disconnect() -> Result:
        """Release COM references; leave AutoCAD and its drawings open."""
        return cad.call("disconnect")

    @tool(True)
    def autocad_get_status() -> Result:
        """Report backend and connection; never claim tested Windows compatibility."""
        return cad.call("status")

    @tool(True)
    def autocad_get_version() -> Result:
        """Read the connected application's version."""
        return cad.call("status")

    @tool(True)
    def autocad_list_documents() -> Result:
        """List open documents without closing or modifying them."""
        return cad.call("list_documents")

    @tool(True)
    def autocad_get_active_document() -> Result:
        """Read active drawing name, units, saved state and document identity."""
        return cad.call("active_document")

    @tool()
    def autocad_select_document(name: Name) -> Result:
        """Activate an already-open drawing by exact name."""
        return cad.call("select_document", name=name)

    @tool()
    def autocad_create_document(units: Literal[1, 2, 4, 5, 6] = 4) -> Result:
        """Create a new document and explicitly set INSUNITS (default 4 = mm)."""
        return cad.call("create_document", units=units)

    @tool()
    def autocad_open_document(path: str) -> Result:
        """Open an existing DWG inside configured save_root."""
        try:
            target = cad.files.resolve(path)
            if not target.is_file():
                raise CadError("DWG not found")
            return cad.call("open_document", path=str(target))
        except (CadError, OSError) as exc:
            return Result(status="error", error=str(exc))

    @tool(destructive=True)
    def autocad_save_document(overwrite: bool = False, dry_run: bool = True) -> Result:
        """Save active DWG with path policy and backup. Existing file requires overwrite=true."""
        return cad.save(None, overwrite, dry_run)

    @tool(destructive=True)
    def autocad_save_as(path: str, overwrite: bool = False, dry_run: bool = True) -> Result:
        """Save an editable DWG inside save_root; default is dry-run. Mock cannot write DWG."""
        return cad.save(path, overwrite, dry_run)

    for name, model, description in [
        ("cad_draw_line", Line, "Create a 2D editable WCS line; points must have z=0."),
        ("cad_draw_polyline", Polyline, "Create a planar editable lightweight polyline."),
        ("cad_draw_circle", Circle, "Create a 2D editable circle."),
        ("cad_draw_arc", Arc, "Create a 2D arc; angles are radians, counterclockwise."),
        ("cad_draw_text", Text, "Create editable single-line text; rotation is radians."),
        ("cad_draw_mtext", MText, "Create editable multiline text."),
        ("cad_draw_dimension", Dimension, "Create editable aligned dimension on the given layer."),
        (
            "cad_draw_spline",
            Spline,
            "Create a 2D fit-point spline with endpoint tangents from route.",
        ),
        (
            "cad_draw_hatch",
            Hatch,
            "Hatch a closed circle/polyline; first boundary outer, remaining holes.",
        ),
        (
            "cad_create_layer",
            Layer,
            "Create a configured layer; existing layers are left unchanged.",
        ),
        ("cad_create_block", Block, "Create an original generic rectangle/cross schematic symbol."),
        (
            "cad_insert_block",
            InsertBlock,
            "Insert a defined block or 2D DWG library inside save_root.",
        ),
    ]:
        model_tool(server, name, model, cad.create, description)

    @tool()
    def cad_draw_rectangle(
        origin: Point,
        width: Positive,
        height: Positive,
        layer: Name = "0",
        units: Units = "mm",
        dry_run: bool = False,
    ) -> Result:
        """Draw a closed 2D rectangle as an editable lightweight polyline."""
        x, y, _ = origin
        return cad.create(
            Polyline(
                points=[origin, (x + width, y, 0), (x + width, y + height, 0), (x, y + height, 0)],
                closed=True,
                layer=layer,
                units=units,
            ),
            dry_run,
        )

    @tool()
    def cad_draw_polygon(
        center: Point,
        radius: Positive,
        sides: Annotated[int, Field(ge=3, le=100)] = 6,
        layer: Name = "0",
        units: Units = "mm",
        dry_run: bool = False,
    ) -> Result:
        """Draw a regular 2D polygon, with radius to its vertices."""
        points = [
            (
                center[0] + radius * math.cos(i * math.tau / sides),
                center[1] + radius * math.sin(i * math.tau / sides),
                0,
            )
            for i in range(sides)
        ]
        return cad.create(Polyline(points=points, closed=True, layer=layer, units=units), dry_run)

    @tool()
    def cad_execute_batch(
        operations: Annotated[list[Creation], Field(min_length=1, max_length=500)],
        dry_run: bool = True,
        rollback_on_error: bool = True,
    ) -> Result:
        """Creation-only batch with typed preflight and optional best-effort COM cleanup."""
        from pydantic import ValidationError

        try:
            return cad.batch(
                Batch(operations=operations, dry_run=dry_run, rollback_on_error=rollback_on_error)
            )
        except ValidationError as exc:
            return Result(status="error", error=str(exc))

    @tool(True)
    def cad_list_layers() -> Result:
        """Read drawing layers and their editable drafting properties."""
        return cad.call("list_layers")

    @tool()
    def cad_set_current_layer(name: Name) -> Result:
        """Set an existing current layer."""
        return cad.call("set_current_layer", name=name)

    @tool()
    def cad_set_layer_color(name: Name, color: Annotated[int, Field(ge=1, le=255)]) -> Result:
        """Set indexed colour; colours are project conventions, not mandated standards."""
        return cad.call("set_layer", name=name, properties={"color": color})

    @tool()
    def cad_set_layer_linetype(name: Name, linetype: Name) -> Result:
        """Use an already-loaded linetype; this tool does not execute commands to load files."""
        return cad.call("set_layer", name=name, properties={"linetype": linetype})

    @tool()
    def cad_set_layer_lineweight(name: Name, lineweight: int) -> Result:
        """Set a valid ActiveX lineweight enumerator (hundredths of mm, or default flags)."""
        try:
            value = Layer(name=name, lineweight=lineweight).lineweight
            return cad.call("set_layer", name=name, properties={"lineweight": value})
        except (ValueError, CadError) as exc:
            return Result(status="error", error=str(exc))

    @tool(destructive=True)
    def cad_delete_layer(name: Name, confirm: bool = False) -> Result:
        """Delete an unused, unprotected layer only with explicit confirm=true."""
        if not confirm:
            return Result(status="error", error="Layer deletion requires confirm=true")
        return cad.call("delete_layer", name=name)

    @tool(True)
    def cad_list_blocks() -> Result:
        """List block definitions; model-space and paper-space layouts are excluded."""
        return cad.call("list_blocks")

    @tool(True)
    def cad_get_block_attributes(handle: Handle) -> Result:
        """Read editable block attribute tags/values by DWG handle."""
        return cad.call("get_attributes", handle=handle)

    @tool()
    def cad_set_block_attributes(handle: Handle, attributes: dict[str, str]) -> Result:
        """Update standard block tags; unknown tags are rejected."""
        try:
            validated = InsertBlock(name="validate", position=(0, 0), attributes=attributes)
            entity = cad.require("get_entity", handle=handle).data["entity"]
            if entity.get("metadata", {}).get("engineering"):
                return Result(
                    status="error",
                    error="Changing linked attributes would stale engineering "
                    "metadata; recreate the element through engineering tools",
                )
            return cad.call("set_attributes", handle=handle, attributes=validated.attributes)
        except (ValueError, CadError) as exc:
            return Result(status="error", error=str(exc))

    @tool(True)
    def cad_get_entity_properties(handle: Handle) -> Result:
        """Read bounded standard properties, attributes and engineering XData."""
        return cad.call("get_entity", handle=handle)

    @tool(True)
    def cad_get_entities(
        layer: Name | None = None,
        entity_type: str | None = None,
        mark: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Result:
        """Page model-space objects by returned next_offset; optional layer/type/MARK filters."""
        return cad.entities(
            layer=layer, entity_type=entity_type, mark=mark, offset=offset, limit=limit
        )

    @tool(True)
    def cad_get_selected_entities(offset: int = 0, limit: int = 100) -> Result:
        """Read the current Pickfirst preselection without prompting or selecting objects."""
        return cad.entities(selected=True, offset=offset, limit=limit)

    @tool(True)
    def cad_find_entities_by_layer(layer: Name, offset: int = 0, limit: int = 100) -> Result:
        """Page model-space entities on a specific layer."""
        return cad.entities(layer=layer, offset=offset, limit=limit)

    @tool(True)
    def cad_find_entities_by_type(entity_type: str, offset: int = 0, limit: int = 100) -> Result:
        """Page entities of type line/polyline/circle/arc/text/mtext/insert_block/dimension."""
        return cad.entities(entity_type=entity_type, offset=offset, limit=limit)

    @tool(True)
    def cad_get_drawing_bounds() -> Result:
        """Read regenerated model-space WCS extents; mock bounds are approximate."""
        return cad.call("bounds")

    @tool(True)
    def cad_get_document_units() -> Result:
        """Read INSUNITS; geometry converts mm/cm/m/in/ft and rejects ambiguous unitless DWGs."""
        return cad.call("get_units")

    register_transforms(server, cad)


def register_transforms(server, cad):
    """Typed per-operation signatures with conservative confirmation defaults."""
    from ..core.models import Model

    class Move(Model):
        object_ids: list[Handle] = Field(min_length=1, max_length=1000)
        base: Point
        target: Point
        units: Units = "mm"
        confirm: bool = False

    class Rotate(Model):
        object_ids: list[Handle] = Field(min_length=1, max_length=1000)
        base: Point
        angle: float = Field(allow_inf_nan=False, ge=-1e6, le=1e6)
        units: Units = "mm"
        confirm: bool = False

    class Scale(Model):
        object_ids: list[Handle] = Field(min_length=1, max_length=1000)
        base: Point
        factor: Positive
        units: Units = "mm"
        confirm: bool = False

    class Delete(Model):
        object_ids: list[Handle] = Field(min_length=1, max_length=1000)
        confirm: bool = False

    class Offset(Model):
        object_ids: list[Handle] = Field(min_length=1, max_length=1000)
        distance: float = Field(allow_inf_nan=False)
        units: Units = "mm"
        confirm: bool = False

    for action, model in [
        ("move", Move),
        ("copy", Move),
        ("rotate", Rotate),
        ("scale", Scale),
        ("delete", Delete),
        ("offset", Offset),
        ("mirror", Move),
        ("delete_block_reference", Delete),
    ]:

        def make_handler(mode):
            def handler(request, dry_run):
                try:
                    if mode == "delete_block_reference":
                        for handle in request.object_ids:
                            entity = cad.call("get_entity", handle=handle)
                            if entity.status == "error":
                                return entity
                            if entity.data["entity"]["type"] != "insert_block":
                                return Result(status="error", error="Expected a block reference")
                    request = Transform(
                        type="delete" if mode == "delete_block_reference" else mode,
                        **request.model_dump(),
                    )
                    return cad.transform(request, dry_run)
                except ValueError as exc:
                    return Result(status="error", error=str(exc))

            return handler

        model_tool(
            server,
            f"cad_{action}",
            model,
            make_handler(action),
            f"2D {action}; large changes require confirm=true, deletions always require it. "
            "Linked engineering geometry must be recreated instead of transformed.",
        )
