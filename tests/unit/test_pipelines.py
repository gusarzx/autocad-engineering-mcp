"""Pipeline behaviour on the explicitly named mock; these tests do not exercise AutoCAD."""

import copy
import math

import pytest
from pydantic import ValidationError

from autocad_engineering_mcp.config import Settings
from autocad_engineering_mcp.core.exceptions import CadError
from autocad_engineering_mcp.pipelines import models as m
from autocad_engineering_mcp.pipelines.colors import classify
from autocad_engineering_mcp.pipelines.geometry import Segment, broad_pairs, intersections
from autocad_engineering_mcp.pipelines.service import PipelineService
from autocad_engineering_mcp.server import create_server


@pytest.fixture
def service(tmp_path):
    _, cad = create_server(Settings(backend="mock", save_root=tmp_path, max_change=1))
    cad.require("connect")
    cad.require(
        "create_document", units=6
    )  # metres: new pipeline tools must not convert to millimetres
    return PipelineService(cad)


def create(service, points=((0, 0), (10, 0)), color="red", **kwargs):
    result = service.create(m.Create(color=color, points=points, **kwargs))
    assert result.status == "ok", result.error
    return result.object_ids[0]


def pipe(service, handle):
    return service.read(handle)["pipeline"]


@pytest.mark.parametrize(
    "assigned,layer,expected",
    [
        ({"method": "aci", "aci": 1}, {}, "red"),
        ({"method": "aci", "aci": 5}, {}, "blue"),
        ({"method": "by_layer"}, {"method": "aci", "aci": 5}, "blue"),
        ({"method": "by_layer"}, {"method": "rgb", "rgb": [255, 0, 0]}, "red"),
        ({"method": "rgb", "rgb": [0, 0, 255]}, {"method": "aci", "aci": 1}, "blue"),
        ({"method": "rgb", "rgb": [254, 0, 0]}, {}, None),
        ({"method": "by_block"}, {"method": "aci", "aci": 1}, None),
        ({"method": "aci", "aci": 10}, {}, None),
    ],
)
def test_exact_colour(assigned, layer, expected):
    assert classify(assigned, layer)[0] == expected


def test_create_drawing_units_layer_permissions_and_dry_run(service):
    before = copy.deepcopy(service.cad.adapter.document())
    preview = service.create(m.Create(color="blue", points=[[1, 2], [4, 6]]), True)
    assert preview.status == "dry_run"
    assert service.cad.adapter.document() == before
    denied = service.create(m.Create(color="red", points=[[0, 0], [1, 0]], layer="named"))
    assert denied.status == "error" and "allow_create_layer" in denied.error
    handle = create(service, [[1, 2], [4, 6]], "blue", layer="named", allow_create_layer=True)
    item = pipe(service, handle)
    assert item["vertices"] == [[1, 2], [4, 6]] and item["length"] == 5
    assert item["candidate"] and not item["confirmed"] and item["classification"] == "BLUE_PIPE"
    assert service.query().data["insunits"] == 6


def test_existing_layer_is_not_recoloured(service):
    service.cad.require("create_layer", name="grey", color=8, linetype="Continuous", lineweight=-3)
    handle = create(service, layer="grey")
    assert service.cad.adapter.document()["layers"]["grey"]["color"] == 8
    assert pipe(service, handle)["assigned_color"] == {"method": "aci", "aci": 1}


def test_modify_extend_move_preserve_handle_and_others(service):
    handle = create(service, [[0, 0], [10, 0], [10, 10]])
    other = create(service, [[100, 0], [110, 0]], "blue")
    untouched = copy.deepcopy(service.cad.adapter.entity(other))
    assert service.modify(m.Modify(handle=handle, points=[[0, 0], [20, 0]])).object_ids == [handle]
    result = service.extend(
        m.Extend(handle=handle, endpoint="start", points=[[0, 0], [-5, 0], [-5, 5]])
    )
    assert result.object_ids == [handle]
    assert pipe(service, handle)["vertices"] == [[-5, 5], [-5, 0], [0, 0], [20, 0]]
    service.extend(m.Extend(handle=handle, endpoint="end", points=[[25, 0], [25, 5]]))
    assert service.mutate(m.Move(handle=handle.lower(), dx=3, dy=-2), "move").object_ids == [handle]
    assert pipe(service, handle)["end"] == [28, 3]
    assert service.cad.adapter.entity(other) == untouched


