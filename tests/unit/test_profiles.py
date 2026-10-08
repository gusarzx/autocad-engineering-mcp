import pytest
from pydantic import ValidationError

from autocad_engineering_mcp.config import Profile
from autocad_engineering_mcp.core.exceptions import CadError
from autocad_engineering_mcp.core.geometry import normalize
from autocad_engineering_mcp.core.models import Block, Line
from autocad_engineering_mcp.engineering.models import Equipment, System


def test_profile_alias_and_user_definition(engineering, cad):
    cad.profile = Profile(
        layer_names={"HVAC_EQUIPMENT": "OV_DEVICES", "TEXT": "OV_TEXT"},
        symbols={"hvac.fan": "USER_FAN"},
    )
    assert cad.create(Block(name="USER_FAN")).status == "ok"
    engineering.create_system(System(name="P1", discipline="hvac", kind="supply"))
    result = engineering.insert(Equipment(system="P1", position=[0, 0], mark="F1"), "fan", "hvac")
    entity = cad.require("get_entity", handle=result.object_ids[0]).data["entity"]
    assert entity["name"] == "USER_FAN" and entity["layer"] == "OV_DEVICES"
    assert engineering.label(result.object_ids[0], [0, 500]).status == "ok"
    assert cad.entities(layer="OV_TEXT").data["total"] == 1


def test_invalid_profile():
    with pytest.raises(ValidationError):
        Profile(layers={"HVAC_DUCT": 999})
    with pytest.raises(ValidationError):
        Profile(layer_names={"TEXT": "../escape"})


def test_unit_conversion_budget():
    with pytest.raises(CadError):
        normalize(Line(start=[0, 0], end=[1e9, 0], units="m").model_dump(), 4)
