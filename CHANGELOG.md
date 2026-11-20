# Changelog

## 1.6.3 — 2026-11-21

- Standardize settings controls with the dark/orange UI theme: dark styled memory-mode selector, consistent field sizing, matching checkbox accent, refined colour-picker frame, and unified footer button states.
- Align the package and Auto Arrange extension version metadata at 1.6.3.


## 1.6.2 — 2026-11-20

- Correct LoRA state transport: use a normal STRING widget hidden by the frontend and included in ComfyUI's standard prompt serialization. Remove the unsupported custom hidden STRING declaration and graph-to-prompt monkey patch.
- Sync hidden widget state whenever workflow properties are restored or edited, so stacked LoRA selections and strengths reach backend execution.
- Guard initial node sizing during ComfyUI graph configuration and align the Auto Arrange extension version log with the package.
- Match the native MODEL LoRA strength range, normalize Windows/POSIX relative paths for metadata lookup, and retry cache checks after temporary LoRA-library errors.

## 1.6.1 — 2026-11-20

- Remove trigger-word state, selection UI, and STRING socket; the LoRA stack now has exactly one MODEL input and one MODEL output.
- Keep embedded LoRA information limited to model metadata; remove trigger separator and trigger-specific settings.
- Skip disabled and zero-strength LoRAs because they do not modify the MODEL output.
- Add regression tests confirming no trigger or CLIP sockets and only the modified MODEL is returned.
- This intermediate candidate used an unsupported custom hidden STRING input; it was superseded before commit by the standard-widget state transport in 1.6.2.

## 1.6.0 — 2026-11-20

- Add a Pixaroma-inspired multi-LoRA node with one MODEL input, a MODEL output, and a trigger-word STRING output; no CLIP sockets or CLIP processing.
- Add a dark, orange-accented frontend with searchable LoRA selection, independent strength controls, row enable switches, all-on/off, info panel, row context actions, and settings.
- Add an offline safetensors metadata route, selected trigger-word handling, custom trigger words, and workflow-state injection for nested subgraphs.
- Apply stacked LoRAs through ComfyUI's native model-only patching API, with safe state normalization, file-change cache invalidation, memory modes, and missing/failed-file handling.
- Re-check ComfyUI 0.46.0's native model-only loader and frontend 1.59.6 prompt-building API; add backend and frontend regression tests and update CI.
- Size newly added nodes to fit their live DOM widget without rewriting saved dimensions during graph restoration.
- Invalidate the output cache when a zero-strength LoRA file appears or disappears, because file presence controls whether its selected trigger words are emitted.

## 1.5.9 — 2026-11-20

- Re-check current ComfyUI core and frontend sources and correct the compatibility notes: ComfyUI v0.46.0 released with frontend package 1.59.6, while current ComfyUI master pins 1.59.10.
- Confirm the active canvas graph, canvas-menu extension hook, execution-order calculation, graph link Map, node positioning, and canvas invalidation APIs remain available.
- Align package and extension version metadata at 1.5.9.

## 1.5.8 — 2026-11-20

- Audit Auto Arrange Graph against ComfyUI 0.46.0, bundled frontend 1.59.6, and standalone frontend 1.61.4.
- Remove the deprecated ComfyApp.graph fallback and use the active graph supplied by the canvas-menu hook.
- Require ComfyUI 0.46.0 and Python 3.10 or newer; add regression coverage for active-canvas graph selection.
- Align package and extension version metadata at 1.5.8.

## 1.5.7 — 2026-11-20

- Remove Concatenate Text, Environment Manager, and Multi LoRA Loader, including their Python modules, frontend extensions, and feature-specific tests.
- Retain Auto Arrange Graph as the only shipped feature and update documentation, package metadata, and CI validation accordingly.
