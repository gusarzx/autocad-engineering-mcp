"""Exercise public schemas and wrappers through the SDK client against mock."""

import math

from mcp import Client

from autocad_engineering_mcp.config import Settings
from autocad_engineering_mcp.server import create_server


async def test_public_cad_geometry_layers_blocks_transforms(tmp_path):
    server, _ = create_server(Settings(backend="mock", save_root=tmp_path))
    async with Client(server) as client:

        async def call(tool_name, **arguments):
            result = await client.call_tool(tool_name, arguments)
            assert not result.is_error, result.content
            data = result.structured_content
            assert data["status"] == "ok", data
            return data

        await call("autocad_connect")
        await call("autocad_create_document")
        await call("cad_create_layer", name="CAD", color=4)
        await call("cad_set_current_layer", name="CAD")
        await call("cad_set_layer_color", name="CAD", color=3)
        await call("cad_set_layer_linetype", name="CAD", linetype="Continuous")
        await call("cad_set_layer_lineweight", name="CAD", lineweight=25)
        line = await call("cad_draw_line", start=[0, 0], end=[100, 0], layer="CAD")
        await call("cad_draw_polyline", points=[[0, 0], [100, 0], [100, 100]])
        circle = await call("cad_draw_circle", center=[100, 100], radius=50)
        await call("cad_draw_arc", center=[0, 0], radius=100, start_angle=0, end_angle=math.pi)
        await call("cad_draw_rectangle", origin=[0, 0], width=100, height=200)
        await call("cad_draw_polygon", center=[0, 0], radius=100, sides=5)
        await call("cad_draw_text", text="label", position=[0, 0])
        await call("cad_draw_mtext", text="first\nsecond", position=[0, 0])
        await call("cad_draw_spline", points=[[0, 0], [100, 100], [200, 0]])
        await call("cad_draw_hatch", boundary_ids=circle["object_ids"])
        await call("cad_draw_dimension", start=[0, 0], end=[100, 0], position=[50, 30])
        await call("cad_create_block", name="CUSTOM")
        block = await call(
            "cad_insert_block", name="CUSTOM", position=[0, 0], attributes={"MARK": "X1"}
        )
        await call(
            "cad_set_block_attributes", handle=block["object_ids"][0], attributes={"MARK": "X2"}
        )
        props = await call("cad_get_block_attributes", handle=block["object_ids"][0])
        assert props["data"]["attributes"]["MARK"] == "X2"
        copied = await call(
            "cad_copy", object_ids=line["object_ids"], base=[0, 0], target=[1000, 0]
        )
        await call("cad_move", object_ids=copied["object_ids"], base=[0, 0], target=[0, 100])
        await call("cad_rotate", object_ids=copied["object_ids"], base=[0, 0], angle=math.pi / 2)
        await call("cad_scale", object_ids=copied["object_ids"], base=[0, 0], factor=2)
        await call("cad_mirror", object_ids=copied["object_ids"], base=[0, 0], target=[100, 0])
        await call("cad_delete", object_ids=copied["object_ids"], confirm=True)
        await call("cad_delete_block_reference", object_ids=block["object_ids"], confirm=True)
        for name in (
            "cad_list_layers",
            "cad_list_blocks",
            "cad_get_entities",
            "cad_get_drawing_bounds",
            "cad_get_document_units",
            "cad_get_selected_entities",
            "autocad_get_status",
            "autocad_get_version",
            "autocad_list_documents",
            "autocad_get_active_document",
        ):
            await call(name)
        await call("cad_find_entities_by_type", entity_type="circle")
        await call("cad_find_entities_by_layer", layer="CAD")


async def test_engineering_tools_use_drawing_records(tmp_path):
    server, _ = create_server(Settings(backend="mock", save_root=tmp_path))
    async with Client(server) as client:

        async def call(tool_name, **arguments):
            result = await client.call_tool(tool_name, arguments)
            assert not result.is_error, result.content
            assert result.structured_content["status"] == "ok", result.structured_content
            return result.structured_content

        await call("autocad_connect")
        await call("autocad_create_document")
        await call("hvac_create_system", name="P1", discipline="hvac", kind="supply")
        duct = await call(
            "hvac_draw_duct", system="P1", points=[[0, 0], [6000, 0]], width=500, height=300
        )
        fan = await call("hvac_insert_fan", system="P1", position=[0, 0], mark="F1")
        await call("hvac_label_duct", handle=duct["object_ids"][0], position=[0, 500])
        await call("hvac_label_equipment", handle=fan["object_ids"][0], position=[0, 1000])
        await call("hvac_create_riser", system="P1", position=[6000, 0], mark="R1")
        await call("hvac_generate_specification", system="P1")
        await call(
            "plumbing_create_system",
            name="W1",
            discipline="plumbing",
            kind="cold_water",
            projection="axonometric",
        )
        pipe = await call(
            "plumbing_draw_pipe", system="W1", points=[[0, 0, 0], [0, 0, 3000]], diameter=25
        )
        pump = await call("plumbing_insert_pump", system="W1", position=[0, 0, 0], mark="PUMP1")
        await call("plumbing_label_pipe", handle=pipe["object_ids"][0], position=[1000, 0])
        await call("plumbing_label_equipment", handle=pump["object_ids"][0], position=[1500, 0])
        await call("plumbing_create_riser", system="W1", position=[0, 3000], mark="W-R1")
        await call("plumbing_generate_specification", system="W1")
        await call("cad_get_engineering_network", system="W1")
        await call("cad_generate_specification", position=[0, -1000])
