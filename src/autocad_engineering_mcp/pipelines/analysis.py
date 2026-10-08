"""Bounded geometric observations; never infer engineering connectivity or equipment roles."""

import json
import math
import re
from collections import Counter, defaultdict

from ..core.exceptions import CadError
from ..core.models import Result
from .common import PAGE_BYTES
from .geometry import EPS, broad_pairs, intersections, same, segments


def tangent(segment, end=False):
    if segment.arc:
        _, _, angle, sweep = segment.arc
        angle += sweep if end else 0
        direction = 1 if sweep > 0 else -1
        return (-math.sin(angle) * direction, math.cos(angle) * direction)
    return (segment.end[0] - segment.start[0], segment.end[1] - segment.start[1])


def analyze(service, request):
    pipes, document, units = service.collect(request, request.max_pipelines)
    findings, endpoints, groups = [], [], defaultdict(list)

    def add(kind, **data):
        if len(findings) >= 20000:
            raise CadError("Analysis finding budget exceeded; narrow selection/layer/region")
        findings.append({"kind": kind, **data})

    for pipe in pipes:
        if not pipe["closed"]:
            for end in ("start", "end"):
                endpoint = {
                    "handle": pipe["handle"],
                    "endpoint": end,
                    "point": pipe[end],
                    "color": pipe["color"],
                }
                endpoints.append(endpoint)
                groups[tuple(pipe[end])].append(endpoint)
        edges = segments(pipe)
        for index in range(len(edges) if pipe["closed"] else len(edges) - 1):
            first, second = edges[index], edges[(index + 1) % len(edges)]
            a, b = tangent(first, True), tangent(second)
            angle = math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))
            if abs(angle) > 1e-7:
                add("TURN", handle=pipe["handle"], point=list(first.end), angle_degrees=angle)
        for index, edge in enumerate(edges):
            if edge.arc:
                add(
                    "CURVED_SEGMENT",
                    handle=pipe["handle"],
                    segment=index,
                    sweep_degrees=math.degrees(edge.arc[3]),
                )
        for i, j in broad_pairs([s.bounds for s in edges]):
            shared = [edges[i].end] if j == i + 1 else []
            if pipe["closed"] and i == 0 and j == len(edges) - 1:
                shared.append(edges[i].start)
            for point in intersections(edges[i], edges[j]):
                if any(math.dist(point, p) <= EPS for p in shared):
                    continue
                add(
                    "INTERSECTION",
                    handles=[pipe["handle"]],
                    point=list(point),
                    self_intersection=True,
                    segments=[i, j],
                    connected=False,
                )

    for point, group in groups.items():
        different = len({e["handle"] for e in group}) > 1
        if different:
            add(
                "CONNECTED",
                point=list(point),
                endpoints=group,
                mixed_colors=len({e["color"] for e in group}) > 1,
                basis="exact_endpoints",
            )
        else:
            for end in group:
                add("OPEN_END", **end)

    boxes = [
        (
            e["point"][0] - request.tolerance,
            e["point"][1] - request.tolerance,
            e["point"][0] + request.tolerance,
            e["point"][1] + request.tolerance,
        )
        for e in endpoints
    ]
    for i, j in broad_pairs(boxes):
        first, second = endpoints[i], endpoints[j]
        distance = math.dist(first["point"], second["point"])
        if first["handle"] != second["handle"] and 0 < distance <= request.tolerance:
            add("NEAR_CONNECTION", endpoints=[first, second], distance=distance, connected=False)

    pairs = list(broad_pairs([p["bounds"] for p in pipes]))
    lookup = {p["handle"]: p for p in pipes}
    for start in range(0, len(pairs), 25):
        selected = [[pipes[i]["handle"], pipes[j]["handle"]] for i, j in pairs[start : start + 25]]
        result = service.cad.require(
            "pipeline_intersections",
            pairs=selected,
            expected_document=document,
            expected={h: lookup[h]["stamp"] for pair in selected for h in pair},
        )
        for hit in result.data["intersections"]:
            first, second = lookup[hit["first_handle"]], lookup[hit["second_handle"]]
            for point in hit["points"]:
                # An approximate intersection coordinate never upgrades nearby ends to CONNECTED.
                common = [
                    e
                    for e in (first["start"], first["end"])
                    if not first["closed"]
                    and not second["closed"]
                    and any(same(e, s) for s in (second["start"], second["end"]))
                ]
                if any(math.dist(point, e) <= EPS for e in common):
                    continue
                add(
                    "INTERSECTION",
                    handles=[first["handle"], second["handle"]],
                    point=list(point),
                    self_intersection=False,
                    connected=False,
                )
    total = len(findings)
    if request.offset > total:
        raise CadError("Finding cursor is outside analysis results")
    page = findings[request.offset : request.offset + request.limit]
    return Result(
        count=len(page),
        data={
            "findings": page,
            "total_findings": total,
            "totals": dict(Counter(f["kind"] for f in findings)),
            "pipeline_count": len(pipes),
            "next_offset": request.offset + len(page)
            if request.offset + len(page) < total
            else None,
            "document_id": document,
            "insunits": units,
            "tolerance": request.tolerance,
        },
        warnings=[
            "Geometry observations on colour candidates; crossings do not imply connections",
            "Analysis is a bounded snapshot; keep the drawing unchanged while paging",
            "Self intersections use planar line/bulge math; "
            "inter-object COM analysis uses IntersectWith",
        ],
    )


