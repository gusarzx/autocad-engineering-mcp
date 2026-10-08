"""In-memory test backend. Does not run AutoCAD or produce DWG files."""

import copy
import math
from typing import Any
from uuid import uuid4

from ..core.exceptions import CadError


class MockAdapter:
    """Document-scoped geometry, attributes and network metadata for tests."""

    backend = "mock"

    def __init__(self) -> None:
        self.connected = False
        self.documents: dict[str, dict] = {}
        self.active: str | None = None
        self.counter = 0

    def close(self) -> None:
        self.connected = False

    def document(self) -> dict[str, Any]:
        if not self.connected:
            raise CadError("Connect first")
        if self.active is None:
            raise CadError("No active document; create one")
        return self.documents[self.active]

    def entity(self, handle: str) -> dict[str, Any]:
        try:
            return self.document()["entities"][handle]
        except KeyError as exc:
            raise CadError(f"Unknown entity handle {handle}") from exc

    def add(self, data: dict[str, Any]) -> dict[str, Any]:
        self.counter += 1
        handle = f"{self.counter:X}"
        entity = copy.deepcopy(data)
        entity["id"] = handle
        entity["type"] = entity["type"].removeprefix("draw_")
        self.document()["entities"][handle] = entity
        self.document()["saved"] = False
        return {"object_ids": [handle], "count": 1, "data": {"entity": entity}}

    def execute(self, command: str, arguments: dict[str, Any]) -> dict[str, Any]:
        args = copy.deepcopy(arguments)
        if command == "connect":
            self.connected = True
            return {"data": {"backend": "mock", "version": "mock", "connected": True}}
        if command == "disconnect":
            self.close()
            return {"data": {"connected": False}}
        if command == "status":
            return {
                "data": {
                    "backend": "mock",
                    "connected": self.connected,
                    "version": "mock",
                    "integration_verified": False,
                }
            }
        if command == "create_document":
            if not self.connected:
                raise CadError("Connect first")
            name = f"Drawing{len(self.documents) + 1}.dwg"
            self.documents[name] = {
                "name": name,
                "document_id": uuid4().hex,
                "path": "",
                "saved": False,
                "units": args.get("units", 4),
                "layers": {
                    "0": {"name": "0", "color": 7, "linetype": "Continuous", "lineweight": -3}
                },
                "current_layer": "0",
                "blocks": {},
                "entities": {},
            }
            self.active = name
            return self.execute("active_document", {})
        if command == "list_documents":
            if not self.connected:
                raise CadError("Connect first")
            return {"data": {"documents": [self.info(d) for d in self.documents.values()]}}
        if command == "select_document":
            if args["name"] not in self.documents:
                raise CadError("Document not found")
            self.active = args["name"]
            return self.execute("active_document", {})
        doc = self.document()
        if command.startswith("pipeline_"):
            from .mock_pipelines import execute

            return execute(self, command, args)
        if command == "active_document":
            return {"data": self.info(doc)}
        if command == "get_units":
            return {"data": {"insunits": doc["units"]}}
        if command in {"open_document", "save", "save_as"}:
            raise CadError("Mock cannot read/write DWG; use a real Windows AutoCAD session")
        if command == "create_layer":
            if args["name"] in doc["layers"]:
                return {"data": {"existing": True, "layer": doc["layers"][args["name"]]}}
            doc["layers"][args["name"]] = args
            doc["saved"] = False
            return {"data": {"layer": args}}
        if command == "list_layers":
            return {"data": {"layers": list(doc["layers"].values())}}
        if command in {"set_current_layer", "set_layer", "delete_layer"}:
            name = args["name"]
            if name not in doc["layers"]:
                raise CadError("Layer not found")
            if command == "set_current_layer":
                doc["current_layer"] = name
            elif command == "set_layer":
                doc["layers"][name].update(args["properties"])
            else:
                if name in {"0", "Defpoints", doc["current_layer"]} or any(
                    e["layer"] == name for e in doc["entities"].values()
                ):
                    raise CadError("Cannot delete current, protected or nonempty layer")
                del doc["layers"][name]
            doc["saved"] = False
            return {"data": {"layer": name}}
        if command == "create_block":
            if args["name"] in doc["blocks"]:
                return {"data": {"existing": True}}
            doc["blocks"][args["name"]] = args
            doc["saved"] = False
            return {"data": {"block": args["name"]}}
        if command == "list_blocks":
            return {"data": {"blocks": list(doc["blocks"])}}
        if command == "get_attributes":
            return {"data": {"attributes": self.entity(args["handle"]).get("attributes", {})}}
        if command == "set_attributes":
            entity = self.entity(args["handle"])
            if entity["type"] != "insert_block":
                raise CadError("Entity is not a block reference")
            tags = doc["blocks"][entity["name"]]["tags"]
            if any(k not in tags for k in args["attributes"]):
                raise CadError("Unknown block attribute tag")
            entity["attributes"].update(args["attributes"])
            doc["saved"] = False
            return {"object_ids": [args["handle"]], "count": 1}
        if command == "metadata":
            self.entity(args["handle"])["metadata"] = args["metadata"]
            doc["saved"] = False
            return {"object_ids": [args["handle"]], "count": 1}
        if command == "get_entity":
            return {"data": {"entity": copy.deepcopy(self.entity(args["handle"]))}}
        if command == "get_entities":
            entities = [
                e
                for e in doc["entities"].values()
                if (not args.get("layer") or e["layer"] == args["layer"])
                and (not args.get("entity_type") or e["type"] == args["entity_type"])
                and (not args.get("mark") or e.get("attributes", {}).get("MARK") == args["mark"])
            ]
            start, limit = args.get("offset", 0), args.get("limit", 100)
            return {
                "data": {
                    "entities": copy.deepcopy(entities[start : start + limit]),
                    "total": len(entities),
                    "next_offset": start + limit if start + limit < len(entities) else None,
                }
            }
        if command == "selected_entities":
            return {
                "data": {"entities": [], "total": 0, "next_offset": None},
                "warnings": ["Mock has no interactive selection"],
            }
        if command == "bounds":
            points = []
            for e in doc["entities"].values():
                for key in ("start", "end", "position"):
                    if key in e:
                        points.append(e[key])
                points.extend(e.get("points", []))
                if "center" in e:
                    x, y, z = e["center"]
                    r = e["radius"]
                    points.extend([(x - r, y - r, z), (x + r, y + r, z)])
            return {
                "data": {
                    "min": [min(p[i] for p in points) for i in range(3)] if points else None,
                    "max": [max(p[i] for p in points) for i in range(3)] if points else None,
                },
                "warnings": ["Mock bounds approximate text, arc and block extents"],
            }
        if command.startswith("draw_") or command == "insert_block":
            if args["layer"] not in doc["layers"]:
                raise CadError("Layer not found; create it first")
            if command == "insert_block":
                if args["name"] not in doc["blocks"]:
                    raise CadError("Mock requires a defined block; external DWG is unsupported")
                if any(k not in doc["blocks"][args["name"]]["tags"] for k in args["attributes"]):
                    raise CadError("Unknown block attribute tag")
            if command == "draw_hatch":
                for handle in args["boundary_ids"]:
                    boundary = self.entity(handle)
                    if boundary["type"] != "circle" and not (
                        boundary["type"] == "polyline" and boundary.get("closed")
                    ):
                        raise CadError("Hatch requires closed polylines or circles")
            args["type"] = command
            return self.add(args)
        if command == "transform":
            return self.transform(args)
        if command == "batch":
            snapshot = copy.deepcopy(doc)
            results = []
            try:
                for operation in args["operations"]:
                    results.append(self.execute(operation["type"], operation))
            except Exception as exc:
                rolled_back = args["rollback_on_error"]
                if rolled_back:
                    self.documents[self.active] = snapshot
                return {
                    "status": "error",
                    "error": str(exc),
                    "data": {
                        "results": results,
                        "failed_index": len(results),
                        "rollback": "complete_mock" if rolled_back else "not_requested",
                    },
                }
            ids = [h for r in results for h in r.get("object_ids", [])]
            return {"object_ids": ids, "count": len(ids), "data": {"results": results}}
        raise CadError(f"Unsupported mock command: {command}")

    @staticmethod
    def info(doc: dict[str, Any]) -> dict[str, Any]:
        return {k: doc[k] for k in ("name", "path", "saved", "units", "document_id")}

    def transform(self, args: dict[str, Any]) -> dict[str, Any]:
        entities = [self.entity(h) for h in args["object_ids"]]
        mode = args["type"]
        if mode == "offset":
            raise CadError("Mock offset is not simulated; requires Windows integration")
        base, target = args["base"], args["target"]

        def point(p):
            x, y, z = (p[i] - base[i] for i in range(3))
            if mode in {"move", "copy"}:
                return tuple(p[i] + target[i] - base[i] for i in range(3))
            if mode == "scale":
                return tuple(base[i] + args["factor"] * (p[i] - base[i]) for i in range(3))
            angle = args["angle"]
            if mode == "mirror":
                angle = math.atan2(target[1] - base[1], target[0] - base[0])
                x, y = (
                    math.cos(2 * angle) * x + math.sin(2 * angle) * y,
                    math.sin(2 * angle) * x - math.cos(2 * angle) * y,
                )
            else:
                x, y = (
                    math.cos(angle) * x - math.sin(angle) * y,
                    math.sin(angle) * x + math.cos(angle) * y,
                )
            return (base[0] + x, base[1] + y, base[2] + z)

        # Validate all before the first modification.
        if mode == "mirror" and any(
            e["type"] in {"arc", "text", "mtext", "insert_block"} for e in entities
        ):
            raise CadError("Mock mirror supports line/polyline/circle only")
        ids = []
        for entity in entities:
            if mode == "delete":
                del self.document()["entities"][entity["id"]]
                ids.append(entity["id"])
                continue
            data = copy.deepcopy(entity)
            for key in ("start", "end", "position", "center"):
                if key in data:
                    data[key] = point(data[key])
            if "points" in data:
                data["points"] = [point(p) for p in data["points"]]
            if mode == "scale":
                for key in ("radius", "height", "width", "scale"):
                    if key in data:
                        data[key] *= args["factor"]
            if mode == "rotate":
                for key in ("rotation", "start_angle", "end_angle"):
                    if key in data:
                        data[key] += args["angle"]
            if mode in {"copy", "mirror"}:
                # A copied engineering object must not silently duplicate its network identity.
                data.pop("metadata", None)
                ids.extend(self.add(data)["object_ids"])
            else:
                self.document()["entities"][entity["id"]] = data
                ids.append(entity["id"])
        self.document()["saved"] = False
        return {"object_ids": ids, "count": len(ids)}
