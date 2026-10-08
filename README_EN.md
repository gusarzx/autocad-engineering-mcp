# AutoCAD Engineering MCP

Local stdio MCP server `autocad-engineering` for **editable 2D AutoCAD drawings**,
HVAC and plumbing schematics controlled from Codex.

[Русский](README.md) · [99-tool catalog](docs/TOOLS.md) ·
[Prompt examples](examples/codex_prompts.md) · [Windows checklist](docs/WINDOWS_VERIFICATION.md)

**0.2.0 development preview.** Real Windows/AutoCAD 2027 integration and PowerShell
scripts have not been run. Mock tests do not verify AutoCAD. This is not an official
Autodesk or OpenAI product. The package is not yet published to GitHub or PyPI.

## Features and versions

- Editable 2D line, polyline, circle, arc, rectangle, polygon, text, MText, spline,
  hatch and aligned dimension tools.
- Move, copy, rotate, scale, mirror, offset and confirmed deletion.
- Layers, generic original schematic blocks, attributes and local user DWG libraries.
- Paginated model-space reading, type/layer/MARK filters, current preselection and bounds.
- Creation-only batches, read-only preflight, dry-run and best-effort COM cleanup.
- HVAC/plumbing schematics, flat isometric projection, persisted network metadata and schedules.
- Restricted file access, explicit overwrite permission and separate backups.
- Colour-based pipeline candidates in existing DWGs, route editing, selection operations,
  connection analysis, possible diameter-label associations and nearby block lookup.

## Working with pipelines

The 14 additional tools share the existing connection, STA and structured responses.
`get_pipelines` / `get_selected_pipelines` recognise LINE, LWPOLYLINE and simple 2D
POLYLINE with exact ACI 1/5 or RGB red/blue, directly assigned or inherited ByLayer.
Matches are **candidates**, classified RED_PIPE/BLUE_PIPE, never identified as a heating
or water system. ByBlock and approximate colours are excluded.

**All new pipeline coordinates, distances, displacements and tolerances use drawing
units directly.** Inspect INSUNITS before translating a request in millimetres.
Use colour/layer/selection and `[xmin,ymin,xmax,ymax]` region filters, `limit` and
`next_offset`. Query/block/label cursors refer to raw ModelSpace positions; analysis
cursors refer to findings. Keep the drawing unchanged while paging.

- `create_pipeline`: one explicit ACI-coloured LWPOLYLINE. Missing default
  MCP_PIPE_RED/BLUE layers are created; a missing named layer needs `allow_create_layer=true`.
- `modify_pipeline`, `extend_pipeline`, `move_pipeline`: preserve the Handle.
  Extension points are ordered outward from the chosen end; start points are reversed
  and prepended. A LINE retains two endpoints and can extend only straight outward.
- `delete_pipeline`: one Handle, requires `confirm=true`; dry-run previews deletion.
- `set_pipeline_color`, `move_selected_pipelines`, `set_selected_pipelines_color`:
  preflight all candidates, no interactive selection. Bulk edits above max_change
  need `confirm=true`; every mutation supports `dry_run`.
- `analyze_pipeline_connections`: exact coincident endpoints are CONNECTED, crossings
  are INTERSECTION, unmatched ends OPEN_END, nearby distinct ends NEAR_CONNECTION;
  also returns TURN, CURVED_SEGMENT and self intersections. Never joins automatically.
- `connect_pipelines`: creates a bridge via connection_point between nearest or explicit
  endpoints, preserving both inputs. Mixed colours need `allow_mixed_colors=true`.
- `find_pipe_diameter_labels`: TEXT/MTEXT Ø, ⌀, DN, Ду, D labels; nearest-pipe links
  remain `confirmed=false`, ties return possible Handles. No sizing calculations.
- `get_nearby_blocks`: actual names, insertion points, layers and XY distances.

Locked layers, XREF and non-ModelSpace edits are rejected. Only WCS XY, standard normal
and zero elevation are supported; fitted legacy polylines are rejected. Arcs can be
read, moved and analysed; route editing rejects arc flattening and unsafe varying widths.
Existing linked engineering geometry is protected from geometry edits and deletion.
Analysis is bounded to 500 candidates by default (1000 maximum), 20000 vertices and
a comparison budget; exceeding these is an explicit error asking for narrower filters.

ActiveX uses grouped Undo marks and captured-state compensation, **not a full DWG
database transaction**. Error responses report `rollback=restored/failed/unavailable_for_delete`.
A deleted object cannot be restored with its original Handle by this adapter; inspect
the drawing and use AutoCAD Undo. Cross-object COM intersections use IntersectWith;
self intersections use planar line/bulge math. No drawing is auto-saved. Native API
calls and coincident-geometry behaviour remain unverified on AutoCAD 2027.

