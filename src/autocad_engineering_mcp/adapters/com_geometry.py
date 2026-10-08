"""ActiveX geometry helpers. Used only inside the COM apartment thread."""

from ..core.exceptions import CadError


def ensure_2d(entity):
    """Reject known 3D classes and geometry outside the XY plane before modification."""
    allowed = {
        "AcDbLine",
        "AcDbPolyline",
        "AcDbCircle",
        "AcDbArc",
        "AcDbText",
        "AcDbMText",
        "AcDbSpline",
        "AcDbHatch",
        "AcDbAlignedDimension",
        "AcDbAttributeDefinition",
        "AcDbAttribute",
        "AcDbBlockReference",
    }
    if entity.ObjectName not in allowed:
        raise CadError(f"Only 2D entities are allowed; got {entity.ObjectName}")
    for prop in ("StartPoint", "EndPoint", "Center", "InsertionPoint"):
        try:
            value = getattr(entity, prop)
        except Exception:
            continue
        if len(value) == 3 and value[2] != 0:
            raise CadError("Entity is outside the 2D XY plane")
    try:
        elevation = entity.Elevation
    except Exception:
        elevation = 0
    if elevation != 0:
        raise CadError("Entity has nonzero elevation")
    try:
        normal = tuple(entity.Normal)
    except Exception:
        normal = (0, 0, 1)
    if normal != (0, 0, 1):
        raise CadError("Entity is outside the 2D XY plane")
    if entity.ObjectName == "AcDbSpline":
        coordinates = entity.ControlPoints
        if any(v != 0 for v in coordinates[2::3]):
            raise CadError("Spline control points must lie in XY")


def validate_block(doc, name, depth=0, budget=None):
    """Inspect nested user block geometry; reject unknown/3D contents conservatively."""
    if depth > 8:
        raise CadError("Block nesting exceeds the 2D validation limit")
    budget = [5000] if budget is None else budget
    for entity in doc.Blocks.Item(name):
        budget[0] -= 1
        if budget[0] < 0:
            raise CadError("Block exceeds the 2D validation object budget")
        ensure_2d(entity)
        if entity.ObjectName == "AcDbBlockReference":
            validate_block(doc, entity.Name, depth + 1, budget)


def draw(doc, command, args, doubles):
    """Create editable WCS model-space entities using documented ActiveX methods."""
    space = doc.ModelSpace
    if command == "draw_line":
        entity = space.AddLine(doubles(args["start"]), doubles(args["end"]))
    elif command == "draw_polyline":
        entity = space.AddLightWeightPolyline(doubles([v for p in args["points"] for v in p[:2]]))
        entity.Elevation = args["points"][0][2]
        entity.Closed = args["closed"]
    elif command == "draw_circle":
        entity = space.AddCircle(doubles(args["center"]), args["radius"])
    elif command == "draw_arc":
        entity = space.AddArc(
            doubles(args["center"]), args["radius"], args["start_angle"], args["end_angle"]
        )
    elif command == "draw_text":
        entity = space.AddText(args["text"], doubles(args["position"]), args["height"])
        entity.Rotation = args["rotation"]
    elif command == "draw_mtext":
        entity = space.AddMText(doubles(args["position"]), args["width"], args["text"])
        entity.Height = args["height"]
        entity.Rotation = args["rotation"]
    elif command == "draw_dimension":
        entity = space.AddDimAligned(
            doubles(args["start"]), doubles(args["end"]), doubles(args["position"])
        )
    elif command == "draw_spline":
        points = args["points"]
        start = [b - a for a, b in zip(points[0], points[1], strict=False)]
        end = [b - a for a, b in zip(points[-2], points[-1], strict=False)]
        entity = space.AddSpline(
            doubles([v for p in points for v in p]), doubles(start), doubles(end)
        )
    elif command == "draw_hatch":
        import pythoncom
        from win32com.client import VARIANT

        boundaries = [doc.HandleToObject(h) for h in args["boundary_ids"]]
        for boundary in boundaries:
            ensure_2d(boundary)
            if boundary.ObjectName != "AcDbCircle" and not (
                boundary.ObjectName == "AcDbPolyline" and boundary.Closed
            ):
                raise CadError("Hatch requires closed 2D polylines or circles")
        entity = space.AddHatch(0, args["pattern"], True)
        try:
            # AppendOuterLoop must immediately follow AddHatch before other property access.
            entity.AppendOuterLoop(
                VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [boundaries[0]])
            )
            for boundary in boundaries[1:]:
                entity.AppendInnerLoop(
                    VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [boundary])
                )
            entity.PatternScale = args["scale"]
            entity.Evaluate()
        except Exception:
            entity.Delete()
            raise
    elif command == "insert_block":
        entity = space.InsertBlock(
            doubles(args["position"]),
            args["name"],
            args["scale"],
            args["scale"],
            args["scale"],
            args["rotation"],
        )
        try:
            validate_block(doc, entity.Name)
        except Exception:
            entity.Delete()
            raise
        attributes = (
            {a.TagString: a for a in entity.GetAttributes()} if entity.HasAttributes else {}
        )
        missing = set(args["attributes"]) - set(attributes)
        if missing:
            entity.Delete()
            raise CadError(f"Block lacks attribute tags: {sorted(missing)}")
        for key, value in args["attributes"].items():
            attributes[key].TextString = value
    else:
        raise CadError(f"Unsupported geometry: {command}")
    try:
        entity.Layer = args["layer"]
    except Exception:
        entity.Delete()
        raise
    return {"object_ids": [str(entity.Handle)], "count": 1}


