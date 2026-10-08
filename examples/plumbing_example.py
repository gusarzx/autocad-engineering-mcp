"""Flat isometric cold-water schematic with meter, filter, valve and three fixtures."""

from _common import checked, run

from autocad_engineering_mcp.engineering.models import Equipment, Pipe, System


def build(engineering):
    checked(
        engineering.create_system(
            System(name="W1", discipline="plumbing", kind="cold_water", projection="axonometric")
        )
    )
    points = [[0, 0, 0], [1000, 0, 0], [2000, 0, 0], [3000, 0, 0], [4000, 0, 0], [5000, 0, 0]]
    checked(engineering.draw_route(Pipe(system="W1", points=points, diameter=32, material="steel")))
    for kind, mark, x in (
        ("valve", "V1", 1000),
        ("filter", "F1", 2000),
        ("water_meter", "WM1", 3000),
    ):
        checked(
            engineering.insert(
                Equipment(system="W1", position=[x, 0, 0], mark=mark), kind, "plumbing"
            )
        )
    for index, x in enumerate((3000, 4000, 5000), 1):
        checked(
            engineering.draw_route(
                Pipe(system="W1", points=[[x, 0, 0], [x, 1000, 0]], diameter=20, material="steel")
            )
        )
        checked(
            engineering.insert(
                Equipment(system="W1", position=[x, 1000, 0], mark=f"C{index}"),
                "fixture",
                "plumbing",
            )
        )
    return checked(engineering.specification("W1", position=[0, -1500]))


if __name__ == "__main__":
    run(build)
