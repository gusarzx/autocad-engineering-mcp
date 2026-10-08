"""Windows ActiveX adapter with one dedicated STA and plain-data message boundary."""

import json
import logging
import queue
import sys
from concurrent.futures import Future
from threading import Thread
from typing import Any

from ..core.exceptions import CadError
from .com_geometry import create_block, draw, transform

LOG = logging.getLogger(__name__)
XDATA_APP = "ACEMCP"


class ComAdapter:
    """Own all COM references in one thread, pump messages and release on shutdown."""

    backend = "com"

    def __init__(self, prog_id: str, expected_version: str) -> None:
        if sys.platform != "win32":
            raise CadError(
                "AutoCAD COM requires Windows; set ACAD_MCP_BACKEND=mock for development"
            )
        self.prog_id = prog_id
        self.expected_version = expected_version
        self.app = None
        self.jobs = queue.Queue()
        self.ready = Future()
        self.closed = False
        self.thread = Thread(target=self._worker, name="AutoCAD-STA", daemon=True)
        self.thread.start()
        self.ready.result()

    def _worker(self) -> None:
        try:
            import pythoncom
            import win32com.client

            self.pythoncom = pythoncom
            self.client = win32com.client
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        except Exception as exc:
            self.ready.set_exception(CadError(f"COM initialization failed: {type(exc).__name__}"))
            return
        self.ready.set_result(True)
        try:
            while True:
                pythoncom.PumpWaitingMessages()
                try:
                    job = self.jobs.get(timeout=0.05)
                except queue.Empty:
                    continue
                if job is None:
                    break
                command, arguments, future = job
                try:
                    future.set_result(self._execute(command, arguments))
                except CadError as exc:
                    future.set_exception(exc)
                except Exception as exc:
                    # No automatic retries of mutations: COM can fail after side effects.
                    code = getattr(exc, "hresult", None)
                    LOG.warning(
                        "COM command %s failed (%s, HRESULT=%s)", command, type(exc).__name__, code
                    )
                    future.set_exception(
                        CadError(
                            f"AutoCAD operation {command} failed (HRESULT={code}). "
                            "Close modal dialogs, wait for AutoCAD idle, then inspect the drawing "
                            "before retrying; partial changes are possible."
                        )
                    )
        finally:
            self.app = None
            pythoncom.CoUninitialize()

    def execute(self, command: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.closed:
            raise CadError("Adapter is closed")
        future = Future()
        self.jobs.put((command, arguments, future))
        # Deliberately no timeout: a timed-out mutation could continue in AutoCAD unnoticed.
        return future.result()

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.jobs.put(None)
            self.thread.join(timeout=5)

    def doubles(self, values: Any) -> Any:
        return self.client.VARIANT(self.pythoncom.VT_ARRAY | self.pythoncom.VT_R8, tuple(values))

    def document(self) -> Any:
        if self.app is None:
            raise CadError("Connect first")
        if self.app.Documents.Count == 0:
            raise CadError("No active document; create one")
        return self.app.ActiveDocument

    @staticmethod
    def document_info(doc: Any) -> dict[str, Any]:
        return {
            "name": doc.Name,
            "path": doc.FullName,
            "saved": bool(doc.Saved),
            "units": int(doc.GetVariable("INSUNITS")),
            "document_id": str(doc.HWND),
        }

    def _execute(self, command: str, args: dict[str, Any]) -> dict[str, Any]:
        if command == "connect":
            if self.app is None:
                try:
                    # GetActiveObject does not start a new process.
                    self.app = self.client.GetActiveObject(self.prog_id)
                except Exception as exc:
                    if not args.get("allow_launch", False):
                        raise CadError(
                            "No running AutoCAD registered in ROT. Open AutoCAD first; "
                            "launch requires allow_launch=true"
                        ) from exc
                    self.app = self.client.DispatchEx(self.prog_id)
                    self.app.Visible = True
            version = str(self.app.Version)
            if not version.startswith(self.expected_version) and not args.get(
                "allow_other_version"
            ):
                self.app = None
                raise CadError(
                    f"Expected AutoCAD {self.expected_version}; got {version}. "
                    "Other versions require allow_other_version=true"
                )
            return {
                "data": {
                    "connected": True,
                    "version": version,
                    "backend": "com",
                    "integration_verified": False,
                }
            }
        if command == "disconnect":
            self.app = None
            return {"data": {"connected": False}}
        if command == "status":
            return {
                "data": {
                    "connected": self.app is not None,
                    "backend": "com",
                    "version": str(self.app.Version) if self.app else None,
                    "integration_verified": False,
                }
            }
        if self.app is None:
            raise CadError("Connect first")
        if command == "create_document":
            doc = self.app.Documents.Add()
            doc.SetVariable("INSUNITS", args.get("units", 4))
            return {"data": self.document_info(doc)}
        if command == "open_document":
            doc = self.app.Documents.Open(args["path"], False)
            return {"data": self.document_info(doc)}
        if command == "list_documents":
            return {"data": {"documents": [self.document_info(d) for d in self.app.Documents]}}
        if command == "select_document":
            self.app.Documents.Item(args["name"]).Activate()
            return {"data": self.document_info(self.document())}
        doc = self.document()
        if command == "active_document":
            return {"data": self.document_info(doc)}
        if command == "get_units":
            return {"data": {"insunits": int(doc.GetVariable("INSUNITS"))}}
        if command == "save":
            doc.Save()
            return {"data": self.document_info(doc)}
        if command == "save_as":
            doc.SaveAs(args["path"])
            return {"data": self.document_info(doc)}
        if command == "create_layer":
            names = [layer.Name for layer in doc.Layers]
            if args["name"] in names:
                return {"data": {"existing": True}}
            layer = doc.Layers.Add(args["name"])
            try:
                layer.Color = args["color"]
                layer.Linetype = args["linetype"]
                layer.Lineweight = args["lineweight"]
            except Exception:
                layer.Delete()
                raise
            return {"data": {"layer": layer.Name, "created_layer": layer.Name}}
        if command == "list_layers":
            return {
                "data": {
                    "layers": [
                        {
                            "name": layer.Name,
                            "color": int(layer.Color),
                            "linetype": layer.Linetype,
                            "lineweight": int(layer.Lineweight),
                        }
                        for layer in doc.Layers
                    ]
                }
            }
        if command == "set_current_layer":
            doc.ActiveLayer = doc.Layers.Item(args["name"])
            return {"data": {"layer": args["name"]}}
        if command == "set_layer":
            layer = doc.Layers.Item(args["name"])
            properties = {"color": "Color", "linetype": "Linetype", "lineweight": "Lineweight"}
            for key, value in args["properties"].items():
                setattr(layer, properties[key], value)
            return {"data": {"layer": args["name"]}}
        if command == "delete_layer":
            name = args["name"]
            if name in {"0", "Defpoints", doc.ActiveLayer.Name}:
                raise CadError("Cannot delete protected or current layer")
            doc.Layers.Item(name).Delete()
            return {"data": {"layer": name}}
        if command == "create_block":
            return create_block(doc, args, self.doubles)
        if command == "list_blocks":
            return {"data": {"blocks": [b.Name for b in doc.Blocks if not b.IsLayout]}}
        if command in {"get_attributes", "set_attributes"}:
            entity = doc.HandleToObject(args["handle"])
            if entity.ObjectName != "AcDbBlockReference":
                raise CadError("Entity is not a block reference")
            attributes = (
                {a.TagString: a for a in entity.GetAttributes()} if entity.HasAttributes else {}
            )
            if command == "set_attributes":
                if set(args["attributes"]) - set(attributes):
                    raise CadError("Block lacks requested attribute tags")
                for tag, value in args["attributes"].items():
                    attributes[tag].TextString = value
            return {"data": {"attributes": {k: v.TextString for k, v in attributes.items()}}}
        if command == "metadata":
            self.set_metadata(doc, doc.HandleToObject(args["handle"]), args["metadata"])
            return {"object_ids": [args["handle"]], "count": 1}
        if command == "get_entity":
            return {"data": {"entity": self.entity_info(doc.HandleToObject(args["handle"]))}}
        if command in {"get_entities", "selected_entities"}:
            collection = (
                doc.PickfirstSelectionSet if command == "selected_entities" else doc.ModelSpace
            )
            items = []
            start, limit = args.get("offset", 0), args.get("limit", 100)
            # Cursor indexes raw model-space positions. Stop scanning after a bounded window.
            end = min(collection.Count, start + args.get("scan_limit", 10000))
            index = start
            while index < end and len(items) < limit:
                entity = collection.Item(index)
                index += 1
                if args.get("layer") and entity.Layer != args["layer"]:
                    continue
                kind = self.kind(entity.ObjectName)
                if args.get("entity_type") and kind != args["entity_type"]:
                    continue
                info = self.entity_info(entity)
                if args.get("mark") and info.get("attributes", {}).get("MARK") != args["mark"]:
                    continue
                items.append(info)
            return {
                "data": {
                    "entities": items,
                    "total_modelspace": collection.Count,
                    "next_offset": index if index < collection.Count else None,
                }
            }
        if command == "bounds":
            doc.Regen(1)
            return {
                "data": {
                    "min": list(doc.GetVariable("EXTMIN")),
                    "max": list(doc.GetVariable("EXTMAX")),
                }
            }
        if command.startswith("draw_") or command == "insert_block":
            return draw(doc, command, args, self.doubles)
        if command == "transform":
            return transform(doc, args, self.doubles)
        if command == "batch":
            return self.batch(doc, args)
        raise CadError(f"Unsupported COM command: {command}")

    @staticmethod
    def kind(name: str) -> str:
        return {
            "AcDbLine": "line",
            "AcDbPolyline": "polyline",
            "AcDbCircle": "circle",
            "AcDbArc": "arc",
            "AcDbText": "text",
            "AcDbMText": "mtext",
            "AcDbBlockReference": "insert_block",
            "AcDbAlignedDimension": "dimension",
        }.get(name, name)

    def entity_info(self, entity: Any) -> dict[str, Any]:
        info = {
            "id": str(entity.Handle),
            "type": self.kind(entity.ObjectName),
            "layer": entity.Layer,
        }
        # Access only a fixed property list; unsupported optional properties are ignored.
        for prop, key in {
            "StartPoint": "start",
            "EndPoint": "end",
            "Center": "center",
            "InsertionPoint": "position",
            "Coordinates": "coordinates",
            "Radius": "radius",
            "TextString": "text",
            "Rotation": "rotation",
            "Name": "name",
            "Closed": "closed",
            "Elevation": "elevation",
            "Normal": "normal",
        }.items():
            try:
                value = getattr(entity, prop)
                if isinstance(value, tuple):
                    info[key] = list(value[:3000])
                    if len(value) > 3000:
                        info["geometry_truncated"] = True
                elif isinstance(value, str):
                    info[key] = value[:4000]
                else:
                    info[key] = value
            except Exception:
                pass
        if entity.ObjectName == "AcDbBlockReference" and entity.HasAttributes:
            info["attributes"] = {
                a.TagString[:100]: a.TextString[:1000] for a in list(entity.GetAttributes())[:100]
            }
        try:
            codes, values = entity.GetXData(XDATA_APP)
            if codes:
                metadata = json.loads(
                    "".join(v for c, v in zip(codes, values, strict=False) if c == 1000)
                )
                if isinstance(metadata, dict):
                    info["metadata"] = metadata
        except Exception:
            pass
        return info

    def set_metadata(self, doc: Any, entity: Any, metadata: dict[str, Any]) -> None:
        encoded = json.dumps(metadata, ensure_ascii=True, separators=(",", ":"))
        if len(encoded) > 12000:
            raise CadError("Engineering metadata exceeds XData budget")
        if XDATA_APP not in [app.Name for app in doc.RegisteredApplications]:
            doc.RegisteredApplications.Add(XDATA_APP)
        chunks = [encoded[i : i + 240] for i in range(0, len(encoded), 240)]
        codes = self.client.VARIANT(
            self.pythoncom.VT_ARRAY | self.pythoncom.VT_I2, [1001] + [1000] * len(chunks)
        )
        values = self.client.VARIANT(
            self.pythoncom.VT_ARRAY | self.pythoncom.VT_VARIANT, [XDATA_APP, *chunks]
        )
        entity.SetXData(codes, values)

    def batch(self, doc: Any, args: dict[str, Any]) -> dict[str, Any]:
        results = []
        undo_started = False
        try:
            doc.StartUndoMark()
            undo_started = True
            for operation in args["operations"]:
                results.append(self._execute(operation["type"], operation))
        except Exception as exc:
            cleanup_errors = []
            if args["rollback_on_error"]:
                for result in reversed(results):
                    try:
                        for handle in reversed(result.get("object_ids", [])):
                            doc.HandleToObject(handle).Delete()
                        data = result.get("data", {})
                        if data.get("created_block"):
                            doc.Blocks.Item(data["created_block"]).Delete()
                        if data.get("created_layer"):
                            doc.Layers.Item(data["created_layer"]).Delete()
                    except Exception as cleanup_exc:
                        cleanup_errors.append(type(cleanup_exc).__name__)
            return {
                "status": "error",
                "error": str(exc)
                if isinstance(exc, CadError)
                else f"COM batch failed ({type(exc).__name__})",
                "data": {
                    "results": results,
                    "failed_index": len(results),
                    "rollback": "best_effort" if args["rollback_on_error"] else "not_requested",
                    "cleanup_errors": cleanup_errors,
                },
                "warnings": [
                    "Rollback is not guaranteed; inspect the failed operation and drawing"
                ],
            }
        finally:
            if undo_started:
                try:
                    doc.EndUndoMark()
                except Exception:
                    LOG.warning("Unable to end AutoCAD undo mark")
        ids = [h for result in results for h in result.get("object_ids", [])]
        return {
            "object_ids": ids,
            "count": len(ids),
            "data": {"results": results},
            "warnings": ["Undo mark groups operations; COM is not a database transaction"],
        }
