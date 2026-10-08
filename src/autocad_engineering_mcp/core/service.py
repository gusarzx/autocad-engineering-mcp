"""Validated service used by MCP and local Python examples."""

import json
import logging
from threading import RLock

from pydantic import ValidationError

from ..adapters.base import Adapter
from ..config import Settings
from .exceptions import CadError
from .geometry import normalize
from .models import Batch, Creation, Hatch, InsertBlock, Result, Transform
from .safety import FilePolicy

LOG = logging.getLogger(__name__)
RESPONSE_BUDGET = 128_000


class CadService:
    """Serialize whole workflows, apply safety once, preserve structured failures."""

    def __init__(self, adapter: Adapter, settings: Settings) -> None:
        self.adapter = adapter
        self.settings = settings
        self.files = FilePolicy(settings.save_root)
        self.profile = settings.drafting_profile()
        self.lock = RLock()

    def call(self, command: str, **arguments) -> Result:
        """Return bounded, structured domain failures; leave programmer errors visible."""
        with self.lock:
            try:
                LOG.info("CAD operation %s backend=%s", command, self.adapter.backend)
                return self.bound(Result.model_validate(self.adapter.execute(command, arguments)))
            except (CadError, ValidationError, OSError) as exc:
                return Result(status="error", error=str(exc))

    def require(self, command: str, **arguments) -> Result:
        result = self.call(command, **arguments)
        if result.status == "error":
            raise CadError(result.error)
        if result.data.get("response_truncated"):
            raise CadError("Internal read exceeded response budget; narrow the drawing/request")
        return result

    @staticmethod
    def bound(result: Result) -> Result:
        """Preserve status and handles after mutation, but omit oversized response details."""
        if len(result.model_dump_json().encode("utf-8")) > RESPONSE_BUDGET:
            result.data = {"response_truncated": True}
            result.warnings.append(
                "Response details exceeded 128 KB and were omitted; "
                "use smaller page size or a narrower request. "
                "Operation status and object_ids remain authoritative."
            )
        return result

    def prepare(self, operation: Creation) -> dict:
        data = operation.model_dump()
        if isinstance(operation, Hatch):
            for handle in operation.boundary_ids:
                entity = self.require("get_entity", handle=handle).data["entity"]
                if entity["type"] != "circle" and not (
                    entity["type"] == "polyline" and entity.get("closed")
                ):
                    raise CadError("Hatch requires closed 2D polylines or circles")
        if isinstance(operation, InsertBlock) and (
            operation.name.lower().endswith(".dwg")
            or "/" in operation.name
            or "\\" in operation.name
        ):
            path = self.files.resolve(operation.name)
            if not path.is_file():
                raise CadError("User block DWG not found inside save_root")
            data["name"] = str(path)
        if "units" in data:
            units = self.require("get_units").data["insunits"]
            data = normalize(data, units)
        return data

    def create(self, operation: Creation, dry_run: bool = False) -> Result:
        return self.batch(Batch(operations=[operation], dry_run=dry_run))

    def batch(self, request: Batch) -> Result:
        with self.lock:
            try:
                if len(request.operations) > self.settings.max_batch:
                    raise CadError(f"Batch exceeds configured limit {self.settings.max_batch}")
                operations = [self.prepare(op) for op in request.operations]
                if len(json.dumps(operations).encode("utf-8")) > RESPONSE_BUDGET:
                    raise CadError("Normalized batch plan exceeds 128 KB; split the batch")
                layers = {x["name"] for x in self.require("list_layers").data["layers"]}
                blocks = set(self.require("list_blocks").data["blocks"])
                for index, op in enumerate(operations):
                    if op["type"] == "create_layer":
                        layers.add(op["name"])
                    elif op["type"] == "create_block":
                        blocks.add(op["name"])
                    else:
                        if op["layer"] not in layers:
                            raise CadError(f"Operation {index}: layer {op['layer']} does not exist")
                        if op["type"] == "insert_block" and not op["name"].lower().endswith(".dwg"):
                            if op["name"] not in blocks:
                                raise CadError(
                                    f"Operation {index}: block {op['name']} does not exist"
                                )
                if request.dry_run:
                    return Result(
                        status="dry_run",
                        data={"operations": operations, "operation_count": len(operations)},
                        warnings=["Read-only preflight; COM-specific failures cannot be predicted"],
                    )
                return self.call(
                    "batch", operations=operations, rollback_on_error=request.rollback_on_error
                )
            except (CadError, OSError, ValidationError) as exc:
                return Result(status="error", error=str(exc))

    def transform(self, request: Transform, dry_run: bool) -> Result:
        with self.lock:
            try:
                if len(request.object_ids) > self.settings.max_change and not request.confirm:
                    raise CadError("Mass modification requires explicit confirm=true")
                if request.type == "delete" and not request.confirm:
                    raise CadError("Deletion requires explicit confirm=true")
                for handle in request.object_ids:
                    info = self.require("get_entity", handle=handle).data["entity"]
                    if info["type"] not in {
                        "line",
                        "polyline",
                        "circle",
                        "arc",
                        "text",
                        "mtext",
                        "dimension",
                        "spline",
                        "hatch",
                        "insert_block",
                    }:
                        raise CadError("Only supported 2D entities can be modified")
                    for key in ("start", "end", "center", "position"):
                        point = info.get(key)
                        if point and len(point) == 3 and point[2] != 0:
                            raise CadError("Existing entity is outside the 2D XY plane")
                    if info.get("elevation", 0) != 0 or info.get("normal", [0, 0, 1]) != [0, 0, 1]:
                        raise CadError("Existing entity is not in the 2D XY plane")
                    if info.get("metadata", {}).get("engineering") and request.type in {
                        "move",
                        "rotate",
                        "scale",
                        "copy",
                        "offset",
                        "mirror",
                    }:
                        raise CadError(
                            "Transform of linked engineering elements would invalidate "
                            "network metadata; recreate through engineering tools"
                        )
                data = normalize(request.model_dump(), self.require("get_units").data["insunits"])
                if dry_run:
                    return Result(status="dry_run", data={"operation": data})
                return self.call("transform", **data)
            except CadError as exc:
                return Result(status="error", error=str(exc))

    def save(self, path: str | None, overwrite: bool, dry_run: bool) -> Result:
        with self.lock:
            try:
                if self.adapter.backend == "mock":
                    raise CadError(
                        "Mock cannot save a DWG; Windows AutoCAD integration is unverified"
                    )
                if path is None:
                    path = self.require("active_document").data["path"]
                    if not path:
                        raise CadError("New drawing requires save_as with an explicit path")
                target = self.files.resolve(path)
                if target.exists() and not overwrite:
                    raise CadError("Existing DWG requires explicit overwrite=true")
                if dry_run:
                    return Result(status="dry_run", data={"path": str(target)})
                target, backup = self.files.prepare_save(str(target), overwrite)
                result = self.call("save_as", path=str(target))
                result.data["backup"] = str(backup) if backup else None
                return result
            except (CadError, OSError) as exc:
                return Result(status="error", error=str(exc))

    def entities(
        self, *, layer=None, entity_type=None, mark=None, offset=0, limit=100, selected=False
    ) -> Result:
        if offset < 0 or not 1 <= limit <= self.settings.page_size:
            return Result(status="error", error="Pagination exceeds configured limits")
        return self.call(
            "selected_entities" if selected else "get_entities",
            layer=layer,
            entity_type=entity_type,
            mark=mark,
            offset=offset,
            limit=limit,
            scan_limit=self.settings.scan_limit,
        )
