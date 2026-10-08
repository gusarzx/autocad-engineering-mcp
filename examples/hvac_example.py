"""Supply AHU, trunk, four branches and grilles; all output geometry is 2D."""

from _common import checked, run

from autocad_engineering_mcp.engineering.models import Duct, Equipment, System


def build(engineering):
    checked(engineering.create_system(System(name="P1", discipline="hvac", kind="supply")))
    checked(
        engineering.insert(
            Equipment(system="P1", position=[0, 0], mark="P1", name="AHU"), "ahu", "hvac"
        )
    )
    checked(
        engineering.draw_route(
            Duct(
                system="P1",
                points=[[0, 0], [1500, 0], [3000, 0], [4500, 0], [6000, 0]],
                width=500,
                height=300,
            )
        )
    )
    for index, x in enumerate((1500, 3000, 4500, 6000), 1):
        checked(
            engineering.draw_route(
                Duct(system="P1", points=[[x, 0], [x, 2000]], width=250, height=150)
            )
        )
        checked(
            engineering.insert(
                Equipment(system="P1", position=[x, 2000], mark=f"R{index}"), "grille", "hvac"
            )
        )
    return checked(engineering.specification("P1", position=[0, -1000]))


if __name__ == "__main__":
    run(build)
