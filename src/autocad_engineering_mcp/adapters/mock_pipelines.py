"""Explicit test implementation of pipeline commands; never presented as real AutoCAD."""

import copy
import math

from ..core.exceptions import CadError
from ..pipelines.colors import ACI, classify
from ..pipelines.common import describe, matches, paginate, validate_plan
from ..pipelines.geometry import pipe_intersections

KINDS = {"line": "LINE", "polyline": "LWPOLYLINE", "legacy_polyline": "POLYLINE"}


def layer_info(adapter, name):
    layer = adapter.document()["layers"].get(name)
    if layer is None:
        return {"name": name, "exists": False, "locked": False, "is_xref": False}
    return {
        "name": name,
        "exists": True,
        "locked": bool(layer.get("locked")),
        "is_xref": bool(layer.get("is_xref")) or "|" in name,
        "color": layer.get("color_spec", {"method": "aci", "aci": layer["color"]}),
    }


def read(adapter, handle):
    entity = adapter.entity(handle.upper())
    kind = entity.get("cad_type", KINDS.get(entity["type"]))
    if kind is None:
        raise CadError("Handle is not a LINE/LWPOLYLINE/POLYLINE")
    if entity.get("normal", [0, 0, 1]) != [0, 0, 1] or entity.get("elevation", 0) != 0:
        raise CadError("Only the 2D XY plane is supported")
    if entity.get("polyline_type", 0) != 0:
        raise CadError("Curve-fit/spline-fit legacy POLYLINE is not supported")
    layer = layer_info(adapter, entity["layer"])
    if not layer["exists"]:
        raise CadError("Entity layer no longer exists")
    vertices = [entity["start"], entity["end"]] if kind == "LINE" else entity["points"]
    return describe(
        handle=entity["id"],
        kind=kind,
        vertices=vertices,
        layer=entity["layer"],
        assigned_color=entity.get("assigned_color", {"method": "by_layer"}),
        layer_color=layer["color"],
        closed=entity.get("closed", False),
        bulges=entity.get("bulges"),
        widths=entity.get("widths"),
        locked=layer["locked"],
        is_xref=bool(entity.get("is_xref")) or layer["is_xref"],
        in_model_space=entity.get("in_model_space", True),
        engineering=bool(entity.get("metadata", {}).get("engineering")),
    )


def execute(adapter, command, args):
    doc = adapter.document()
    if command == "pipeline_get":
        return {
            "data": {
                "pipeline": read(adapter, args["handle"]),
                "document_id": doc["document_id"],
                "insunits": doc["units"],
            }
        }
    if command == "pipeline_layer":
        return {"data": layer_info(adapter, args["name"])}
    if command == "pipeline_query":
        handles = (
            list(doc.get("selection", []))
            if args["selection"] == "selected"
            else list(doc["entities"])
        )

        def getter(index):
            entity = adapter.entity(handles[index].upper())
            if entity["type"] not in KINDS and entity.get("cad_type") not in KINDS.values():
                return None
            if args.get("layer") and entity["layer"] != args["layer"]:
                return None
            color, _ = classify(
                entity.get("assigned_color", {"method": "by_layer"}),
                layer_info(adapter, entity["layer"]).get("color", {}),
            )
            if color is None or (args["color"] != "all" and args["color"] != color):
                return None
            pipe = read(adapter, handles[index])
            return pipe if matches(pipe, args) else None

        result = paginate(len(handles), getter, args)
        result["data"].update(document_id=doc["document_id"], insunits=doc["units"])
        result["warnings"] = ["Mock selection is test state; no real interactive AutoCAD selection"]
        return result
    if command == "pipeline_aux":
        handles = list(doc["entities"])

        def getter(index):
            entity = adapter.entity(handles[index])
            expected = {"text", "mtext"} if args["kind"] == "texts" else {"insert_block"}
            if entity["type"] not in expected:
                return None
            if args.get("layer") and entity["layer"] != args["layer"]:
                return None
            position = list(entity.get("position", (0, 0, 0)))
            if len(position) == 3 and position[2] != 0:
                return None
            if args.get("region"):
                x0, y0, x1, y1 = args["region"]
                if not x0 <= position[0] <= x1 or not y0 <= position[1] <= y1:
                    return None
            if args.get("point") is not None:
                distance = math.dist(position[:2], args["point"][:2])
                if distance > args["radius"]:
                    return None
            else:
                distance = None
            return {
                "scan_position": index,
                "handle": entity["id"],
                "type": entity["type"],
                "position": position[:2],
                "layer": entity["layer"],
                "name": entity.get("name"),
                "text": entity.get("text", "")[:4000],
                "distance": distance,
            }

        result = paginate(len(handles), getter, args, key="objects")
        result["data"].update(document_id=doc["document_id"], insunits=doc["units"])
        return result
    if command == "pipeline_intersections":
        if doc["document_id"] != args["expected_document"]:
            raise CadError("Active document changed during analysis")
        for handle, stamp in args["expected"].items():
            if read(adapter, handle)["stamp"] != stamp:
                raise CadError("Pipeline changed during analysis; retry")
        results = []
        for first, second in args["pairs"]:
            points = pipe_intersections(read(adapter, first), read(adapter, second))
            if points:
                results.append({"first_handle": first, "second_handle": second, "points": points})
        return {
            "data": {"intersections": results},
            "warnings": ["Mock uses exact planar segment/bulge math"],
        }
    if command == "pipeline_mutate":
        return mutate(adapter, args)
    raise CadError("Unsupported pipeline command")


