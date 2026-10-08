"""ActiveX pipeline operations. Every function runs only in ComAdapter's owning STA.

Undo marks group edits; captured geometry provides compensating restoration, not a
database transaction. Deletion cannot be restored with its original Handle here.
"""

import json
import math

from ..core.exceptions import CadError
from ..pipelines.colors import ACI, classify, color_spec
from ..pipelines.common import describe, matches, paginate, validate_plan

KINDS = {"AcDbLine": "LINE", "AcDbPolyline": "LWPOLYLINE", "AcDb2dPolyline": "POLYLINE"}


def layer_info(doc, name):
    try:
        layer = doc.Layers.Item(name)
    except Exception:
        return {"name": name, "exists": False, "locked": False, "is_xref": "|" in name}
    return {
        "name": name,
        "exists": True,
        "locked": bool(layer.Lock),
        "is_xref": "|" in name,
        "color": color_spec(layer),
    }


def entity_by_handle(doc, handle):
    try:
        return doc.HandleToObject(handle.upper())
    except Exception as exc:
        raise CadError(
            f"Cannot resolve entity Handle {handle}; inspect the active document"
        ) from exc


def read(adapter, doc, handle, entity=None):
    entity = entity if entity is not None else entity_by_handle(doc, handle)
    kind = KINDS.get(entity.ObjectName)
    if kind is None:
        raise CadError("Handle is not a LINE/LWPOLYLINE/simple 2D POLYLINE")
    layer = layer_info(doc, entity.Layer)
    if not layer["exists"]:
        raise CadError("Cannot read the entity layer")
    if kind == "LINE":
        vertices = [list(entity.StartPoint), list(entity.EndPoint)]
        closed, bulges, widths = False, [], []
    else:
        if list(entity.Normal) != [0, 0, 1] or entity.Elevation != 0:
            raise CadError(
                "Tilted or elevated OCS geometry is unsupported; only WCS XY is supported"
            )
        if kind == "POLYLINE" and int(entity.Type) != 0:
            raise CadError("Curve-fit/spline-fit legacy POLYLINE is unsupported")
        coordinates = tuple(entity.Coordinates)
        stride = 2 if kind == "LWPOLYLINE" else 3
        if len(coordinates) > 2000 * stride or len(coordinates) % stride:
            raise CadError("Polyline coordinates exceed supported vertex budget")
        # Autodesk: legacy Polyline Coordinates uses OCS XY and ignores every third value.
        # Normal=(0,0,1), Elevation=0 makes these coordinates identical to WCS XY.
        vertices = [list(coordinates[i : i + 2]) for i in range(0, len(coordinates), stride)]
        closed = bool(entity.Closed)
        count = len(vertices) if closed else len(vertices) - 1
        bulges = [float(entity.GetBulge(i)) for i in range(count)]
        widths = [list(entity.GetWidth(i)) for i in range(count)]
    owner_id = int(entity.OwnerID)
    in_model = owner_id == int(doc.ModelSpace.ObjectID)
    owner = doc.ObjectIDToObject(owner_id)
    is_xref = bool(owner.IsXRef) or layer["is_xref"]
    try:
        codes, values = entity.GetXData("ACEMCP")
    except Exception as exc:
        raise CadError("Cannot inspect engineering metadata safely") from exc
    engineering = False
    if codes:
        try:
            metadata = json.loads(
                "".join(v for c, v in zip(codes, values, strict=False) if c == 1000)
            )
            engineering = isinstance(metadata, dict) and bool(metadata.get("engineering"))
        except (ValueError, TypeError) as exc:
            raise CadError("Malformed engineering XData; candidate editing is protected") from exc
    return describe(
        handle=str(entity.Handle),
        kind=kind,
        vertices=vertices,
        layer=str(entity.Layer),
        assigned_color=color_spec(entity),
        layer_color=layer["color"],
        closed=closed,
        bulges=bulges,
        widths=widths,
        length=float(entity.Length),
        object_id=str(entity.ObjectID),
        locked=layer["locked"],
        is_xref=is_xref,
        in_model_space=in_model,
        engineering=engineering,
    )


def document_data(adapter, doc):
    info = adapter.document_info(doc)
    return {"document_id": info["document_id"], "insunits": info["units"]}


