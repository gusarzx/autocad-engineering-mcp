"""Specialized 2D HVAC/plumbing MCP tools."""

from ..core.models import Handle, Point, Result
from ..engineering.models import Duct, Equipment, Pipe, Riser, System
from .registration import annotations, model_tool


def register(server, engineering):
    for discipline in ("hvac", "plumbing"):

        def system_handler(expected):
            def handler(request, dry_run):
                if request.discipline != expected:
                    return Result(status="error", error=f"Expected {expected} discipline")
                return engineering.create_system(request, dry_run)

            return handler

        model_tool(
            server,
            f"{discipline}_create_system",
            System,
            system_handler(discipline),
            f"Declare a {discipline} system and create its configured 2D layers.",
        )

    model_tool(
        server,
        "hvac_draw_duct",
        Duct,
        engineering.draw_route,
        "Draw a 2D centreline duct with section, airflow, elevation and persistent topology.",
    )
    model_tool(
        server,
        "plumbing_draw_pipe",
        Pipe,
        engineering.draw_route,
        "Draw a 2D pipe schematic. Logical XYZ is projected in axonometric mode; no 3D object.",
    )

    for discipline, kinds in {
        "hvac": (
            "fan",
            "ahu",
            "diffuser",
            "grille",
            "damper",
            "filter",
            "heater",
            "silencer",
            "pump",
            "radiator",
        ),
        "plumbing": (
            "valve",
            "gate_valve",
            "ball_valve",
            "check_valve",
            "pump",
            "filter",
            "water_meter",
            "fixture",
            "tee",
            "reducer",
            "cleanout",
        ),
    }.items():
        for kind in kinds:

            def insert_handler(symbol, expected):
                return lambda request, dry_run: engineering.insert(
                    request, symbol, expected, dry_run
                )

            model_tool(
                server,
                f"{discipline}_insert_{kind}",
                Equipment,
                insert_handler(kind, discipline),
                f"Insert editable 2D {kind} block with MARK/NAME/TYPE/SIZE/SYSTEM attributes.",
            )

    for discipline in ("hvac", "plumbing"):

        def riser_handler(expected):
            return lambda request, dry_run: engineering.riser(request, expected, dry_run)

        model_tool(
            server,
            f"{discipline}_create_riser",
            Riser,
            riser_handler(discipline),
            "Draw a 2D riser circle and mark; elevation remains engineering metadata.",
        )

    def label_tool(name):
        def label(handle: Handle, position: Point, dry_run: bool = False) -> Result:
            return engineering.label(handle, position, dry_run)

        server.add_tool(
            label,
            name=name,
            description="Label equipment or route from current drawing metadata.",
            annotations=annotations(),
        )

    for name in (
        "hvac_label_duct",
        "hvac_label_equipment",
        "plumbing_label_pipe",
        "plumbing_label_equipment",
    ):
        label_tool(name)

    def specification_tool(name, discipline):
        def specification(
            system: str | None = None, position: Point | None = None, dry_run: bool = False
        ) -> Result:
            return engineering.specification(system, discipline, position, dry_run)

        server.add_tool(
            specification,
            name=name,
            description="Aggregate DWG XData routes/attributed blocks. "
            "Optional editable 2D text schedule.",
            annotations=annotations(),
        )

    specification_tool("hvac_generate_specification", "hvac")
    specification_tool("plumbing_generate_specification", "plumbing")
    specification_tool("cad_generate_specification", None)

    @server.tool(annotations=annotations(read_only=True))
    def cad_get_engineering_network(system: str, limit: int = 100) -> Result:
        """Read logical nodes/edges; connections require matching route vertices."""
        if limit < 1:
            return Result(status="error", error="Limit must be positive")
        return engineering.network(system, limit)