DIAMETER = re.compile(
    r"(?<![\w])(?:[Ø⌀]|DN|Ду|D)\s*(\d+(?:[.,]\d+)?)(?![\w]|[.,]\d)", re.IGNORECASE
)


def plain_text(text):
    text = re.sub(r"%%[cC]|\\U\+00[Dd]8|\\U\+2300", "Ø", text)
    text = re.sub(r"\\[Pp]", " ", text)
    text = re.sub(r"\\[ACFHQTWacfhqtw][^;]*;", "", text)
    text = re.sub(r"\\[LlOoKk]", "", text).replace(r"\~", " ")
    return text.replace("{", "").replace("}", "")


def diameter_labels(service, request):
    pipes, document, units = service.collect(request, request.max_pipelines)
    result = service.cad.require("pipeline_aux", kind="texts", **service.page_args(request))
    if result.data["document_id"] != document:
        raise CadError("Active document changed during label lookup")
    edges = {p["handle"]: segments(p) for p in pipes}
    labels = []
    byte_count, comparisons = 0, 0
    for text in result.data.pop("objects"):
        matches = list(DIAMETER.finditer(plain_text(text["text"])))
        if len(matches) > 20:
            raise CadError("Too many diameter labels in one text; narrow the request")
        if matches:
            comparisons += sum(len(parts) for parts in edges.values())
            if comparisons > 2_000_000:
                raise CadError("Label distance budget exceeded; narrow region or lower page limit")
        distances = (
            sorted(
                (min(e.distance(text["position"]) for e in parts), handle)
                for handle, parts in edges.items()
            )
            if matches
            else []
        )
        near = [
            h for d, h in distances if d <= request.max_distance and abs(d - distances[0][0]) <= EPS
        ]
        text_labels = []
        for match in matches:
            diameter = float(match.group(1).replace(",", "."))
            if not math.isfinite(diameter) or not 0 < diameter <= 1e9:
                continue
            text_labels.append(
                {
                    "text_handle": text["handle"],
                    "text": text["text"],
                    "label": match.group(),
                    "diameter": diameter,
                    "position": text["position"],
                    "nearest_pipeline_handle": near[0] if len(near) == 1 else None,
                    "possible_pipeline_handles": near,
                    "distance": distances[0][0] if near else None,
                    "confirmed": False,
                }
            )
        size = len(json.dumps(text_labels).encode())
        if byte_count + size > PAGE_BYTES:
            if not labels:
                raise CadError("Single text label result exceeds budget; narrow candidate filters")
            result.data["next_offset"] = text["scan_position"]
            result.data["scanned"] = text["scan_position"] - request.offset
            break
        labels.extend(text_labels)
        byte_count += size
    result.data.update(
        labels=labels,
        insunits=units,
        max_distance=request.max_distance,
        cursor_kind="raw_modelspace_position",
    )
    result.count = len(labels)
    result.warnings.append(
        "Diameter associations are inferred, unconfirmed; no sizing calculations"
    )
    return result
