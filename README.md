# Phantom God ComfyUI Nodes

A ComfyUI frontend extension repository. The first release contains exactly one feature: **Auto Arrange Graph**.

## Auto Arrange Graph

Right-click an **empty area of the graph canvas** to access two commands:

- **Arrange (float left)** — delegates to ComfyUI's native `graph.arrange()` layout.
- **Arrange (float right)** — arranges nodes by execution order, moves upstream nodes toward their earliest downstream use, and right-aligns nodes inside each column. `SaveImage` and `PreviewImage` nodes are prioritized at the top of their column.

These are canvas context-menu commands, not draggable workflow nodes. The extension does not add backend nodes, alter workflow connections, or install third-party runtime dependencies.

## Install

Run this from your ComfyUI `custom_nodes` directory:

```bash
git clone https://github.com/midnight-god-01/phantom-god-comfyui-nodes.git
```

Restart ComfyUI and hard-refresh the browser (`Ctrl+Shift+R`).

## Update

```bash
cd phantom-god-comfyui-nodes
git pull
```

Restart ComfyUI and hard-refresh the browser after updating.

## Troubleshooting

1. Confirm that `ComfyUI/custom_nodes/phantom-god-comfyui-nodes/__init__.py` exists. It must be directly inside the repository folder.
2. Remove earlier standalone folders named `ComfyUI-Auto-Arrange-Graph*` from `custom_nodes` to prevent duplicate or broken copies.
3. Right-click a blank canvas area, not a node, link, or group. These commands are added to the canvas menu.
4. Open the browser developer console and confirm that it reports:

   ```text
   [Phantom God] Auto Arrange Graph extension loaded (v1.1.0).
   ```

5. If the message is missing, check the ComfyUI startup log for custom-node import errors and confirm that the repository's `WEB_DIRECTORY` resolves to `web/js`.

## Compatibility and implementation

This is a frontend-only ComfyUI custom-node extension. Its root `__init__.py` exports the documented `WEB_DIRECTORY = "./web/js"` entry point and an intentionally empty `NODE_CLASS_MAPPINGS = {}`. The empty mapping is required by ComfyUI v0.45.0’s V1 custom-node loader for a frontend-only pack; it prevents the package being marked as an import failure while adding no draggable or executable backend nodes. The frontend imports `app` from ComfyUI's `scripts/app.js`, registers through `app.registerExtension()`, and adds the two commands through the official `getCanvasMenuItems()` hook. It does not patch `LGraphCanvas` prototypes or import deprecated `/scripts/ui.js` APIs.

The layout actions use ComfyUI's graph APIs: `graph.arrange()`, `graph.computeExecutionOrder(false, true)`, the current `graph.links` Map, `node.setPos()`, and `graph.setDirtyCanvas()`. The float-right action retains the original upstream "earliest downstream use" placement behavior while avoiding the old indexed `graph.links[id]` access.

### Version check

Checked on **17 November 2026**:

- Latest stable ComfyUI core release: **v0.45.0**.
- The ComfyUI v0.45.0 release notes specify bundled frontend package **1.58.5**.
- Latest stable `comfyui-frontend-package` on PyPI: **1.59.2** (released 16 November 2026).
- The ComfyUI log you provided reported frontend package **1.59.1**, one patch behind 1.59.2.

The implementation is based on the current frontend extension types and graph methods, not legacy canvas prototype overrides. The extension itself has no frontend-version pin and uses only the supported APIs described above.

## Development checks

No JavaScript package installation is required. With Python 3.13 and Node.js 26 installed, run:

```bash
python -m py_compile __init__.py
node --check web/js/graphArrange.js
node --test
```

GitHub Actions runs these checks on pushes and pull requests. Dependabot checks the workflow actions weekly for updates.

## Source and attribution

The arrangement behavior is adapted from the Auto Arrange Graph script in [pythongosssss/ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts). The upstream MIT copyright notice is retained in [LICENSE](LICENSE).
