import copy

import pytest

from autocad_engineering_mcp.core.exceptions import CadError
from autocad_engineering_mcp.core.models import (
    Batch,
    Block,
    Circle,
    Hatch,
    InsertBlock,
    Layer,
    Line,
    Polyline,
    Transform,
)
from autocad_engineering_mcp.core.safety import FilePolicy


def test_batch_dry_run_and_preflight_do_not_mutate(cad):
    before = copy.deepcopy(cad.adapter.document())
    result = cad.batch(
        Batch(operations=[Layer(name="TEST"), Line(start=[0, 0], end=[10, 0], layer="TEST")])
    )
    assert result.status == "dry_run"
    assert cad.adapter.document() == before
    result = cad.batch(
        Batch(
            operations=[Layer(name="TEST"), Line(start=[0, 0], end=[10, 0], layer="MISSING")],
            dry_run=False,
        )
    )
    assert result.status == "error"
    assert cad.adapter.document() == before


def test_batch_create_rollback_and_partial_reporting(cad):
    operations = [Layer(name="TEST"), Line(start=[0, 0], end=[1, 0], layer="TEST")]
    assert cad.batch(Batch(operations=operations, dry_run=False)).count == 1
    before = copy.deepcopy(cad.adapter.document())
    operations = [
        Line(start=[0, 0], end=[2, 0]),
        Block(name="NO_MARK", tags=[]),
        InsertBlock(name="NO_MARK", position=[0, 0], attributes={"MARK": "X"}),
    ]
    result = cad.batch(Batch(operations=operations, dry_run=False))
    assert result.status == "error"
    assert result.data["failed_index"] == 2
    assert result.data["rollback"] == "complete_mock"
    assert cad.adapter.document() == before
    result = cad.batch(Batch(operations=operations, dry_run=False, rollback_on_error=False))
    assert result.status == "error" and result.data["rollback"] == "not_requested"
    assert cad.adapter.document() != before


def test_batch_limits_and_unknown_units(cad):
    cad.settings.max_batch = 1
    assert cad.batch(Batch(operations=[Layer(name="A"), Layer(name="B")])).status == "error"
    cad.adapter.document()["units"] = 0
    assert cad.create(Line(start=[0, 0], end=[1, 1])).status == "error"


def test_geometry_layers_blocks_and_attributes(cad):
    result = cad.batch(
        Batch(
            operations=[
                Layer(name="CAD"),
                Block(name="SYMBOL"),
                Polyline(points=[[0, 0], [100, 0], [100, 100]], layer="CAD"),
                InsertBlock(
                    name="SYMBOL", position=[50, 0], layer="CAD", attributes={"MARK": "P1"}
                ),
            ],
            dry_run=False,
        )
    )
    assert result.status == "ok" and result.count == 2
    handle = result.object_ids[-1]
    assert cad.require("get_attributes", handle=handle).data["attributes"]["MARK"] == "P1"
    assert cad.call("delete_layer", name="CAD").status == "error"
    assert cad.call("set_attributes", handle=handle, attributes={"BAD": "x"}).status == "error"
    assert cad.entities(mark="P1").data["entities"][0]["id"] == handle


def test_hatch_validation(cad):
    line = cad.create(Line(start=[0, 0], end=[10, 0])).object_ids[0]
    assert cad.create(Hatch(boundary_ids=[line])).status == "error"
    circle = cad.create(Circle(center=[0, 0], radius=10)).object_ids[0]
    assert cad.create(Hatch(boundary_ids=[circle])).status == "ok"


def test_transform_confirmations_and_prevalidation(cad):
    handles = [cad.create(Line(start=[0, 0], end=[10, 0])).object_ids[0] for _ in range(3)]
    cad.settings.max_change = 2
    assert (
        cad.transform(Transform(type="move", object_ids=handles, target=[1, 0]), False).status
        == "error"
    )
    assert cad.transform(Transform(type="delete", object_ids=handles[:1]), False).status == "error"
    before = copy.deepcopy(cad.adapter.document())
    assert (
        cad.transform(
            Transform(type="move", object_ids=[handles[0], "FFFF"], target=[1, 0]), False
        ).status
        == "error"
    )
    assert cad.adapter.document() == before
    result = cad.transform(Transform(type="copy", object_ids=handles[:1], target=[100, 0]), False)
    assert result.object_ids[0] != handles[0]
    assert cad.require("get_entity", handle=result.object_ids[0]).data["entity"]["end"] == (
        110,
        0,
        0,
    )
    assert (
        cad.transform(Transform(type="delete", object_ids=handles, confirm=True), False).status
        == "ok"
    )


def test_pagination_and_document_isolation(cad):
    for index in range(5):
        cad.create(Line(start=[0, index], end=[10, index]))
    page = cad.entities(limit=2).data
    assert len(page["entities"]) == 2 and page["next_offset"] == 2
    assert cad.entities(offset=4, limit=2).data["next_offset"] is None
    assert cad.entities(limit=1000).status == "error"
    first = cad.require("active_document").data["name"]
    cad.require("create_document")
    assert cad.entities().data["total"] == 0
    cad.require("select_document", name=first)
    assert cad.entities().data["total"] == 5


@pytest.mark.parametrize("path", ["../escape.dwg", "drawing.txt", "CON.dwg", "file:stream.dwg"])
def test_path_policy_rejects(cad, path):
    with pytest.raises(CadError):
        cad.files.resolve(path)


def test_overwrite_backup_and_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    policy = FilePolicy(root)
    target = root / "drawing.dwg"
    target.write_bytes(b"existing")
    with pytest.raises(CadError):
        policy.prepare_save("drawing.dwg", False)
    path, backup = policy.prepare_save("drawing.dwg", True)
    assert path == target and backup.read_bytes() == b"existing"
    try:
        (root / "escape").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Platform does not permit symlinks")
    with pytest.raises(CadError):
        policy.resolve("escape/other.dwg")


def test_mock_never_creates_fake_dwg(cad):
    assert cad.save("example.dwg", False, False).status == "error"
    assert not (cad.files.root / "example.dwg").exists()