def test_line_and_legacy_polyline_keep_types(service):
    service.cad.require("create_layer", name="red", color=1, linetype="Continuous", lineweight=-3)
    handle = service.cad.adapter.add(
        {"type": "draw_line", "start": [0, 0, 0], "end": [5, 0, 0], "layer": "red"}
    )["object_ids"][0]
    assert pipe(service, handle)["type"] == "LINE"
    bad = service.extend(m.Extend(handle=handle, endpoint="end", points=[[6, 1]]))
    assert bad.status == "error"
    result = service.extend(m.Extend(handle=handle, endpoint="start", points=[[-2, 0], [-4, 0]]))
    assert result.object_ids == [handle] and pipe(service, handle)["start"] == [-4, 0]
    assert (
        service.modify(m.Modify(handle=handle, points=[[0, 0], [1, 0], [1, 1]])).status == "error"
    )
    legacy = service.cad.adapter.add(
        {"type": "legacy_polyline", "points": [[0, 0, 0], [1, 0, 0]], "layer": "red"}
    )["object_ids"][0]
    assert service.modify(m.Modify(handle=legacy, points=[[2, 0], [3, 0], [3, 1]])).status == "ok"
    assert pipe(service, legacy)["type"] == "POLYLINE"


@pytest.mark.parametrize("flag,value", [("is_xref", True), ("in_model_space", False)])
def test_xref_and_paperspace_guard(service, flag, value):
    handle = create(service)
    service.cad.adapter.entity(handle)[flag] = value
    assert service.mutate(m.Move(handle=handle, dx=1, dy=0), "move").status == "error"
    assert pipe(service, handle)["start"] == [0, 0]


def test_locked_layer_preflight_is_atomic_for_selection(service):
    first, second = create(service), create(service, color="blue")
    doc = service.cad.adapter.document()
    doc["selection"] = [first, second]
    doc["layers"]["MCP_PIPE_BLUE"]["locked"] = True
    before = copy.deepcopy(doc)
    result = service.mutate(m.SelectedMove(dx=5, dy=0, confirm=True), "move", selected=True)
    assert result.status == "error" and "locked" in result.error
    assert doc == before
    assert service.create(m.Create(color="blue", points=[[1, 0], [2, 0]])).status == "error"


def test_selection_empty_paging_bulk_confirmation_and_dry_run(service):
    assert "No preselected" in service.query(selection="selected").data["message"]
    assert service.mutate(m.SelectedColor(color="blue"), "color", selected=True).status == "error"
    first, second = create(service), create(service, [[20, 0], [30, 0]])
    service.cad.adapter.document()["selection"] = [first, second]
    assert service.query(selection="selected", limit=1).data["next_offset"] == 1
    args = m.SelectedMove(dx=0, dy=-300)
    assert service.mutate(args, "move", selected=True).status == "error"
    assert service.mutate(args, "move", True, True).status == "dry_run"
    assert pipe(service, first)["start"] == [0, 0]
    assert (
        service.mutate(m.SelectedColor(color="blue", confirm=True), "color", selected=True).count
        == 2
    )
    assert service.query(color="red").count == 0


def test_delete_invalid_handle_and_engineering_protection(service):
    first, second = create(service), create(service)
    assert service.mutate(m.Delete(handle="FFFF", confirm=True), "delete").status == "error"
    assert service.mutate(m.Delete(handle=first), "delete").status == "error"
    assert service.mutate(m.Delete(handle=first), "delete", True).status == "dry_run"
    assert service.mutate(m.Delete(handle=first, confirm=True), "delete").object_ids == [first]
    assert pipe(service, second)
    service.cad.adapter.entity(second)["metadata"] = {"engineering": {"element": "pipe"}}
    for action, request in [
        ("move", m.Move(handle=second, dx=1, dy=0)),
        ("delete", m.Delete(handle=second, confirm=True)),
    ]:
        assert service.mutate(request, action).status == "error"


