"""Shared command-line runner for local 2D examples."""

import argparse
import json

from autocad_engineering_mcp.config import Settings
from autocad_engineering_mcp.engineering.service import EngineeringService
from autocad_engineering_mcp.server import create_server


def checked(result):
    if result.status == "error":
        raise RuntimeError(result.error)
    return result


def run(build):
    parser = argparse.ArgumentParser(description="New isolated 2D schematic; mock by default")
    parser.add_argument("--backend", choices=["mock", "com"], default="mock")
    parser.add_argument("--save", help="New DWG filename inside configured save_root (COM only)")
    args = parser.parse_args()
    _, cad = create_server(Settings(backend=args.backend))
    try:
        checked(cad.call("connect", allow_launch=False))
        checked(cad.call("create_document", units=4))
        engineering = EngineeringService(cad)
        result = build(engineering)
        if args.save:
            checked(cad.save(args.save, overwrite=False, dry_run=False))
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    finally:
        cad.adapter.close()
