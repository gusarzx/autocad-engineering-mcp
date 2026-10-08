"""Isolated mock drawing fixtures; no user DWG access."""

import pytest

from autocad_engineering_mcp.adapters.mock import MockAdapter
from autocad_engineering_mcp.config import Settings
from autocad_engineering_mcp.core.service import CadService
from autocad_engineering_mcp.engineering.service import EngineeringService


@pytest.fixture
def cad(tmp_path):
    service = CadService(MockAdapter(), Settings(backend="mock", save_root=tmp_path))
    service.require("connect")
    service.require("create_document")
    return service


@pytest.fixture
def engineering(cad):
    return EngineeringService(cad)