def test_arc_length_intersections_and_preserving_move(service):
    handle = create(service, [[-1, 0], [1, 0]])
    service.cad.adapter.entity(handle)["bulges"] = [1]
    assert pipe(service, handle)["length"] == pytest.approx(math.pi)
    assert service.modify(m.Modify(handle=handle, points=[[0, 0], [2, 0]])).status == "error"
    assert service.mutate(m.Move(handle=handle, dx=10, dy=0), "move").status == "ok"
    assert pipe(service, handle)["bulges"] == [1]
    points = intersections(Segment((-1, 0), (1, 0), 1), Segment((0, -2), (0, 2)))
    assert points == pytest.approx([(0, -1)])


def test_connection_analysis_separates_crossings_ends_and_gaps(service):
    first = create(service, [[0, 0], [10, 0], [10, 10]])
    second = create(service, [[10, 10], [20, 10]])
    create(service, [[5, -5], [5, 5]], "blue")
    create(service, [[20.5, 10], [30, 10]])
    result = service.analyze(tolerance=1)
    assert result.status == "ok", result.error
    assert result.data["totals"] == {
        "TURN": 1,
        "OPEN_END": 6,
        "CONNECTED": 1,
        "NEAR_CONNECTION": 1,
        "INTERSECTION": 1,
    }
    connected = next(f for f in result.data["findings"] if f["kind"] == "CONNECTED")
    assert {e["handle"] for e in connected["endpoints"]} == {first, second}
    assert service.analyze(tolerance=0).data["totals"].get("NEAR_CONNECTION", 0) == 0
    page = service.analyze(tolerance=1, limit=2)
    assert page.count == 2 and page.data["next_offset"] == 2


def test_self_intersection_and_closed_geometry(service):
    handle = create(service, [[0, 0], [10, 10], [0, 10], [10, 0]])
    result = service.analyze()
    assert any(f.get("self_intersection") and f["point"] == [5, 5] for f in result.data["findings"])
    service.cad.adapter.entity(handle)["closed"] = True
    assert "OPEN_END" not in service.analyze().data["totals"]
    assert (
        service.extend(m.Extend(handle=handle, endpoint="end", points=[[11, 0]])).status == "error"
    )


def test_connect_creates_bridge_retaining_inputs_and_checks_mixing(service):
    first = create(service, [[0, 0], [10, 0]])
    second = create(service, [[20, 5], [30, 5]], "blue")
    before = [copy.deepcopy(service.cad.adapter.entity(h)) for h in (first, second)]
    args = dict(first_handle=first, second_handle=second, connection_point=[15, 0], color="red")
    assert service.connect(m.Connect(**args)).status == "error"
    preview = service.connect(m.Connect(**args, allow_mixed_colors=True), True)
    assert preview.status == "dry_run"
    result = service.connect(m.Connect(**args, allow_mixed_colors=True))
    assert result.count == 1
    assert pipe(service, result.object_ids[0])["vertices"] == [[10, 0], [15, 0], [20, 5]]
    assert before == [service.cad.adapter.entity(h) for h in (first, second)]
    assert service.analyze().data["totals"]["CONNECTED"] == 2


