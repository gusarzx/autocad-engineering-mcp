"""ActiveX property/method contracts with Python doubles. No AutoCAD, Windows or COM runtime."""

import pytest

from autocad_engineering_mcp.adapters import com_pipelines as com
from autocad_engineering_mcp.config import Settings
from autocad_engineering_mcp.core.service import CadService
from autocad_engineering_mcp.pipelines import models as m
from autocad_engineering_mcp.pipelines.geometry import segments
from autocad_engineering_mcp.pipelines.service import PipelineService


class Colour:
    def __init__(self, method=195, index=1, rgb=(255, 0, 0)):
        self.ColorMethod, self.ColorIndex = method, index
        self.Red, self.Green, self.Blue = rgb

    def SetRGB(self, r, g, b):
        self.ColorMethod = 194
        self.Red, self.Green, self.Blue = r, g, b


class Layer:
    def __init__(self, collection, name, index):
        self.collection, self.Name, self.Lock = collection, name, False
        self.Color = index

    @property
    def Color(self):
        return self.TrueColor.ColorIndex

    @Color.setter
    def Color(self, value):
        self.TrueColor = Colour(195, value)

    def Delete(self):
        del self.collection.items[self.Name]


class Layers:
    def __init__(self):
        self.items = {}
        self.Add("0").Color = 7
        self.Add("pipes").Color = 1

    def Item(self, name):
        return self.items[name]

    def Add(self, name):
        if name in self.items:
            raise RuntimeError("Layer exists")
        self.items[name] = Layer(self, name, 7)
        return self.items[name]


class Collection:
    ObjectID = 100
    IsXRef = False

    def __init__(self, doc):
        self.doc = doc
        self.objects = []

    @property
    def Count(self):
        return len(self.objects)

    def Item(self, index):
        return self.objects[index]

    def AddLightWeightPolyline(self, coordinates):
        entity = Entity(self.doc, coordinates)
        self.objects.append(entity)
        return entity


class Entity:
    def __init__(self, doc, coordinates, kind="AcDbPolyline"):
        self.doc = doc
        doc.counter += 1
        self.Handle, self.ObjectID, self.OwnerID = f"{doc.counter:X}", doc.counter, 100
        self.ObjectName, self.Layer, self.Closed, self.Type = kind, "pipes", False, 0
        self.Normal, self.Elevation = (0, 0, 1), 0
        self.coordinates = list(coordinates)
        self.TrueColor = Colour(192)
        self.bulges, self.widths = {}, {}
        self.fail_coordinates_once, self.fail_update_once, self.fail_delete = False, False, False
        self.intersection_calls = []
        self.deleted = False

    @property
    def Coordinates(self):
        return tuple(self.coordinates)

    @Coordinates.setter
    def Coordinates(self, value):
        self.coordinates = list(value)
        if self.fail_coordinates_once:
            self.fail_coordinates_once = False
            raise RuntimeError("Coordinate write failed after side effect")

    @property
    def Color(self):
        return self.TrueColor.ColorIndex

    @Color.setter
    def Color(self, value):
        self.TrueColor = Colour(192 if value == 256 else 193 if value == 0 else 195, value)

    def points(self):
        stride = 3 if self.ObjectName == "AcDb2dPolyline" else 2
        return [self.coordinates[i : i + 2] for i in range(0, len(self.coordinates), stride)]

    @property
    def Length(self):
        vertices = self.points()
        count = len(vertices) if self.Closed else len(vertices) - 1
        return sum(
            s.length
            for s in segments(
                {
                    "vertices": vertices,
                    "closed": self.Closed,
                    "bulges": [self.GetBulge(i) for i in range(count)],
                }
            )
        )

    def GetBulge(self, index):
        return self.bulges.get(index, 0)

    def SetBulge(self, index, value):
        self.bulges[index] = value

    def GetWidth(self, index):
        return self.widths.get(index, (0, 0))

    def SetWidth(self, index, start, end):
        self.widths[index] = (start, end)

    def GetXData(self, app):
        assert app == "ACEMCP"
        return None, None

    def Update(self):
        if self.fail_update_once:
            self.fail_update_once = False
            raise RuntimeError("Injected update failure")

    def Move(self, start, end):
        assert start == (0, 0, 0)
        stride = 3 if self.ObjectName == "AcDb2dPolyline" else 2
        for i in range(0, len(self.coordinates), stride):
            self.coordinates[i] += end[0]
            self.coordinates[i + 1] += end[1]

    def Delete(self):
        self.doc.ModelSpace.objects.remove(self)
        self.deleted = True
        if self.fail_delete:
            raise RuntimeError("Delete failed after side effect")

    def IntersectWith(self, other, option):
        self.intersection_calls.append((other.Handle, option))
        return (5, 0, 0)


class Document:
    def __init__(self):
        self.counter = 0
        self.Layers = Layers()
        self.ModelSpace = Collection(self)
        self.PickfirstSelectionSet = Collection(self)
        self.marks = []

    def HandleToObject(self, handle):
        return next(e for e in self.ModelSpace.objects if e.Handle == handle)

    def ObjectIDToObject(self, owner):
        assert owner == 100
        return self.ModelSpace

    def StartUndoMark(self):
        self.marks.append("start")

    def EndUndoMark(self):
        self.marks.append("end")


class AdapterDouble:
    backend = "com"

    def __init__(self):
        self.doc = Document()

    def document(self):
        return self.doc

    def document_info(self, doc):
        assert doc is self.doc
        return {"document_id": "test-document", "units": 6}

    def doubles(self, values):
        return tuple(values)

    def execute(self, command, arguments):
        if command == "active_document":
            return {"data": self.document_info(self.doc)}
        return com.execute(self, command, arguments)

    def close(self):
        pass


