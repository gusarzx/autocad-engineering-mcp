"""stdio MCP server; all logging goes to stderr."""

import logging
import sys
from contextlib import asynccontextmanager

from mcp.server import MCPServer

from .adapters.mock import MockAdapter
from .config import Settings
from .core.exceptions import CadError
from .core.service import CadService
from .engineering.service import EngineeringService
from .pipelines.service import PipelineService
from .tools import cad, engineering, pipelines


def create_server(settings: Settings | None = None):
    """Build a server without opening AutoCAD; return service for development/tests."""
    settings = settings or Settings()
    if settings.backend == "mock":
        adapter = MockAdapter()
    else:
        from .adapters.autocad_com import ComAdapter

        adapter = ComAdapter(settings.prog_id, settings.expected_version)
    service = CadService(adapter, settings)

    @asynccontextmanager
    async def lifespan(server):
        try:
            yield service
        finally:
            adapter.close()

    server = MCPServer(
        "autocad-engineering",
        version="0.2.0",
        lifespan=lifespan,
        instructions="Local 2D engineering schematics only. Connect then select/create a document. "
        "Use dry_run to preview changes. Ask the user before confirming deletion, bulk changes, "
        "AutoCAD launch or DWG overwrite. Mock never produces DWG. COM integration is unverified. "
        "Do not claim automatic GOST/SPDS conformity.",
    )
    cad.register(server, service)
    engineering.register(server, EngineeringService(service))
    pipelines.register(server, PipelineService(service))
    return server, service


def main():
    """Console and python -m entry point."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        server, _ = create_server()
        server.run(transport="stdio")
    except (CadError, ValueError, OSError) as exc:
        logging.getLogger(__name__).error("Startup failed: %s", exc)
        raise SystemExit(1) from None