def test_connect_ambiguous_and_already_connected(service):
    first = create(service, [[0, 0], [10, 0]])
    second = create(service, [[10, 0], [20, 0]])
    args = dict(first_handle=first, second_handle=second, color="red")
    assert service.connect(m.Connect(**args, connection_point=[5, 0])).status == "error"
    result = service.connect(m.Connect(**args, connection_point=[10, 0]))
    assert result.count == 0 and result.data["already_connected"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Ø25", 25),
        ("⌀25", 25),
        ("DN25", 25),
        ("Ду25", 25),
        ("D25", 25),
        (r"{\C1;DN32}", 32),
        ("%%c20,5", 20.5),
    ],
)
def test_diameter_labels_unconfirmed(service, text, expected):
    handle = create(service)
    service.cad.adapter.add(
        {"type": "draw_mtext", "text": text, "position": [5, 3, 0], "layer": "0"}
    )
    result = service.labels(max_distance=5)
    assert result.status == "ok", result.error
    label = result.data["labels"][0]
    assert label["diameter"] == expected and label["nearest_pipeline_handle"] == handle
    assert label["distance"] == 3 and label["confirmed"] is False
    assert service.labels(max_distance=2).data["labels"][0]["nearest_pipeline_handle"] is None


def test_label_tie_and_non_label_text(service):
    create(service, [[0, 0], [10, 0]])
    create(service, [[0, 2], [10, 2]], "blue")
    service.cad.adapter.add(
        {"type": "draw_text", "text": "DN25", "position": [5, 1, 0], "layer": "0"}
    )
    service.cad.adapter.add(
        {"type": "draw_text", "text": "Dimension25 ADN25", "position": [5, 1, 0], "layer": "0"}
    )
    labels = service.labels().data["labels"]
    assert len(labels) == 1 and labels[0]["nearest_pipeline_handle"] is None
    assert len(labels[0]["possible_pipeline_handles"]) == 2


def test_blocks_distance_and_names_are_actual(service):
    service.cad.adapter.add(
        {"type": "insert_block", "name": "Equipment_A", "position": [3, 4, 0], "layer": "0"}
    )
    service.cad.adapter.add(
        {"type": "insert_block", "name": "Other", "position": [20, 0, 0], "layer": "0"}
    )
    result = service.blocks(point=[0, 0], radius=5)
    assert result.count == 1 and result.data["blocks"][0]["distance"] == 5
    assert result.data["blocks"][0]["name"] == "Equipment_A"


def test_by_layer_rgb_and_direct_colour_query(service):
    first, second = create(service), create(service, [[20, 0], [30, 0]])
    doc = service.cad.adapter.document()
    doc["layers"]["MCP_PIPE_RED"]["color_spec"] = {"method": "rgb", "rgb": [0, 0, 255]}
    doc["entities"][first]["assigned_color"] = {"method": "by_layer"}
    assert [p["handle"] for p in service.query(color="blue").data["pipelines"]] == [first]
    assert [p["handle"] for p in service.query(color="red").data["pipelines"]] == [second]
    doc["entities"][first]["assigned_color"] = {"method": "by_block"}
    assert service.query(color="blue").count == 0


def test_varying_width_and_move_coordinate_guard(service):
    handle = create(service, [[0, 0], [5, 0], [10, 0]])
    service.cad.adapter.entity(handle)["widths"] = [[1, 1], [2, 2]]
    before = copy.deepcopy(service.cad.adapter.entity(handle))
    assert service.modify(m.Modify(handle=handle, points=[[0, 0], [20, 0]])).status == "error"
    assert service.mutate(m.Move(handle=handle, dx=1e9, dy=0), "move").status == "error"
    assert service.cad.adapter.entity(handle) == before


def test_label_response_budget_has_resumable_cursor(service):
    create(service)
    text = " ".join(["DN25"] * 20) + " " + "x" * 3500
    for i in range(2):
        service.cad.adapter.add(
            {"type": "draw_text", "text": text, "position": [5, i + 1, 0], "layer": "0"}
        )
    result = service.labels()
    assert result.status == "ok" and result.count == 20
    assert result.data["next_offset"] == 2 and not result.data.get("response_truncated")
    second = service.labels(offset=result.data["next_offset"])
    assert second.count == 20 and second.data["next_offset"] is None


