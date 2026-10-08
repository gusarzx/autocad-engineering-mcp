# Implementation sources

Documentation reviewed on 2026-10-08. Documentation support is separate from runtime verification.

- [MCP Python SDK v2](https://py.sdk.modelcontextprotocol.io/): current stable SDK, typed tools,
  structured output, lifespan and stdio. Implementation tested with `mcp==2.3.0`.
- [SDK v2 migration](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md):
  `MCPServer` replaces v1 `FastMCP`; no private compatibility shim is used.
- [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli): CLI registration,
  `config.toml`, environment variables, timeouts and tool approval hints.
- [AutoCAD 2027 ActiveX compatibility](https://help.autodesk.com/cloudhelp/2027/DEU/AutoCAD-Customization/files/GUID-927E71C2-E515-438E-9D7A-246D97BEF93F.htm):
  documents version 26.0 and the acax26 type library. Target ProgID is configurable
  `AutoCAD.Application.26`; verify its registration locally with the environment script.
- [AutoCAD 2027 Developer index](https://help.autodesk.com/view/OARX/2027/DEU/):
  official entry point for ActiveX and .NET guides.
- [ModelSpace ActiveX methods](https://help.autodesk.com/cloudhelp/2025/DEU/AutoCAD-LT-ActiveX-Reference/files/GUID-C541B6F2-1279-4D1C-8DC0-788F27F644EF.htm):
  documented AddLine/AddLightWeightPolyline/AddCircle/AddArc/AddSpline/AddHatch/
  AddDimAligned/InsertBlock API family. Method reference is from an earlier release;
  exact Python marshaling and behavior in 2027 are still pending workstation tests.
- [Microsoft COM initialization](https://learn.microsoft.com/en-us/windows/win32/learnwin32/initializing-the-com-library):
  initialize COM on the owning thread, pump messages, avoid sharing interface pointers,
  and balance initialization with uninitialization.

The adapter implements only a fixed allowlist of ActiveX methods. It does not use
`SendCommand`, arbitrary AutoLISP, remote hosting or user projects as research material.

## Pipeline extension

- [Coordinates](https://help.autodesk.com/cloudhelp/2018/DEU/AutoCAD-ActiveX-Reference/files/GUID-11CAC0D6-DFCF-4653-8403-CF5AFD689773.htm):
  writable coordinates can change vertex count. LWPolyline uses OCS XY, legacy Polyline
  uses OCS XY plus ignored Z; this adapter requires standard normal and zero elevation.
- [ColorMethod](https://help.autodesk.com/cloudhelp/2024/DEU/AutoCAD-LT-ActiveX-Reference/files/GUID-C555F5A1-A3AE-42F6-B45D-930B42AD5F9A.htm)
  and [enum values](https://help.autodesk.com/cloudhelp/2015/JPN/AutoCAD-ActiveX/files/GUID-82A124B3-1F6D-44EF-A3AE-CA269A5BC5CB.htm):
  192 ByLayer, 193 ByBlock, 194 ByRGB, 195 ByACI. TrueColor is read before classifying.
- [GetBulge](https://help.autodesk.com/cloudhelp/2018/ENU/AutoCAD-ActiveX-Reference/files/GUID-6AC9CF99-7230-4333-859A-1CBACB57B5BA.htm):
  signed tan(sweep/4), simple polyline restrictions; curved lengths, distances and bounds
  are retained rather than interpreting arc chords as straight pipes.
- [IntersectWith](https://help.autodesk.com/cloudhelp/2024/FRA/AutoCAD-ActiveX-Reference/files/GUID-1243A593-5DAE-4DC3-B539-59FDA990E687.htm):
  intersection coordinates, acExtendNone=0. Actual COM calls await Windows verification.
- [Layer Lock](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-LT-ActiveX-Reference/files/GUID-49CA344E-0F8C-4AB2-8336-9E696F8BD5D7.htm):
  locked layers protect editing; pipeline tools additionally reject creation on them.

Earlier-release API references support implementation choices, not a claim that
AutoCAD 2027 marshaling or transaction behaviour has been tested.