@pytest.fixture
def service(tmp_path):
    return PipelineService(
        CadService(AdapterDouble(), Settings(backend="mock", save_root=tmp_path))
    )


def seed(service, coordinates=(0, 0, 10, 0), kind="AcDbPolyline"):
    doc = service.cad.adapter.doc
    entity = Entity(doc, coordinates, kind)
    doc.ModelSpace.objects.append(entity)
    return entity


def test_com_contract_reads_exact_truecolor_and_legacy_ocs(service):
    entity = seed(service, (0, 0, 99, 10, 0, 99), "AcDb2dPolyline")
    service.cad.adapter.doc.Layers.Item("pipes").TrueColor = Colour(194, rgb=(0, 0, 255))
    pipe = service.read(entity.Handle)["pipeline"]
    assert pipe["vertices"] == [[0, 0], [10, 0]]  # ignored legacy OCS Z, not elevation
    assert pipe["color"] == "blue" and pipe["object_id"] == str(entity.ObjectID)
    entity.TrueColor = Colour(194, rgb=(254, 0, 0))
    assert service.query().count == 0
    entity.TrueColor = Colour(195, 1)
    entity.Normal = (0, 1, 0)
    assert service.query().data["unsupported_count"] == 1
    assert service.analyze().status == "error"


def test_com_contract_same_handle_route_and_straight_widths(service):
    entity = seed(service)
    entity.widths[0] = (2, 2)
    result = service.modify(m.Modify(handle=entity.Handle, points=[[0, 0], [20, 0], [20, 10]]))
    assert result.object_ids == [entity.Handle]
    assert entity.Coordinates == (0, 0, 20, 0, 20, 10)
    assert entity.GetWidth(1) == (2, 2)
    assert service.cad.adapter.doc.marks == ["start", "end"]


def test_com_contract_rolls_back_failed_geometry_write(service):
    entity = seed(service)
    before = service.read(entity.Handle)["pipeline"]
    entity.fail_coordinates_once = True
    result = service.modify(m.Modify(handle=entity.Handle, points=[[0, 0], [30, 0], [30, 5]]))
    assert result.status == "error" and result.data["rollback"] == "restored"
    assert service.read(entity.Handle)["pipeline"] == before
    assert service.cad.adapter.doc.marks == ["start", "end"]


def test_com_contract_bulk_colour_rollback_restores_rgb_and_bylayer(service):
    first, second = seed(service), seed(service, (20, 0, 30, 0))
    first.TrueColor = Colour(194, rgb=(255, 0, 0))
    doc = service.cad.adapter.doc
    doc.PickfirstSelectionSet.objects = [first, second]
    second.fail_update_once = True
    result = service.mutate(m.SelectedColor(color="blue"), "color", selected=True)
    assert result.status == "error" and result.data["rollback"] == "restored"
    assert first.TrueColor.ColorMethod == 194 and first.TrueColor.Red == 255
    assert second.TrueColor.ColorMethod == 192


def test_com_contract_creation_rollback_cleans_only_new_layer(service):
    adapter = service.cad.adapter
    original = adapter.doc.ModelSpace.AddLightWeightPolyline

    def fail_on_update(coordinates):
        entity = original(coordinates)
        entity.fail_update_once = True
        return entity

    adapter.doc.ModelSpace.AddLightWeightPolyline = fail_on_update
    result = service.create(m.Create(color="red", points=[[0, 0], [10, 0]]))
    assert result.status == "error" and result.data["rollback"] == "restored"
    assert adapter.doc.ModelSpace.Count == 0
    assert set(adapter.doc.Layers.items) == {"0", "pipes"}


def test_com_contract_restoration_failure_is_reported(service, monkeypatch):
    entity = seed(service)
    calls = 0

    def fail_update_twice():
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise RuntimeError("Injected mutation and restoration failure")

    monkeypatch.setattr(entity, "Update", fail_update_twice)
    result = service.mutate(m.Move(handle=entity.Handle, dx=5, dy=0), "move")
    assert result.status == "error" and result.data["rollback"] == "failed"
    assert result.data["rollback_errors"] and result.data["requested_handles"] == [entity.Handle]


def test_com_contract_delete_reports_unrestorable_handle(service):
    entity = seed(service)
    entity.fail_delete = True
    result = service.mutate(m.Delete(handle=entity.Handle, confirm=True), "delete")
    assert result.status == "error" and result.data["rollback"] == "unavailable_for_delete"
    assert entity.deleted


def test_com_contract_calls_native_intersectwith(service):
    first, second = seed(service), seed(service, (5, -5, 5, 5))
    result = service.analyze(tolerance=0)
    assert result.status == "ok", result.error
    assert result.data["totals"]["INTERSECTION"] == 1
    assert first.intersection_calls == [(second.Handle, 0)]


def test_com_contract_locked_destination_and_readonly_preview(service):
    doc = service.cad.adapter.doc
    before = set(doc.Layers.items)
    assert service.create(m.Create(color="red", points=[[0, 0], [1, 0]]), True).status == "dry_run"
    assert set(doc.Layers.items) == before and doc.marks == []
    doc.Layers.Item("pipes").Lock = True
    assert (
        service.create(m.Create(color="red", layer="pipes", points=[[0, 0], [1, 0]])).status
        == "error"
    )
    assert doc.ModelSpace.Count == 0 and doc.marks == []
