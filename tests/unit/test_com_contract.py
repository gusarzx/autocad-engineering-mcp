"""COM-boundary tests use fakes, never an installed AutoCAD."""

import threading
from types import SimpleNamespace

import pytest

from autocad_engineering_mcp.adapters import autocad_com
from autocad_engineering_mcp.adapters.com_geometry import ensure_2d
from autocad_engineering_mcp.core.exceptions import CadError


def test_sta_ownership_no_implicit_launch_and_release(monkeypatch):
    calls = []
    initialized = []
    fake_app = SimpleNamespace(Version="26.0 test")

    def record(name):
        calls.append((name, threading.get_ident()))

    def init(flags):
        initialized.append(threading.get_ident())

    def active(prog_id):
        record("get_active")
        return fake_app

    def forbidden_launch(prog_id):
        raise AssertionError("Unexpected AutoCAD launch")

    pythoncom = SimpleNamespace(
        COINIT_APARTMENTTHREADED=2,
        CoInitializeEx=init,
        CoUninitialize=lambda: record("uninitialize"),
        PumpWaitingMessages=lambda: None,
    )
    client = SimpleNamespace(GetActiveObject=active, DispatchEx=forbidden_launch)
    monkeypatch.setattr(autocad_com, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setitem(__import__("sys").modules, "pythoncom", pythoncom)
    monkeypatch.setitem(__import__("sys").modules, "win32com", SimpleNamespace(client=client))
    monkeypatch.setitem(__import__("sys").modules, "win32com.client", client)
    main_thread = threading.get_ident()
    adapter = autocad_com.ComAdapter("AutoCAD.Application.26", "26.0")
    try:
        result = adapter.execute("connect", {"allow_launch": False})
        assert result["data"]["version"] == "26.0 test"
        assert adapter.execute("status", {})["data"]["connected"]
        adapter.execute("disconnect", {})
    finally:
        adapter.close()
    assert initialized[0] != main_thread
    assert all(thread == initialized[0] for _, thread in calls)
    assert calls[-1][0] == "uninitialize"


@pytest.mark.parametrize(
    "entity",
    [
        SimpleNamespace(ObjectName="AcDb3dSolid"),
        SimpleNamespace(ObjectName="AcDbLine", StartPoint=(0, 0, 1)),
        SimpleNamespace(ObjectName="AcDbPolyline", Elevation=1),
        SimpleNamespace(ObjectName="AcDbCircle", Normal=(1, 0, 0)),
    ],
)
def test_existing_3d_rejected(entity):
    with pytest.raises(CadError):
        ensure_2d(entity)


def test_xy_geometry_allowed():
    ensure_2d(SimpleNamespace(ObjectName="AcDbLine", StartPoint=(0, 0, 0), EndPoint=(1, 0, 0)))
