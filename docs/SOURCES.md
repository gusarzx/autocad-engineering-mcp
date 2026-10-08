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
