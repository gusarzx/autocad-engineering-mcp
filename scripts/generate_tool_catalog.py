"""Generate docs from registered public tool descriptions without AutoCAD."""

import asyncio
from pathlib import Path

from autocad_engineering_mcp.config import Settings
from autocad_engineering_mcp.server import create_server


async def main():
    server, service = create_server(Settings(backend="mock"))
    try:
        tools = await server.list_tools()
        lines = [
            "# MCP tools",
            "",
            f"{len(tools)} registered tools. Generated from the actual server.",
            "",
            "COM implementations require Windows verification. Mock evidence is separate.",
            "All geometry is 2D XY; engineering axonometry is a flat projection.",
            "",
            "| Tool | Description |",
            "| --- | --- |",
        ]
        for tool in tools:
            description = (tool.description or "").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{tool.name}` | {description} |")
        destination = Path(__file__).resolve().parents[1] / "docs" / "TOOLS.md"
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    finally:
        service.adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
