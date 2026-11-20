# Phantom God ComfyUI Nodes

A lightweight ComfyUI custom-node package containing a graph-canvas arrangement extension.

**Current version:** 1.5.7  
**Minimum requirements:** ComfyUI 0.45.0 or newer; Python 3.9 or newer

## Features

### Auto Arrange Graph

Adds two commands to the graph canvas context menu:

- **Arrange (float left)** uses ComfyUI's native graph arrangement.
- **Arrange (float right)** arranges nodes by execution order, right-aligns nodes within columns, and moves upstream nodes toward their earliest downstream use. Save Image and Preview Image nodes are prioritized within each column.

To access the commands, right-click an empty area of the graph canvas. These are canvas actions, not workflow nodes.

This package currently provides no custom workflow nodes. Auto Arrange Graph is its only shipped feature.

## Installation

1. Close ComfyUI.
2. Open a terminal in the ComfyUI \`custom_nodes\` directory.
3. Clone this repository:

~~~~bash
git clone https://github.com/midnight-god-01/phantom-god-comfyui-nodes.git
~~~~

4. Start ComfyUI again and refresh the browser interface.

The repository does not require a separate pip or npm installation step. It uses the Python and frontend APIs provided by ComfyUI.

## Updating

From the custom node directory, run:

~~~~bash
cd phantom-god-comfyui-nodes
git pull
~~~~

Restart the ComfyUI server after updating. Then refresh the browser interface so ComfyUI reloads the JavaScript extension.

## Compatibility

The package declares ComfyUI 0.45.0 or newer and Python 3.9 or newer. Auto Arrange Graph uses ComfyUI's extension registration and canvas-menu APIs. It reads graph links through the current Map-based link collection rather than patching legacy canvas prototypes.

## Troubleshooting

- **The arrange commands are not visible:** Right-click an empty area of the graph canvas rather than a node.
- **The browser extension does not load:** Confirm the repository is located at \`ComfyUI/custom_nodes/phantom-god-comfyui-nodes\`, restart the ComfyUI server, and hard-refresh the browser.
- **The package fails during startup:** Check the ComfyUI terminal for Python import errors and confirm the installed ComfyUI version meets the minimum requirement.

## Development

The repository keeps the frontend extension and tests separate:

~~~~text
.
├── __init__.py
├── features/
│   └── __init__.py
├── web/
│   └── js/
│       └── graphArrange.js
├── tests/
│   ├── graphArrange.test.mjs
│   └── test_feature_registry.py
├── CHANGELOG.md
├── LICENSE
├── package.json
└── pyproject.toml
~~~~

The \`features\` package retains automatic discovery for future Python node modules. The current package does not register any workflow nodes.

Run validation commands from the repository root:

~~~~bash
python -m py_compile __init__.py features/*.py
python -m unittest discover -s tests -p 'test_*.py' -v
node --check web/js/graphArrange.js
node --test
~~~~

GitHub Actions runs the Python package and registry checks, JavaScript syntax validation, and frontend tests.

## Attribution and licensing

The Auto Arrange Graph implementation is adapted from the graph-arrangement feature in [pythongosssss/ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts/blob/609f3afaa74b2f88ef9ce8d939626065e3247469/web/js/graphArrange.js), Copyright (c) 2023 pythongosssss. The upstream project is MIT-licensed; its copyright attribution is retained in this repository's LICENSE file.

The remaining original Phantom God project code is Copyright (c) 2026 midnight-god-01. This project is distributed under the MIT License. See LICENSE for the complete license text.
