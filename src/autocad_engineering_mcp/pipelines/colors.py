"""Exact ACI/TrueColor classification; ByBlock cannot be inferred from a layer."""

ACI = {"red": 1, "blue": 5}
RGB = {"red": (255, 0, 0), "blue": (0, 0, 255)}
# Values documented in Autodesk's AcColorMethod enum. No nearest-colour matching.
METHODS = {192: "by_layer", 193: "by_block", 194: "rgb", 195: "aci"}


def color_spec(source) -> dict:
    """Read a COM colour on the STA thread; TrueColor is authoritative."""
    color = source.TrueColor
    method = METHODS.get(int(color.ColorMethod), "unknown")
    if method == "rgb":
        return {"method": method, "rgb": [int(color.Red), int(color.Green), int(color.Blue)]}
    if method == "aci":
        return {"method": method, "aci": int(color.ColorIndex)}
    return {"method": method}


def classify(assigned: dict, layer_color: dict) -> tuple[str | None, dict]:
    """Return red/blue only for exact effective colours, including layer RGB."""
    effective = layer_color if assigned.get("method") == "by_layer" else assigned
    for name in ACI:
        if effective.get("method") == "aci" and effective.get("aci") == ACI[name]:
            return name, effective
        if effective.get("method") == "rgb" and tuple(effective.get("rgb", [])) == RGB[name]:
            return name, effective
    return None, effective