def test_underlined_mtext_label_and_punctuation(service):
    create(service)
    service.cad.adapter.add(
        {"type": "draw_mtext", "text": r"\LDN25\l, Ø32.", "position": [5, 1, 0], "layer": "0"}
    )
    assert [label["diameter"] for label in service.labels().data["labels"]] == [25, 32]


async def test_all_pipeline_tools_through_public_sdk(tmp_path):
    from mcp import Client

    server, cad = create_server(Settings(backend="mock", save_root=tmp_path))
    async with Client(server) as client:

        async def call(name, **kwargs):
            result = await client.call_tool(name, kwargs)
            assert not result.is_error, result.content
            value = result.structured_content
            assert value["status"] == "ok", value
            return value

        await call("autocad_connect")
        await call("autocad_create_document")
        first = (await call("create_pipeline", color="red", points=[[0, 0], [10, 0]]))[
            "object_ids"
        ][0]
        second = (await call("create_pipeline", color="red", points=[[20, 0], [30, 0]]))[
            "object_ids"
        ][0]
        await call("get_pipelines", color="red")
        await call("modify_pipeline", handle=first, points=[[0, 0], [10, 1]])
        await call("extend_pipeline", handle=first, endpoint="end", points=[[10, 0]])
        await call("move_pipeline", handle=first, dx=0, dy=1)
        await call("set_pipeline_color", handle=first, color="red")
        cad.adapter.document()["selection"] = [first, second]
        assert (await call("get_selected_pipelines"))["count"] == 2
        await call("move_selected_pipelines", dx=0, dy=-1)
        await call("set_selected_pipelines_color", color="blue")
        await call("analyze_pipeline_connections", tolerance=2)
        await call(
            "connect_pipelines",
            first_handle=first,
            second_handle=second,
            connection_point=[15, 0],
            color="blue",
        )
        await call("find_pipe_diameter_labels")
        await call("get_nearby_blocks", point=[0, 0], radius=100)
        await call("delete_pipeline", handle=first, confirm=True)


def test_region_pagination_and_budgets(service):
    create(service)
    create(service, [[20, 0], [30, 0]], "blue")
    assert service.query(region=[19, -1, 31, 1]).count == 1
    assert service.query(region=[10, 0, 0, 10]).status == "error"
    assert service.query(limit=101).status == "error"
    assert service.query(offset=-1).status == "error"
    assert service.analyze(max_pipelines=1).status == "error"
    with pytest.raises(CadError, match="budget"):
        list(broad_pairs([(0, 0, 1, 1)] * 20, budget=5))


def test_stale_plan_document_switch_and_mock_rollback(service, monkeypatch):
    first, second = create(service), create(service)
    info = service.read(first)
    plan = service.plan("move", [info["pipeline"]], info["document_id"], dx=1, dy=0)
    service.mutate(m.Move(handle=first, dx=5, dy=0), "move")
    assert service.apply(plan, False).status == "error"
    service.cad.require("create_document", units=4)
    assert service.apply(plan, False).status == "error"
    service.cad.require("select_document", name="Drawing1.dwg")
    adapter = service.cad.adapter
    adapter.document()["selection"] = [first, second]
    before = copy.deepcopy(adapter.document())
    original = adapter.entity
    calls = 0

    def fail_after_first_change(handle):
        nonlocal calls
        calls += 1
        if calls == 9:  # query reads 4, preflight reads 2, first move reads 2, then second fails
            raise CadError("Injected adapter failure")
        return original(handle)

    monkeypatch.setattr(adapter, "entity", fail_after_first_change)
    result = service.mutate(m.SelectedMove(dx=1, dy=0, confirm=True), "move", selected=True)
    assert result.status == "error" and result.data["rollback"] == "complete_mock"
    assert adapter.document() == before


@pytest.mark.parametrize(
    "points", [[[0, 0]], [[0, 0], [0, 0]], [[0, 0], [1, 0, 1]], [[0, 0], [float("nan"), 0]]]
)
def test_invalid_points_rejected(points):
    with pytest.raises(ValidationError):
        m.Create(color="red", points=points)
