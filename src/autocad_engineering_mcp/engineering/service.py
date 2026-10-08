"""2D schematics, persistent XData records, topology and bounded specifications."""

import math
from collections import defaultdict
from typing import Any
from uuid import uuid4

from ..core.exceptions import CadError
from ..core.geometry import axonometric
from ..core.models import Batch, Block, Circle, InsertBlock, Layer, Polyline, Result, Text
from ..core.service import CadService
from .models import Duct, Equipment, Pipe, Riser, System

SYMBOLS = {
    "fan",
    "ahu",
    "damper",
    "filter",
    "silencer",
    "diffuser",
    "grille",
    "heater",
    "pump",
    "radiator",
    "valve",
    "gate_valve",
    "ball_valve",
    "check_valve",
    "water_meter",
    "tee",
    "reducer",
    "fixture",
    "cleanout",
    "riser",
}


class EngineeringService:
    """Session system declarations; network elements are persisted in each drawing."""

    def __init__(self, cad: CadService) -> None:
        self.cad = cad
        self.systems: dict[tuple[str, str], System] = {}

    def drawing_key(self) -> str:
        return self.cad.require("active_document").data["document_id"]

    def records(self) -> list[dict[str, Any]]:
        """Fail explicitly if a full bounded scan is impossible; never hide truncation."""
        records = []
        offset = 0
        while True:
            result = self.cad.entities(offset=offset, limit=self.cad.settings.page_size)
            if result.status == "error":
                raise CadError(result.error)
            if result.data.get("response_truncated"):
                raise CadError("Drawing page exceeded 128 KB; lower ACAD_MCP_PAGE_SIZE")
            records.extend(result.data["entities"])
            next_offset = result.data["next_offset"]
            if next_offset is None:
                return records
            if next_offset >= self.cad.settings.scan_limit:
                raise CadError("Drawing scan limit reached; raise ACAD_MCP_SCAN_LIMIT explicitly")
            offset = next_offset

    def create_system(self, system: System, dry_run: bool = False) -> Result:
        with self.cad.lock:
            try:
                key = (self.drawing_key(), system.name)
                if key in self.systems and self.systems[key] != system:
                    raise CadError("System name already declared with different parameters")
                for entity in self.records():
                    record = entity.get("metadata", {}).get("engineering", {})
                    existing = record.get("system", {})
                    if existing.get("name") == system.name and existing != system.model_dump():
                        raise CadError("Drawing contains a different system with this name")
                prefix = "HVAC" if system.discipline == "hvac" else "PLUMBING"
                names = [
                    f"{prefix}_{'DUCT' if prefix == 'HVAC' else 'PIPE'}",
                    f"{prefix}_EQUIPMENT",
                    "TEXT",
                ]
                profile = self.cad.profile
                result = self.cad.batch(
                    Batch(
                        operations=[
                            Layer(
                                name=profile.layer(name),
                                color=profile.layers.get(name, 7),
                                linetype=profile.linetype,
                            )
                            for name in names
                        ],
                        dry_run=dry_run,
                    )
                )
                if result.status == "ok":
                    self.systems[key] = system
                result.data["system"] = system.model_dump()
                result.warnings.append(
                    "Empty system declarations are session-local until an element is added"
                )
                return result
            except CadError as exc:
                return Result(status="error", error=str(exc))

    def get_system(self, name: str) -> System:
        key = (self.drawing_key(), name)
        if key not in self.systems:
            for entity in self.records():
                data = entity.get("metadata", {}).get("engineering", {}).get("system", {})
                if data.get("name") == name:
                    self.systems[key] = System.model_validate(data)
                    break
        if key not in self.systems:
            raise CadError("Create the engineering system first")
        return self.systems[key]

    @staticmethod
    def project(system: System, point: tuple[float, float, float]) -> tuple[float, float, float]:
        if system.projection == "axonometric":
            return axonometric(point)
        if point[2] != 0:
            raise CadError("Plan mode needs z=0; use elevation metadata or axonometric projection")
        return point

    def persist(
        self,
        result: Result,
        system: System,
        kind: str,
        parameters: dict[str, Any],
        logical_points: list[tuple[float, float, float]],
    ) -> Result:
        if result.status != "ok":
            return result
        record = {
            "schema_version": 1,
            "element_id": uuid4().hex,
            "system": system.model_dump(),
            "kind": kind,
            "parameters": parameters,
            "logical_points": logical_points,
        }
        for handle in result.object_ids:
            persisted = self.cad.call("metadata", handle=handle, metadata={"engineering": record})
            if persisted.status == "error":
                result.status = "error"
                result.error = (
                    "Geometry created but metadata could not be saved: " + persisted.error
                )
                result.warnings.append(
                    "Partial operation; inspect returned object_ids before retrying"
                )
                return result
        result.data["engineering"] = record
        return result

    def draw_route(self, route: Duct | Pipe, dry_run: bool = False) -> Result:
        with self.cad.lock:
            try:
                system = self.get_system(route.system)
                expected = "hvac" if isinstance(route, Duct) else "plumbing"
                if system.discipline != expected:
                    raise CadError("Route does not match system discipline")
                points = [self.project(system, p) for p in route.points]
                layer = "HVAC_DUCT" if expected == "hvac" else "PLUMBING_PIPE"
                result = self.cad.create(
                    Polyline(points=points, layer=self.cad.profile.layer(layer)), dry_run
                )
                parameters = route.model_dump(exclude={"points", "system"})
                parameters["length_mm"] = sum(
                    math.dist(a, b) for a, b in zip(route.points, route.points[1:], strict=False)
                )
                result.warnings.append(
                    "Duct/pipe drawn as a 2D centreline schematic; size is metadata"
                )
                return self.persist(
                    result,
                    system,
                    "duct" if expected == "hvac" else "pipe",
                    parameters,
                    route.points,
                )
            except (CadError, ValueError) as exc:
                return Result(status="error", error=str(exc))

    def insert(
        self, equipment: Equipment, kind: str, discipline: str, dry_run: bool = False
    ) -> Result:
        with self.cad.lock:
            try:
                if kind not in SYMBOLS:
                    raise CadError("Unknown schematic symbol")
                system = self.get_system(equipment.system)
                if system.discipline != discipline:
                    raise CadError("Equipment does not match system discipline")
                for entity in self.records():
                    if entity.get("attributes", {}).get("MARK") == equipment.mark:
                        raise CadError("Equipment MARK already exists in drawing")
                name = f"ACEMCP_{discipline.upper()}_{kind.upper()}"
                custom_name = self.cad.profile.symbols.get(f"{discipline}.{kind}")
                layer = "HVAC_EQUIPMENT" if discipline == "hvac" else "PLUMBING_EQUIPMENT"
                unit = self.cad.require("get_units").data["insunits"]
                from ..core.geometry import INSUNITS, MM

                if unit not in INSUNITS:
                    raise CadError("Unsupported drawing units")
                factor = 1 / MM[INSUNITS[unit]]
                attributes = {
                    "MARK": equipment.mark,
                    "NAME": equipment.name or kind,
                    "TYPE": kind,
                    "SIZE": equipment.size,
                    "SYSTEM": system.name,
                    "DESCRIPTION": equipment.description,
                }
                operations = (
                    []
                    if custom_name
                    else [Block(name=name, width=600 * factor, height=400 * factor)]
                )
                operations.append(
                    InsertBlock(
                        name=custom_name or name,
                        position=self.project(system, equipment.position),
                        layer=self.cad.profile.layer(layer),
                        attributes=attributes,
                        rotation=equipment.rotation,
                        scale=self.cad.profile.symbol_scale,
                    )
                )
                result = self.cad.batch(
                    Batch(
                        operations=operations,
                        dry_run=dry_run,
                    )
                )
                result.warnings.append(
                    "Original generic rectangle/cross symbol; no GOST conformity claimed"
                )
                return self.persist(
                    result,
                    system,
                    kind,
                    equipment.model_dump(exclude={"position", "system"}),
                    [equipment.position],
                )
            except (CadError, ValueError) as exc:
                return Result(status="error", error=str(exc))

    def riser(self, riser: Riser, discipline: str, dry_run: bool = False) -> Result:
        with self.cad.lock:
            try:
                system = self.get_system(riser.system)
                if system.discipline != discipline:
                    raise CadError("Riser discipline mismatch")
                layer = "HVAC_DUCT" if discipline == "hvac" else "PLUMBING_PIPE"
                result = self.cad.batch(
                    Batch(
                        operations=[
                            Circle(
                                center=riser.position,
                                radius=riser.diameter / 2,
                                layer=self.cad.profile.layer(layer),
                            ),
                            Text(
                                text=riser.mark,
                                position=(riser.position[0] + riser.diameter, riser.position[1], 0),
                                layer=self.cad.profile.layer("TEXT"),
                                height=self.cad.profile.text_height,
                            ),
                        ],
                        dry_run=dry_run,
                    )
                )
                # Only the circle carries network metadata; the label is an annotation.
                if result.status == "ok":
                    primary = Result(object_ids=result.object_ids[:1], count=1)
                    primary = self.persist(
                        primary,
                        system,
                        "riser",
                        riser.model_dump(exclude={"position", "system"}),
                        [riser.position],
                    )
                    if primary.status == "error":
                        result.status, result.error = primary.status, primary.error
                return result
            except (CadError, ValueError) as exc:
                return Result(status="error", error=str(exc))

    def label(
        self, handle: str, position: tuple[float, float, float], dry_run: bool = False
    ) -> Result:
        with self.cad.lock:
            try:
                entity = self.cad.require("get_entity", handle=handle).data["entity"]
                attrs = entity.get("attributes", {})
                record = entity.get("metadata", {}).get("engineering", {})
                parameters = record.get("parameters", {})
                if attrs:
                    text = " ".join(
                        str(attrs.get(key, "")) for key in ("MARK", "NAME", "SIZE")
                    ).strip()
                elif record:
                    size = (
                        f"{parameters['width']:g}x{parameters['height']:g}"
                        if parameters.get("shape") == "rectangular"
                        else f"D{parameters.get('diameter', 0):g}"
                    )
                    text = f"{record['system']['name']} {size} z={parameters.get('elevation', 0):g}"
                else:
                    raise CadError("Entity has no engineering metadata or block attributes")
                return self.cad.create(
                    Text(
                        text=text,
                        position=position,
                        layer=self.cad.profile.layer("TEXT"),
                        height=self.cad.profile.text_height,
                    ),
                    dry_run,
                )
            except CadError as exc:
                return Result(status="error", error=str(exc))

    def network(self, system_name: str, limit: int = 100) -> Result:
        with self.cad.lock:
            try:
                system = self.get_system(system_name)
                nodes, edges, elements = {}, [], []
                for entity in self.records():
                    record = entity.get("metadata", {}).get("engineering", {})
                    if record.get("system", {}).get("name") != system.name:
                        continue
                    if len(elements) >= min(limit, self.cad.settings.page_size):
                        raise CadError(
                            "Network output limit exceeded; narrow the system or raise page size"
                        )
                    elements.append({"handle": entity["id"], **record})
                    keys = []
                    for point in record["logical_points"]:
                        key = ",".join(f"{v:.3f}" for v in point)
                        nodes[key] = point
                        keys.append(key)
                    edges.extend(
                        {"from": a, "to": b, "handle": entity["id"]}
                        for a, b in zip(keys, keys[1:], strict=False)
                    )
                return self.cad.bound(
                    Result(
                        data={
                            "system": system.model_dump(),
                            "nodes": nodes,
                            "edges": edges,
                            "elements": elements,
                        },
                        warnings=[
                            "Nodes connect only at matching vertices (0.001 mm rounding); "
                            "intersections and mid-segment equipment require explicit vertices"
                        ],
                    )
                )
            except CadError as exc:
                return Result(status="error", error=str(exc))

    def specification(
        self,
        system: str | None = None,
        discipline: str | None = None,
        position: tuple[float, float, float] | None = None,
        dry_run: bool = False,
    ) -> Result:
        with self.cad.lock:
            try:
                groups = defaultdict(lambda: {"quantity": 0.0, "handles": []})
                for entity in self.records():
                    record = entity.get("metadata", {}).get("engineering", {})
                    attrs = entity.get("attributes", {})
                    if record:
                        name = record["system"]["name"]
                        if system and system != name:
                            continue
                        if discipline and record["system"]["discipline"] != discipline:
                            continue
                        params = record["parameters"]
                        kind = record["kind"]
                        size = (
                            f"{params['width']:g}x{params['height']:g}"
                            if params.get("shape") == "rectangular"
                            else str(params.get("diameter", params.get("size", "")))
                        )
                        material = params.get("material", "")
                        amount = (
                            params.get("length_mm", 1000) / 1000 if kind in {"duct", "pipe"} else 1
                        )
                        unit = "m" if kind in {"duct", "pipe"} else "pcs"
                    elif attrs and not discipline:
                        name = attrs.get("SYSTEM", "")
                        if system and system != name:
                            continue
                        kind, size, material = (
                            attrs.get("NAME", "equipment"),
                            attrs.get("SIZE", ""),
                            "",
                        )
                        amount, unit = 1, "pcs"
                    else:
                        continue
                    key = (name, kind, size, material, unit)
                    groups[key]["quantity"] += amount
                    groups[key]["handles"].append(entity["id"])
                if len(groups) > self.cad.settings.page_size:
                    raise CadError("Specification output limit exceeded; filter by system")
                rows = [
                    {
                        "system": key[0],
                        "name": key[1],
                        "size": key[2],
                        "material": key[3],
                        "unit": key[4],
                        "quantity": round(value["quantity"], 3),
                        "handles": value["handles"][: self.cad.settings.page_size],
                        "handle_count": len(value["handles"]),
                    }
                    for key, value in sorted(groups.items())
                ]
                result = Result(
                    data={"rows": rows},
                    warnings=[
                        "Counts XData routes and attributed blocks only; "
                        "arbitrary DWG lines are not interpreted",
                        "No airflow/hydraulic calculation, fitting allowance "
                        "or standards certification",
                    ],
                )
                if position is not None and rows:
                    operations = [
                        Text(
                            text="SYSTEM | NAME | SIZE | QTY | UNIT",
                            position=position,
                            height=self.cad.profile.text_height,
                            layer=self.cad.profile.layer("TEXT"),
                        )
                    ]
                    for i, row in enumerate(rows):
                        operations.append(
                            Text(
                                text=f"{row['system']} | {row['name']} | {row['size']} | "
                                f"{row['quantity']} | {row['unit']}",
                                position=(
                                    position[0],
                                    position[1] - (i + 1) * self.cad.profile.text_height * 1.5,
                                    0,
                                ),
                                height=self.cad.profile.text_height,
                                layer=self.cad.profile.layer("TEXT"),
                            )
                        )
                    drawn = self.cad.batch(Batch(operations=operations, dry_run=dry_run))
                    drawn.data["rows"] = rows
                    drawn.warnings.extend(result.warnings)
                    return self.cad.bound(drawn)
                return self.cad.bound(result)
            except CadError as exc:
                return Result(status="error", error=str(exc))