def execute(adapter, command, args):
    doc = adapter.document()
    if command == "pipeline_get":
        return {
            "data": {"pipeline": read(adapter, doc, args["handle"]), **document_data(adapter, doc)}
        }
    if command == "pipeline_layer":
        return {"data": layer_info(doc, args["name"])}
    if command == "pipeline_query":
        collection = (
            doc.PickfirstSelectionSet if args["selection"] == "selected" else doc.ModelSpace
        )

        def getter(index):
            entity = collection.Item(index)
            if entity.ObjectName not in KINDS or (
                args.get("layer") and entity.Layer != args["layer"]
            ):
                return None
            layer = layer_info(doc, entity.Layer)
            color, _ = classify(color_spec(entity), layer.get("color", {}))
            if color is None or (args["color"] != "all" and color != args["color"]):
                return None
            pipe = read(adapter, doc, str(entity.Handle), entity)
            return pipe if matches(pipe, args) else None

        result = paginate(int(collection.Count), getter, args)
        result["data"].update(document_data(adapter, doc))
        return result
    if command == "pipeline_aux":
        collection = doc.ModelSpace

        def getter(index):
            entity = collection.Item(index)
            names = {"AcDbText", "AcDbMText"} if args["kind"] == "texts" else {"AcDbBlockReference"}
            if entity.ObjectName not in names or (
                args.get("layer") and entity.Layer != args["layer"]
            ):
                return None
            point = list(entity.InsertionPoint)
            if len(point) != 3 or point[2] != 0:
                return None
            if args.get("region"):
                x0, y0, x1, y1 = args["region"]
                if not x0 <= point[0] <= x1 or not y0 <= point[1] <= y1:
                    return None
            distance = (
                math.dist(point[:2], args["point"][:2]) if args.get("point") is not None else None
            )
            if distance is not None and distance > args["radius"]:
                return None
            return {
                "scan_position": index,
                "handle": str(entity.Handle),
                "type": entity.ObjectName,
                "position": point[:2],
                "layer": str(entity.Layer),
                "distance": distance,
                "name": str(entity.Name) if args["kind"] == "blocks" else None,
                "text": str(entity.TextString)[:4000] if args["kind"] == "texts" else "",
            }

        result = paginate(int(collection.Count), getter, args, key="objects")
        result["data"].update(document_data(adapter, doc))
        return result
    if command == "pipeline_intersections":
        if document_data(adapter, doc)["document_id"] != args["expected_document"]:
            raise CadError("Active document changed during analysis")
        if len(args["pairs"]) > 25:
            raise CadError("Intersection batch exceeds budget")
        for handle, stamp in args["expected"].items():
            if read(adapter, doc, handle)["stamp"] != stamp:
                raise CadError("Pipeline changed during analysis; retry")
        hits, point_count = [], 0
        for first, second in args["pairs"]:
            raw = entity_by_handle(doc, first).IntersectWith(entity_by_handle(doc, second), 0)
            if raw:
                if len(raw) % 3:
                    raise CadError("Unexpected IntersectWith coordinates")
                points = [list(raw[i : i + 2]) for i in range(0, len(raw), 3)]
                point_count += len(points)
                if point_count > 1000:
                    raise CadError("Intersection point budget exceeded; narrow the request")
                hits.append({"first_handle": first, "second_handle": second, "points": points})
        return {"data": {"intersections": hits}}
    if command == "pipeline_mutate":
        return mutate(adapter, doc, args)
    raise CadError("Unsupported pipeline command")


def restore_color(entity, spec):
    if spec["method"] == "rgb":
        color = entity.TrueColor
        color.SetRGB(*spec["rgb"])
        entity.TrueColor = color
    elif spec["method"] in {"aci", "by_layer", "by_block"}:
        entity.Color = spec.get("aci", 256 if spec["method"] == "by_layer" else 0)
    else:
        raise CadError("Unsupported colour method cannot be restored safely")


def write_route(adapter, entity, pipe, points, bulges, widths):
    if pipe["type"] == "LINE":
        entity.StartPoint = adapter.doubles([*points[0][:2], 0])
        entity.EndPoint = adapter.doubles([*points[-1][:2], 0])
    else:
        stride = 2 if pipe["type"] == "LWPOLYLINE" else 3
        flat = [v for p in points for v in ([*p[:2], 0] if stride == 3 else p[:2])]
        entity.Coordinates = adapter.doubles(flat)
        entity.Closed = pipe["closed"]
        for i, bulge in enumerate(bulges):
            entity.SetBulge(i, bulge)
        for i, (start_width, end_width) in enumerate(widths):
            entity.SetWidth(i, start_width, end_width)
    entity.Update()