Try: “Show red pipeline candidates on layer Pipes”; “Preview a red route through
[0,0], [1000,0], [1000,500]”; “Move selected pipes down 300 mm after checking units”;
“Find nearby gaps, without treating crossings as connections”.
See the [Russian walkthrough](README.md#работа-с-трубопроводами) and
[implementation report](docs/PIPELINES_REPORT.md).

Target: full AutoCAD 2027 on Windows. Autodesk documents version 26.0 and ActiveX;
this establishes API availability, not successful execution of this adapter.
[Autodesk compatibility documentation](https://help.autodesk.com/cloudhelp/2027/DEU/AutoCAD-Customization/files/GUID-927E71C2-E515-438E-9D7A-246D97BEF93F.htm).
Other versions require explicit connection override and are not claimed compatible.
LT, Mac, Web and noninteractive Windows services are not verified targets.

## Requirements

Windows 10/11, running AutoCAD 2027, Python 3.11+ (64-bit recommended), and Codex CLI
or a Desktop/IDE Extension version supporting local MCP. Use the same user session
and privilege level for AutoCAD and MCP. Dependencies install from PyPI, including
MCP Python SDK v2, Pydantic 2 and pywin32 on Windows.

MCP lets Codex call tools exposed by a local program. This server does not replace
AutoCAD or run an AI model. It requires no OpenAI API key; Codex authentication is
separate. Run it on the Windows machine running AutoCAD. Remote Mac-to-Windows
control is not implemented. The server contains no project/DWG upload function;
AI service data handling depends on the Codex client configuration.

## Install AutoCAD Engineering MCP in Codex in 5 steps

1. Transfer the project locally, e.g. to `C:\CAD\autocad-engineering-mcp`. Install
   Python 3.11+ with the Python launcher and install Codex. Open PowerShell.
2. Install the local package without registration:

   ```powershell
   Set-Location 'C:\CAD\autocad-engineering-mcp'
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -SkipCodexRegistration
   ```

   Execution policy changes apply to this process only. The script creates `.venv`,
   installs dependencies and reports registry/component availability. It does not
   launch AutoCAD, run integration tests or change system PATH.
3. Register the absolute interpreter path:

   ```powershell
   $McpPython = (Resolve-Path '.\.venv\Scripts\python.exe').Path
   $DwgRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'AutoCAD Engineering MCP'
   codex mcp add autocad-engineering --env 'ACAD_MCP_BACKEND=com' --env "ACAD_MCP_SAVE_ROOT=$DwgRoot" -- $McpPython -m autocad_engineering_mcp
   ```

4. Run `codex mcp list`, then `.\.venv\Scripts\python.exe scripts\check_environment.py`.
   Open AutoCAD manually and wait until it is idle.
5. Start a new Codex session. Ask: “Use autocad-engineering to attach to the running
   AutoCAD without launching it. Show the version and active drawing; do not modify it.”
   Create a new test drawing before testing modifications.

Registration/configuration follows [official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
`codex mcp list` only establishes configuration; verify actual tool discovery/calls
in a new Codex session. User Codex registration has not been changed during development.

## PowerShell installation

```powershell
.\scripts\install.ps1                         # Offers registration when codex is found
.\scripts\install.ps1 -RegisterCodex          # Explicitly authorized registration
.\scripts\install.ps1 -SkipCodexRegistration -SaveRoot 'C:\CAD\Drawings'
.\scripts\install.ps1 -SkipCodexRegistration -PythonCommand 'python' -PythonArguments @()
```

An existing environment must have the installer ownership marker. A manual `.venv`
is not adopted; update it manually or use a fresh folder. Missing AutoCAD registration
is a warning, allowing package installation before AutoCAD installation.

## Manual Windows installation

```powershell
py -3 -c "import sys; assert sys.version_info >= (3,11); print(sys.version)"
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe .\scripts\check_environment.py
```

Install from the local directory, not an assumed published package. Reinstall after
source changes or use editable development installation.

## Codex config.toml and connection verification

As an alternative to CLI registration, edit `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.autocad-engineering]
command = 'C:\CAD\autocad-engineering-mcp\.venv\Scripts\python.exe'
args = ["-m", "autocad_engineering_mcp"]
startup_timeout_sec = 20
tool_timeout_sec = 120

[mcp_servers.autocad-engineering.env]
ACAD_MCP_BACKEND = "com"
ACAD_MCP_SAVE_ROOT = 'C:\CAD\Drawings'
```

Adjust paths to your installation and use either registration method. CLI and IDE
Extension support MCP configuration. In Desktop check your installed version's MCP
settings, enable the local server and restart the session if needed. Only stdio is
implemented; do not configure a cloud HTTP connector for this program.

For a manual diagnostic launch:

```powershell
$env:ACAD_MCP_BACKEND = 'com'
.\.venv\Scripts\python.exe -m autocad_engineering_mcp
# Equivalent console entry point:
.\.venv\Scripts\autocad-engineering-mcp.exe
```

The process waits for MCP stdin messages; it is not an interactive command prompt.
Ctrl+C stops it. Logging goes to stderr, preserving protocol stdout.

## Using MCP after installation

State the system, units, sizes, positions and save destination. Connect and inspect
the active drawing, then create an isolated document for initial tests. New documents
default to INSUNITS=4 (mm). Geometry accepts mm/cm/m/in/ft; angles use radians.
CAD points must be `[x,y]` or `[x,y,0]`; nonzero Z is rejected.

Batch dry-run returns a checked plan using read-only queries. It cannot predict all
COM failures. Execute with `dry_run=false`; direct creation tools default to execution,
while batch and save default to dry-run. Save a new filename under SAVE_ROOT.
Overwriting requires `overwrite=true` and makes a separate `.bak`. Deletion always
requires `confirm=true`; modifications above the configured threshold (default 20)
also need confirmation. Pass these flags only after explicit human authorization.

All responses use `status`, `object_ids`, `count`, `data`, `error`, `warnings`.
Handles are scoped to their DWG. Layer/block definitions do not count as model-space
geometry. Schema failures can also appear as standard MCP errors.

## Available tools

The complete generated [tool catalog](docs/TOOLS.md) lists 99 tools. `autocad_*`
handles connection/documents, `cad_draw_*` handles 2D geometry, `cad_*` provides
reading/layers/blocks/transforms/batches, `hvac_*` and `plumbing_*` build schematics.
`cad_generate_specification` aggregates supported drawing entities;
`cad_get_engineering_network` reads logical nodes and edges.

## HVAC

Declare a system with `discipline=hvac`, kind supply/exhaust/heating. Rectangular
ducts require width/height; round ducts require diameter. Engineering dimensions
and elevation are mm; airflow is m³/h. Routes are centreline schematics, without
automatic double-line outlines or fittings. Branch connection points must be explicit
trunk vertices. Equipment uses editable MARK/NAME/TYPE/SIZE/SYSTEM/DESCRIPTION attributes.
Built-in symbols are original generic rectangles/crosses, not a certified symbol library.

```powershell
.\.venv\Scripts\python.exe .\examples\hvac_example.py --backend mock
# Later, on Windows with AutoCAD running, creates a NEW drawing:
.\.venv\Scripts\python.exe .\examples\hvac_example.py --backend com --save hvac-test.dwg
```

Creates an AHU, 500×300 trunk, four 250×150 branches/grilles and editable text schedule.

## Plumbing

System kinds: cold_water, hot_water, hot_water_return, sanitary_sewer, rainwater.
Projection is plan or axonometric. Pipes store diameter, material, elevation, slope
(dimensionless fraction 0..1), direction, mark and length. Slope is metadata and does
not automatically reshape the route.

Axonometric mode projects logical XYZ mm using `X=(x-y)*sqrt(3)/2`, `Y=(x+y)/2+z`,
`Z=0`. Output remains a 2D drawing; specification lengths use the logical route.

```powershell
.\.venv\Scripts\python.exe .\examples\plumbing_example.py --backend mock
.\.venv\Scripts\python.exe .\examples\plumbing_example.py --backend com --save plumbing-test.dwg
```

## Prompt examples

At least twelve detailed Russian prompts with tools, expected results and limitations
are provided in [examples/codex_prompts.md](examples/codex_prompts.md): inspect a drawing,
create HVAC layers, draw a duct, supply/exhaust schematics, label elements, cold-water
isometric schematic, sewer riser, AHU search, specification, missing marks and DWG copy.

## User libraries and engineering standards

Keep permitted **2D** DWG libraries inside SAVE_ROOT, e.g. `blocks\fan.dwg`.
`cad_insert_block` accepts a definition name or a local DWG path. Validate imported
units, attributes, XY planarity and scaling on Windows. Only distribute licensed assets.

Set `ACAD_MCP_PROFILE` to an explicit JSON file. The bundled example is in
`src/autocad_engineering_mcp/resources/profile.example.json`. `layers` maps semantic
roles to colours, `layer_names` maps roles to actual project layer names, and `symbols`
maps keys such as `hvac.fan` to an existing definition or user DWG. `linetype` must be
already loaded. `text_height` is mm and `symbol_scale` controls schematic block size.
`cad_create_block` dimensions use drawing units. Supply equipment marks explicitly.
Profile extensions belong in `config.py`. Engineer review is required for SPDS/GOST;
automatic compliance with any particular standard is not claimed.

## Limitations

- 2D XY only, no solids/BIM/automatic routing/hydraulic or airflow design calculations.
- ModelSpace only; no PaperSpace/plotting workflow.
- Specifications use our XData and attributed blocks; arbitrary third-party linework
  is not recognized as a network. Discipline-specific schedules use XData records.
- Matching vertices rounded to 0.001 mm form nodes. Mid-segment equipment/intersections
  need explicit vertices; no proximity-based network inference.
- Empty system declarations remain session-local until an element is persisted.
  XData survives DWG saving, but manual editing outside MCP can stale network metadata.
- Creation-only batches default to 100 operations. COM compensation and Undo Mark
  are not transactions. Failed operations may leave partial changes.
- Default page size 100 and engineering scan budget 10,000. Always follow next_offset.
  Exceeding scan budget yields an error rather than a misleading partial specification.
- Batch plans are limited to 128 KB. Oversized response details are explicitly omitted
  with response_truncated, preserving status/handles. Reduce page size or request scope.
- Direct attribute updates of linked engineering elements are blocked to prevent stale
  XData; recreate them using the engineering tools.
- Mock is in memory, cannot read/write DWG and does not simulate offset.
- No arbitrary AutoCAD/AutoLISP/shell execution or document closing tools.
- Save/open/library paths stay inside SAVE_ROOT; symlink escapes are rejected.
  Concurrent external file/drawing switching during operations is unsupported.

Environment variables use the prefix `ACAD_MCP_`: BACKEND, SAVE_ROOT, PROG_ID,
EXPECTED_VERSION, MAX_BATCH, MAX_CHANGE, PAGE_SIZE, SCAN_LIMIT, PROFILE.
`.env.example` is a reference, not auto-loaded. No credentials are included or required.

## Troubleshooting

| Problem | Action |
| --- | --- |
| Unsupported Python | Inspect `py -0p`, select Python >=3.11 |
| Requires Windows | Use mock on Mac/Linux; run COM on the AutoCAD machine |
| AutoCAD not in ROT | Start AutoCAD manually; match privilege level and user session |
| COM busy/HRESULT | Close dialogs; inspect partial changes before retrying |
| Wrong version | Check Version, registry report and configurable ProgID |
| Unitless drawing | Create units=4 or set INSUNITS manually in AutoCAD |
| Missing block/layer | Create definitions first, respecting batch order |
| Missing tags | Add standard attribute tags to your library block |
| Rejected path | Use a .dwg filename inside SAVE_ROOT |
| Existing destination | Use a new name or explicitly authorize overwrite |
| Invisible tools | Check absolute interpreter, package installation, list and new session |
| Scan budget exceeded | Raise SCAN_LIMIT deliberately or split the project |

## FAQ and uninstall

Develop without AutoCAD? Yes, use mock/unit tests on Mac/Linux. Real DWG output? The
COM implementation calls SaveAs but requires Windows verification; mock does not.
Automatic AutoCAD launch? Only with explicit allow_launch=true. Certified GOST assets?
None bundled; use your own permitted library. OpenAI API key? Not needed by this server.

For an installer-owned venv, preview `.\scripts\uninstall.ps1 -WhatIf`, then run it
normally. Optional `-RemoveCodexRegistration` also removes the Codex entry. Manual
installations can use `.\.venv\Scripts\python.exe -m pip uninstall autocad-engineering-mcp`.
AutoCAD, source files and user drawings are retained.

## Architecture

`server.py`/`config.py` configure MCP and settings; `core/` owns typed operations,
units, safety and service; `adapters/` contains the protocol, mock, COM STA worker
and ActiveX geometry; `tools/` registers schemas; `engineering/` builds 2D schematics,
topology and schedules; `resources/` provides profile examples. Tests, scripts,
examples and documentation remain separate.

One STA worker owns all COM interfaces and pumps messages. Only plain data crosses
the thread boundary. A service lock preserves workflow ordering; do not switch active
drawings manually during an operation. The adapter protocol allows a future .NET backend.

## Development and testing

```console
python3.11 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/python -m pytest -m "not autocad"
.venv/bin/python -m build
ACAD_MCP_BACKEND=mock .venv/bin/python -m autocad_engineering_mcp
```

On Windows use `.venv\Scripts\` executables. Unit tests cover validation, units,
mock geometry, engineering scenarios, metadata reload, batch failures, path safety,
schemas and real stdio protocol exchange. Integration tests are opt-in and create
a fresh test document. See the [Windows checklist](docs/WINDOWS_VERIFICATION.md).
Prepared GitHub Actions checks formatting/lint/unit/build across three OSes; no
GitHub CI run or publication has occurred during development.

## Contributing and license

[CONTRIBUTING](CONTRIBUTING.md), [CHANGELOG](CHANGELOG.md), [MIT](LICENSE).
No proprietary AutoCAD files or third-party DWG libraries are included.
[Documentation sources and evidence boundaries](docs/SOURCES.md).
