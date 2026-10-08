# Contributing

Use Python 3.11+ and an isolated environment:

```console
python -m venv .venv
python -m pip install -e ".[dev]"
ruff format .
ruff check .
pytest -m "not autocad"
python -m build
```

Activate that virtual environment first, or invoke its Python and tool executables
with absolute paths. Set `ACAD_MCP_BACKEND=mock` when running the server on macOS/Linux.
Never commit credentials, personal DWGs, proprietary Autodesk libraries or unlicensed symbols.
Do not upload a user's project without their explicit permission.

Keep operation schemas in `core/models.py`, engineering schemas in `engineering/models.py`
and all COM interfaces inside the adapter's STA thread. Return plain JSON-compatible data.
New adapter implementations must respect the same safety policies and exception contract.
Do not add arbitrary command, AutoLISP, process execution, HTTP transport or public endpoints.
Add meaningful regression tests for safety policies, parameter conversion and state changes.

See [Windows verification](docs/WINDOWS_VERIFICATION.md) for the opt-in integration
procedure. Changes must not silently edit existing drawings, overwrite files, or start
AutoCAD. Document partial failure and unsupported behavior. Mock results must always
remain distinguishable from actual COM evidence.