def create_block(doc, args, doubles):
    """Original schematic rectangle/cross block with editable attributes."""
    existing = [b.Name for b in doc.Blocks]
    if args["name"] in existing:
        return {"data": {"existing": True}}
    block = doc.Blocks.Add(doubles((0, 0, 0)), args["name"])
    w, h = args["width"], args["height"]
    try:
        border = block.AddLightWeightPolyline(doubles((0, 0, w, 0, w, h, 0, h)))
        border.Closed = True
        block.AddLine(doubles((0, 0, 0)), doubles((w, h, 0)))
        block.AddLine(doubles((w, 0, 0)), doubles((0, h, 0)))
        for index, tag in enumerate(args["tags"]):
            # acAttributeModeInvisible=1 except visible MARK; no copyrighted symbols.
            block.AddAttribute(
                h / 5, 0 if tag == "MARK" else 1, tag, doubles((0, h + index * h / 4, 0)), tag, ""
            )
    except Exception:
        block.Delete()
        raise
    return {"data": {"block": args["name"], "created_block": args["name"]}}


def transform(doc, args, doubles):
    """Pre-resolve handles; allow only fixed ActiveX transformations."""
    entities = [doc.HandleToObject(h) for h in args["object_ids"]]
    for entity in entities:
        ensure_2d(entity)
        if entity.ObjectName == "AcDbBlockReference":
            validate_block(doc, entity.Name)
    handles = []
    for entity in entities:
        mode = args["type"]
        if mode == "delete":
            handles.append(str(entity.Handle))
            entity.Delete()
            continue
        if mode == "copy":
            entity = entity.Copy()
            entity.Move(doubles(args["base"]), doubles(args["target"]))
        elif mode == "move":
            entity.Move(doubles(args["base"]), doubles(args["target"]))
        elif mode == "rotate":
            entity.Rotate(doubles(args["base"]), args["angle"])
        elif mode == "scale":
            entity.ScaleEntity(doubles(args["base"]), args["factor"])
        elif mode == "mirror":
            entity = entity.Mirror(doubles(args["base"]), doubles(args["target"]))
        elif mode == "offset":
            handles.extend(str(e.Handle) for e in entity.Offset(args["distance"]))
            continue
        handles.append(str(entity.Handle))
    return {
        "object_ids": handles,
        "count": len(handles),
        "warnings": ["Transforms are not atomic; COM failure may leave partial changes"],
    }
