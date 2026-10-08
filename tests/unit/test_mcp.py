import os
import sys

import pytest
from mcp import Client, StdioServerParameters

from autocad_engineering_mcp.config import Settings
from autocad_engineering_mcp.server import create_server


async def test_schemas_and_real_stdio_protocol(tmp_path):
    server, _ = create_server(Settings(backend="mock", save_root=tmp_path))
    tools = await server.list_tools()
    assert len(tools) == 99
    assert len({t.name for t in tools}) == len(tools)
    assert all(t.input_schema and t.output_schema for t in tools)
    line = next(t for t in tools if t.name == "cad_draw_line")
    assert line.input_schema["required"] == ["start", "end"]
    batch = next(t for t in tools if t.name == "cad_execute_batch")
    assert "oneOf" in batch.input_schema["properties"]["operations"]["items"]
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "autocad_engineering_mcp"],
        env={**os.environ, "ACAD_MCP_BACKEND": "mock", "ACAD_MCP_SAVE_ROOT": str(tmp_path)},
    )
    async with Client(params) as client:
        listed = await client.list_tools()
        assert len(listed.tools) == 99
        for name in ("autocad_connect", "autocad_create_document"):
            result = await client.call_tool(name, {})
            assert result.structured_content["status"] == "ok"
        result = await client.call_tool("cad_draw_line", {"start": [0, 0], "end": [5000, 0]})
        data = result.structured_content
        assert data["status"] == "ok" and data["count"] == 1
        pipe = await client.call_tool(
            "create_pipeline", {"color": "red", "points": [[0, 0], [10, 0]]}
        )
        handle = pipe.structured_content["object_ids"][0]
        moved = await client.call_tool("move_pipeline", {"handle": handle, "dx": 2, "dy": 3})
        assert moved.structured_content["object_ids"] == [handle]
        candidates = await client.call_tool("get_pipelines", {"color": "red"})
        assert candidates.structured_content["data"]["pipelines"][0]["start"] == [2, 3]
        invalid = await client.call_tool("cad_draw_line", {"start": [0, 0], "end": [5000, 0, 10]})
        assert invalid.is_error
        save = await client.call_tool("autocad_save_as", {"path": "test.dwg", "dry_run": False})
        assert save.structured_content["status"] == "error"


def test_default_com_fails_cleanly_on_non_windows():
    if sys.platform == "win32":
        pytest.skip("Only checks non-Windows environment guard")
    from autocad_engineering_mcp.core.exceptions import CadError

    with pytest.raises(CadError, match="requires Windows"):
        create_server(Settings(backend="com"))
