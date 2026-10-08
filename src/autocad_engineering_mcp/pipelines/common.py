"""Plain-data contracts shared by the real STA adapter and explicit test mock."""

import hashlib
import json
import math

from ..core.exceptions import CadError
from .colors import classify
from .geometry import bounds, boxes_overlap, segments

MAX_VERTICES = 2000
PAGE_BYTES = 110_000


def describe(
    *,
    handle,
    kind,
    vertices,
    layer,
    assigned_color,
    layer_color,
    closed=False,
    bulges=None,
    widths=None,
    length=None,
    object_id=None,
    locked=False,
    is_xref=False,
    in_model_space=True,
    engineering=False,
):
    """Build a bounded pipeline candidate; distances and coordinates are drawing units."""
    if kind not in {"LINE", "LWPOLYLINE", "POLYLINE"}:
        raise CadError("Only LINE/LWPOLYLINE/simple 2D POLYLINE candidates are supported")
    if not 2 <= len(vertices) <= MAX_VERTICES:
        raise CadError("Pipeline vertex count must be between 2 and 2000")
    if any(len(p) < 2 or any(not math.isfinite(v) or abs(v) > 1e9 for v in p) for p in vertices):
        raise CadError("Invalid pipeline coordinates")
    if any(len(p) == 3 and p[2] != 0 for p in vertices):
        raise CadError("Pipeline must lie in the 2D XY plane")
    vertices = [list(p[:2]) for p in vertices]
    if any(a == b for a, b in zip(vertices, vertices[1:], strict=False)):
        raise CadError("Pipeline contains zero-length segments")
    if closed and (vertices[-1] == vertices[0] or len({tuple(p) for p in vertices}) < 3):
        raise CadError(
            "Closed pipeline requires three distinct vertices and no zero-length closure"
        )
    count = len(vertices) if closed else len(vertices) - 1
    bulges = list(bulges or [0] * count)[:count]
    if len(bulges) != count or any(not math.isfinite(b) for b in bulges):
        raise CadError("Invalid polyline bulges")
    if any(abs(b) > 1e9 for b in bulges):
        raise CadError("Polyline bulge exceeds numerical budget")
    if widths and (
        len(widths) != count
        or any(len(w) != 2 or any(not math.isfinite(v) or v < 0 for v in w) for w in widths)
    ):
        raise CadError("Invalid segment widths")
    color, effective = classify(assigned_color, layer_color)
    item = {
        "handle": handle.upper(),
        "object_id": object_id,
        "type": kind,
        "color": color,
        "classification": f"{color.upper()}_PIPE" if color else None,
        "candidate": True,
        "confirmed": False,
        "assigned_color": assigned_color,
        "effective_color": effective,
        "layer": layer,
        "vertices": vertices,
        "start": vertices[0],
        "end": vertices[-1],
        "closed": bool(closed),
        "segment_count": count,
        "bulges": bulges,
        "widths": widths or [],
        "layer_locked": bool(locked),
        "is_xref": bool(is_xref),
        "in_model_space": bool(in_model_space),
        "engineering_metadata": bool(engineering),
    }
    item["length"] = float(length) if length is not None else sum(s.length for s in segments(item))
    if not math.isfinite(item["length"]):
        raise CadError("Nonfinite pipeline length")
    item["bounds"] = list(bounds(item))
    item["stamp"] = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
    return item


def editable(pipe, geometry_change=False):
    """Conservative mutation guard; no unlock, XREF detachment or network metadata edits."""
    if pipe["color"] is None:
        raise CadError("Handle is not a red/blue pipeline candidate")
    if pipe["layer_locked"]:
        raise CadError(f"Layer {pipe['layer']} is locked")
    if pipe["is_xref"] or not pipe["in_model_space"]:
        raise CadError("XREF and non-ModelSpace objects cannot be edited")
    if geometry_change and pipe["engineering_metadata"]:
        raise CadError("Linked engineering geometry is protected; use its engineering workflow")


def validate_plan(plan, read, document_id, max_change):
    """Recheck document identity, snapshots and safety inside the owning adapter thread."""
    if str(document_id) != plan["expected_document"]:
        raise CadError("Active document changed after preflight; retry against the intended DWG")
    handles = plan.get("handles", [])
    if plan["action"] != "create" and len(handles) > max_change and not plan.get("confirm"):
        raise CadError("Mass modification requires confirm=true")
    if plan["action"] == "delete" and not plan.get("confirm"):
        raise CadError("Deletion requires confirm=true")
    for handle in handles:
        pipe = read(handle)
        editable(pipe, plan["action"] in {"modify", "move"})
        if plan["action"] == "delete" and pipe["engineering_metadata"]:
            raise CadError("Linked engineering elements cannot be deleted through candidate tools")
        if pipe["stamp"] != plan["expected"][handle]:
            raise CadError("Pipeline changed after preflight; inspect and retry")


def paginate(collection_count, getter, args, key="pipelines"):
    """Raw-position cursor with colour/region filters and a response byte budget."""
    start, limit = args["offset"], args["limit"]
    if not 0 <= start <= collection_count:
        raise CadError("Cursor is outside the current collection")
    end = min(collection_count, start + args["scan_limit"])
    items, skipped, failures = [], 0, []
    index, byte_count = start, 0
    while index < end and len(items) < limit:
        try:
            item = getter(index)
        except CadError as exc:
            skipped += 1
            if len(failures) < 10:
                failures.append(str(exc))
            index += 1
            continue
        if item is None:
            index += 1
            continue
        size = len(json.dumps(item).encode())
        if byte_count + size > PAGE_BYTES:
            if not items:
                raise CadError("Single object exceeds response budget")
            break
        index += 1
        items.append(item)
        byte_count += size
    data = {
        key: items,
        "next_offset": index if index < collection_count else None,
        "scanned": index - start,
        "collection_count": collection_count,
        "unsupported_count": skipped,
        "unsupported_examples": failures,
    }
    if collection_count == 0 and args.get("selection") == "selected":
        data["message"] = (
            "No preselected objects. Select objects in AutoCAD first; "
            "no interactive prompt is opened."
        )
    return {"data": data}


def matches(pipe, args):
    return (
        pipe["color"] is not None
        and (args.get("color", "all") == "all" or pipe["color"] == args["color"])
        and (not args.get("layer") or pipe["layer"] == args["layer"])
        and (not args.get("region") or boxes_overlap(pipe["bounds"], args["region"]))
    )
