# Changelog

## 1.1.0 — 2026-11-17

- Audited the extension against ComfyUI v0.45.0 and frontend package 1.59.2.
- Exported the empty `NODE_CLASS_MAPPINGS` required for a successful frontend-only V1 custom-node load.
- Kept the official canvas context-menu extension hook.
- Restored the original float-right earliest-downstream-use placement behavior using the current graph links Map API.
- Removed the legacy indexed-link access and canvas prototype patching approach.
- Updated GitHub Actions to current v7 action releases and Node.js 26 LTS.
- Added a regression test for branching graph placement.

## 1.0.0 — 2026-11-17

- Initial Phantom God ComfyUI Nodes release.
- Includes only the Auto Arrange Graph canvas-menu feature.
