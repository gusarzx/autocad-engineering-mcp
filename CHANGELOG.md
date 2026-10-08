# Changelog

## 0.2.0 — unreleased

- Added 14 pipeline tools to the existing MCP server; all 85 previous schemas remain unchanged.
- Exact ACI/TrueColor/ByLayer red and blue candidates, model/preselection queries and bounded pages.
- Standard 2D polylines, same-Handle route/move/extend operations, guarded deletion and colour edits.
- Endpoint/crossing/gap/turn/self-intersection analysis, explicit bridge creation, possible diameter
  label associations and actual nearby blocks; all new parameters use drawing units.
- Locked layer, XREF, metadata and stale-document/state guards; grouped Undo and captured-state
  COM compensation with explicit rollback failures and deletion limitations.
- No new dependencies. Mock and Python ActiveX-contract tests only; AutoCAD remains unverified.

## 0.1.0 — unreleased

- Local stdio MCP server on the official MCP Python SDK v2.
- 85 typed tools for editable 2D CAD, layers, blocks, annotation, HVAC and plumbing.
- STA-thread Windows COM adapter and platform-independent mock.
- Validated creation-only batch, read-only dry-run, best-effort COM compensation.
- File restrictions, explicit confirmations, overwrite backups and bounded drawing queries.
- Drawing-backed engineering metadata, topology and schematic specifications.
- Windows installer/uninstaller, bilingual docs, examples and opt-in integration tests.

Windows scripts and real AutoCAD 2027 integration have not been run. The project is a
development preview, not a verified production release. No GitHub upload was performed.
