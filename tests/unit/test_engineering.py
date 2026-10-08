from autocad_engineering_mcp.core.models import Transform
from autocad_engineering_mcp.engineering.models import Duct, Equipment, Pipe, System
from autocad_engineering_mcp.engineering.service import EngineeringService


def test_hvac_end_to_end_network_specification_and_reload(engineering, cad):
    assert (
        engineering.create_system(System(name="P1", discipline="hvac", kind="supply")).status
        == "ok"
    )
    assert (
        engineering.insert(
            Equipment(system="P1", position=[0, 0], mark="P1-AHU"), "ahu", "hvac"
        ).status
        == "ok"
    )
    result = engineering.draw_route(
        Duct(system="P1", points=[[0, 0], [6000, 0]], width=500, height=300)
    )
    assert result.status == "ok"
    assert (
        engineering.insert(
            Equipment(system="P1", position=[6000, 0], mark="R1"), "grille", "hvac"
        ).status
        == "ok"
    )
    network = engineering.network("P1")
    assert len(network.data["nodes"]) == 2 and len(network.data["edges"]) == 1
    rows = engineering.specification("P1").data["rows"]
    assert next(row for row in rows if row["name"] == "duct")["quantity"] == 6
    fresh = EngineeringService(cad)
    assert fresh.network("P1").status == "ok"
    assert fresh.specification("P1").data["rows"] == rows
    transform = Transform(type="move", object_ids=result.object_ids, target=[100, 0])
    assert cad.transform(transform, False).status == "error"
    assert engineering.label(result.object_ids[0], [0, 500]).status == "ok"


def test_plumbing_axonometry_and_unit_independent_lengths(engineering, cad):
    cad.adapter.document()["units"] = 6
    assert (
        engineering.create_system(
            System(name="W1", discipline="plumbing", kind="cold_water", projection="axonometric")
        ).status
        == "ok"
    )
    result = engineering.draw_route(
        Pipe(system="W1", points=[[0, 0, 0], [0, 0, 3000]], diameter=25)
    )
    entity = cad.require("get_entity", handle=result.object_ids[0]).data["entity"]
    assert entity["points"] == [(0, 0, 0), (0, 3, 0)]
    equipment = engineering.insert(
        Equipment(system="W1", position=[0, 0, 3000], mark="WM1"), "water_meter", "plumbing"
    )
    assert equipment.status == "ok"
    assert engineering.specification("W1").data["rows"][0]["quantity"] == 3


def test_engineering_dry_run_and_duplicates(engineering, cad):
    system = System(name="P1", discipline="hvac", kind="supply")
    assert engineering.create_system(system, dry_run=True).status == "dry_run"
    assert (
        engineering.draw_route(
            Duct(system="P1", points=[[0, 0], [100, 0]], width=50, height=30)
        ).status
        == "error"
    )
    engineering.create_system(system)
    equipment = Equipment(system="P1", position=[0, 0], mark="A1")
    assert engineering.insert(equipment, "fan", "hvac", True).status == "dry_run"
    assert cad.entities().data["total"] == 0
    assert engineering.insert(equipment, "fan", "hvac").status == "ok"
    assert engineering.insert(equipment, "fan", "hvac").status == "error"
    assert engineering.insert(equipment, "pump", "plumbing").status == "error"


def test_scan_limit_fails_instead_of_partial_spec(engineering, cad):
    engineering.create_system(System(name="P1", discipline="hvac", kind="supply"))
    for index in range(3):
        engineering.draw_route(
            Duct(system="P1", points=[[0, index], [1000, index]], width=50, height=30)
        )
    cad.settings.page_size = 1
    cad.settings.scan_limit = 1
    assert engineering.specification().status == "error"
