"""Opt-in Windows smoke scenario. Never edits the user's active drawing."""

import os
import sys

import pytest

pytestmark = [
    pytest.mark.autocad,
    pytest.mark.skipif(
        sys.platform != "win32" or os.environ.get("ACAD_MCP_RUN_INTEGRATION") != "1",
        reason="Requires Windows, running AutoCAD and explicit ACAD_MCP_RUN_INTEGRATION=1",
    ),
]


def test_isolated_new_document(tmp_path):
    from autocad_engineering_mcp.config import Settings
    from autocad_engineering_mcp.core.models import Batch, Block, InsertBlock, Layer, Line, Polyline
    from autocad_engineering_mcp.server import create_server

    _, cad = create_server(Settings(backend="com", save_root=tmp_path))
    try:
        assert cad.call("connect", allow_launch=False).status == "ok"
        # Documents.Add is the first mutation; no existing document is modified.
        assert cad.call("create_document", units=4).status == "ok"
        result = cad.batch(
            Batch(
                operations=[
                    Layer(name="MCP_TEST"),
                    Block(name="MCP_TEST_BLOCK"),
                    Line(start=[0, 0], end=[1000, 0], layer="MCP_TEST"),
                    Polyline(points=[[0, 0], [500, 500], [1000, 500]], layer="MCP_TEST"),
                    InsertBlock(
                        name="MCP_TEST_BLOCK", position=[1000, 0], attributes={"MARK": "T1"}
                    ),
                ],
                dry_run=False,
            )
        )
        assert result.status == "ok" and result.count == 3
        assert cad.entities().status == "ok"
        assert cad.save("integration.dwg", False, False).status == "ok"
        assert (tmp_path / "integration.dwg").stat().st_size > 0
        # Keep the new test drawing open, so users can inspect it; never close user files.
    finally:
        cad.adapter.close()