def mutate(adapter, doc, plan):
    identity = document_data(adapter, doc)
    validate_plan(
        plan, lambda h: read(adapter, doc, h), identity["document_id"], plan["max_change"]
    )
    snapshots = {h: read(adapter, doc, h) for h in plan["handles"]}
    # All snapshots and destination checks precede the first drawing change.
    if plan["action"] == "create":
        layer = layer_info(doc, plan["layer"])
        if (
            layer["locked"]
            or layer["is_xref"]
            or (not layer["exists"] and not plan["create_layer"])
        ):
            raise CadError("Destination layer is not editable or cannot be created")
    created, changed, new_layer, marked, warnings = [], [], None, False, []
    result = None
    try:
        doc.StartUndoMark()
        marked = True
        action = plan["action"]
        if action == "create":
            if not layer["exists"]:
                new_layer = doc.Layers.Add(plan["layer"])
                new_layer.Color = ACI[plan["color"]]
            entity = doc.ModelSpace.AddLightWeightPolyline(
                adapter.doubles([v for p in plan["points"] for v in p[:2]])
            )
            created.append(entity)  # Track before the next COM property assignment can fail.
            entity.Layer = plan["layer"]
            entity.Color = ACI[plan["color"]]
            entity.Closed = False
            entity.Update()
            handles = [str(entity.Handle)]
        else:
            handles = plan["handles"]
            for handle in handles:
                entity, pipe = entity_by_handle(doc, handle), snapshots[handle]
                changed.append(
                    handle
                )  # A failed property assignment may already have side effects.
                if action == "delete":
                    entity.Delete()
                elif action == "color":
                    entity.Color = ACI[plan["color"]]
                    entity.Update()
                elif action == "move":
                    entity.Move(
                        adapter.doubles([0, 0, 0]), adapter.doubles([plan["dx"], plan["dy"], 0])
                    )
                    entity.Update()
                elif action == "modify":
                    points = plan["points"]
                    count = len(points) if pipe["closed"] else len(points) - 1
                    widths = pipe["widths"]
                    if widths and len(points) != len(pipe["vertices"]):
                        widths = [widths[0]] * count
                    write_route(adapter, entity, pipe, points, [0] * count, widths)
                else:
                    raise CadError("Unsupported mutation action")
        result = {
            "object_ids": handles,
            "count": len(handles),
            "data": {
                "action": action,
                "undo": "grouped_mark",
                "rollback": "not_needed",
                **identity,
            },
        }
    except Exception as exc:
        errors = []
        if plan["action"] == "delete" and changed:
            rollback = "unavailable_for_delete"
            warnings.append(
                "COM cannot restore a deleted object with its Handle; "
                "inspect DWG and use AutoCAD Undo"
            )
        else:
            for entity in reversed(created):
                try:
                    entity.Delete()
                except Exception as failure:
                    errors.append(f"Created entity cleanup failed: {type(failure).__name__}")
            if new_layer is not None:
                try:
                    new_layer.Delete()
                except Exception as failure:
                    errors.append(f"New layer cleanup failed: {type(failure).__name__}")
            for handle in reversed(changed):
                try:
                    pipe = snapshots[handle]
                    entity = entity_by_handle(doc, handle)
                    if plan["action"] in {"modify", "move"}:
                        write_route(
                            adapter, entity, pipe, pipe["vertices"], pipe["bulges"], pipe["widths"]
                        )
                    restore_color(entity, pipe["assigned_color"])
                    entity.Update()
                    if read(adapter, doc, handle)["stamp"] != pipe["stamp"]:
                        raise CadError("Restored state differs from snapshot")
                except Exception as failure:
                    errors.append(f"Handle {handle} restoration failed: {type(failure).__name__}")
            rollback = "failed" if errors else "restored"
        result = {
            "status": "error",
            "error": f"Pipeline mutation failed ({type(exc).__name__}); inspect rollback status",
            "data": {
                "action": plan["action"],
                "rollback": rollback,
                "rollback_errors": errors,
                "requested_handles": plan["handles"],
                **identity,
            },
        }
    finally:
        if marked:
            try:
                doc.EndUndoMark()
            except Exception:
                warnings.append("EndUndoMark failed; AutoCAD Undo grouping is uncertain")
    result["warnings"] = warnings
    return result
