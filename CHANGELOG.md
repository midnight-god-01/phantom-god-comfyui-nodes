# Changelog

## 1.5.2 — 2026-11-18

- Audited every pack feature: Auto Arrange Graph, Concatenate Text, Multi LoRA Loader, and Environment Manager.
- Made Concatenate Text OFF switches exclude values from the execution prompt, including values supplied through linked sockets.
- Corrected Concatenate Text DOM control sizing using rendered content measurements while preserving ComfyUI's native multiline widget sizing.
- Required an importable Triton version matching the active PyTorch compatibility line before enabling SageAttention installation.
- Added the verified PyTorch 2.15 → Triton 3.9 pairing for Linux.
- Made Environment Manager layout content-aware, aligned its install polling window with the backend timeout, and stopped client polling when its node is removed.
- Added regression tests for execution toggles, package prerequisites, live layout sizing, and node cleanup.
- Updated README feature inventory, supported LoRA row count, development file tree, and validation commands.


## 1.5.1 — 2026-11-18

- Fixed Concatenate Text collapsing native multiline text widgets by preserving ComfyUI's widget sizing.
- Explicitly hid the serialized Multi LoRA state widget in both Classic and Nodes 2.0, preventing raw JSON from appearing in the node body.
- Removed the 64-row restriction from the Python LoRA state parser as well as the frontend.
- Added regressions for text widget sizing, hidden state widget handling, and 70-row stacks.


## 1.5.0 — 2026-11-18

- Rebuilt Concatenate Text controls into responsive, non-scrolling rows with per-field enable/disable toggles and separate delete buttons.
- Added width-aware text widget sizing and resize callbacks for Classic and Nodes 2.0.
- Reworked Multi LoRA controls with fluid rows, improved narrow-width behavior, and live content-height sizing.
- Removed the fixed 64-row LoRA UI limit.
- Added frontend regression tests for field toggles, resizing and LoRA stacks beyond 64 rows.


## 1.4.0 — 2026-11-18

- Added Environment Manager node to inspect the active ComfyUI Python, PyTorch, CUDA, GPU, and driver environment.
- Added separate Triton and SageAttention compatibility checks, install/update controls, and job-status reporting.
- Added PyTorch-matched Triton version selection for Windows and Linux.
- Added exact Python/PyTorch/CUDA/platform wheel matching through the Comfy-Org SageAttention wheel index.
- Installer uses the active ComfyUI Python executable, binary packages only, and disables dependency upgrades so it does not replace PyTorch.
- Added backend compatibility tests and frontend validation coverage.


## 1.3.1 — 2026-11-18

- Reload cached LoRA weights when a model file changes at the same path.
- Reject absolute LoRA paths and path-traversal segments in workflow-supplied state.
- Added regression coverage for file replacement and unsafe LoRA paths.
- Rewrote the README with installation, feature, compatibility, development, and troubleshooting guidance.
- Clarified MIT licensing and retained the upstream Auto Arrange Graph copyright notice.
- Aligned package and frontend extension version metadata at 1.3.1.

## 1.3.0 — 2026-11-18

- Added Multi LoRA Loader (Model Only): up to 64 individually selectable LoRAs, each with its own strength, enable toggle, and remove control.
- Added model-only LoRA application through ComfyUI's official model patching API, without CLIP inputs or outputs.
- Added workflow-persisted LoRA row state, live LoRA file listing, list refresh, and file-change cache invalidation.
- Reworked Concatenate Text controls with a rounded Add Text button and per-field remove controls.
- Made every Concatenate Text field optional so any individual field, including the first two, can be removed safely.
- Standardized dynamically added text placeholders and labels to "Text N".
- Added Python and frontend regression tests for LoRA stacking, independent toggles, workflow prompt injection, and row removal.

## 1.2.1 — 2026-11-18

- Fixed dynamic backend input schema lookup for ComfyUI's membership-plus-index access pattern.
- Restored dynamic widget values by name on recent frontends, with positional fallback for older workflow files.
- Kept the Add Text control label stable after workflow restoration.
- Added regression tests for dynamic input lookup and both workflow restoration formats.
- Audited extension hooks and widget constructors against ComfyUI v0.45.0 with bundled frontend 1.58.5 and standalone frontend 1.61.2.

## 1.2.0 — 2026-11-17

- Added the draggable Concatenate Text (Phantom God) backend node.
- Added an Add Text control with multiline text widgets and matching STRING sockets.
- Added workflow restoration for dynamically created text fields.
- Added automatic Python feature discovery through the features package.
- Updated package documentation and CI to cover backend nodes and frontend features.
- Preserved the existing Auto Arrange Graph feature and its tests.

## 1.1.0 — 2026-11-17

- Audited the extension against ComfyUI v0.45.0 and frontend package 1.59.2.
- Exported the empty NODE_CLASS_MAPPINGS required for a successful frontend-only V1 custom-node load.
- Kept the official canvas context-menu extension hook.
- Restored the original float-right earliest-downstream-use placement behavior using the current graph links Map API.
- Removed the legacy indexed-link access and canvas prototype patching approach.
- Updated GitHub Actions to current v7 action releases and Node.js 26 LTS.
- Added a regression test for branching graph placement.

## 1.0.0 — 2026-11-17

- Initial Phantom God ComfyUI Nodes release.
- Includes the Auto Arrange Graph canvas-menu feature.