def mutate(adapter, plan):
    doc = adapter.document()
    validate_plan(plan, lambda h: read(adapter, h), doc["document_id"], plan["max_change"])
    snapshot = copy.deepcopy(doc)
    created = []
    try:
        action = plan["action"]
        if action == "create":
            layer = layer_info(adapter, plan["layer"])
            if layer["locked"] or layer["is_xref"]:
                raise CadError("Destination layer is locked or XREF-dependent")
            if not layer["exists"]:
                if not plan["create_layer"]:
                    raise CadError("Creating a missing named layer requires explicit permission")
                adapter.execute(
                    "create_layer",
                    {
                        "name": plan["layer"],
                        "color": ACI[plan["color"]],
                        "linetype": "Continuous",
                        "lineweight": -3,
                    },
                )
            data = {
                "type": "draw_polyline",
                "points": plan["points"],
                "closed": False,
                "layer": plan["layer"],
                "assigned_color": {"method": "aci", "aci": ACI[plan["color"]]},
            }
            created = adapter.add(data)["object_ids"]
            handles = created
        else:
            handles = plan["handles"]
            for handle in handles:
                entity = adapter.entity(handle)
                if action == "delete":
                    del doc["entities"][handle]
                    doc["selection"] = [h for h in doc.get("selection", []) if h != handle]
                elif action == "color":
                    entity["assigned_color"] = {"method": "aci", "aci": ACI[plan["color"]]}
                else:
                    pipe = read(adapter, handle)
                    vertices = (
                        plan["points"]
                        if action == "modify"
                        else [[p[0] + plan["dx"], p[1] + plan["dy"], 0] for p in pipe["vertices"]]
                    )
                    if pipe["type"] == "LINE":
                        entity["start"], entity["end"] = tuple(vertices[0]), tuple(vertices[-1])
                    else:
                        entity["points"] = [tuple(p) for p in vertices]
                        if action == "modify":
                            entity["bulges"] = [0] * (
                                len(vertices) if pipe["closed"] else len(vertices) - 1
                            )
                            widths = pipe["widths"]
                            if widths and len(vertices) != len(pipe["vertices"]):
                                entity["widths"] = [widths[0]] * len(entity["bulges"])
        doc["saved"] = False
        return {
            "object_ids": handles,
            "count": len(handles),
            "data": {
                "action": action,
                "undo": "mock_snapshot",
                "rollback": "not_needed",
                "insunits": doc["units"],
                "document_id": doc["document_id"],
            },
        }
    except Exception as exc:
        adapter.documents[adapter.active] = snapshot
        return {
            "status": "error",
            "error": str(exc),
            "data": {
                "action": plan["action"],
                "rollback": "complete_mock",
                "requested_handles": plan["handles"],
            },
        }
