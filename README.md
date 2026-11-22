# Phantom God ComfyUI Nodes

A ComfyUI custom-node pack combining graph-canvas arrangement and architecture-aware model enhancement.

**Current version:** 1.5.9  
**Minimum requirements:** ComfyUI 0.46.0 or newer; Python 3.10 or newer

## Features

### Auto Arrange Graph

Adds two commands to the graph canvas context menu:

- **Arrange (float left)** uses ComfyUI's native graph arrangement.
- **Arrange (float right)** arranges nodes by execution order, right-aligns nodes within columns, and moves upstream nodes toward their earliest downstream use. Save Image and Preview Image nodes are prioritized within each column.

To access the commands, right-click an empty area of the graph canvas. These are canvas actions, not workflow nodes.

### Prompt Adherence Enhancer Pro

Adds an architecture-aware workflow node with exactly one `MODEL` input and one `MODEL` output. All controls are widgets; it adds no CLIP, conditioning, prompt, image, latent, or text-encoder sockets.

The node structurally detects the connected diffusion model and selects the matching adapter automatically:

| Model family | Enhancement path |
|---|---|
| Krea 2 | Native 12-tap `txtfusion` residual enhancement, with optional `txtmlp` scaling |
| Anima | Post-LLM-adapter text-context scaling |
| MOSS-Image | Native `text_embedder` output scaling |
| Qwen-Image 2.1 | Native `txt_in` projection scaling |
| Z-Image / Z-Image-Turbo | Native `cap_embedder` caption scaling |

The node displays the detected model family and selected adapter in two read-only rows. Detection is based on the underlying diffusion-model structure, not checkpoint or LoRA filenames. Architecture-compatible base, distilled/Turbo, and LoRA variants use the same adapter. Unsupported architectures pass through unchanged.

Place the node after the diffusion model loader and all model/LoRA loaders, before KSampler. A built-in ComfyUI ModelPatcher clone normally retains the wrapper; placing the node after all loaders is recommended for compatibility with third-party loaders.

The five adapter methods are architecture-specific inference-time modifications. They do not train weights or rewrite prompts, and improved image quality or prompt adherence is not guaranteed. See the node's Info description and `NOTICE-PROMPT-ADHERENCE.md` for implementation and attribution details.

## Installation

1. Close ComfyUI.
2. Open a terminal in the ComfyUI `custom_nodes` directory.
3. Clone this repository:

~~~~bash
git clone https://github.com/midnight-god-01/phantom-god-comfyui-nodes.git
~~~~

4. Start ComfyUI again and refresh the browser interface.

The repository does not require a separate pip or npm installation step. The Prompt Adherence Enhancer uses PyTorch already provided by the ComfyUI environment, plus ComfyUI's Python and frontend APIs.

## Updating

From the custom node directory, run:

~~~~bash
cd phantom-god-comfyui-nodes
git pull
~~~~

Restart the ComfyUI server after updating. Then refresh the browser interface so ComfyUI reloads the JavaScript extension.

## Compatibility

The package targets ComfyUI 0.46.0 or newer and Python 3.10 or newer, matching the current ComfyUI core requirements. Compatibility was re-checked against the ComfyUI 0.46.0 release and current core/frontend source on November 20, 2026. The v0.46.0 release included `comfyui-frontend-package` 1.59.6; the current ComfyUI `master` requirements now pin 1.59.10 (updated November 20, 2026). The standalone ComfyUI frontend release is 1.61.4. Auto Arrange Graph uses the supported `getCanvasMenuItems` extension hook and the active graph supplied by the canvas. It reads links from the graph's Map-based link collection and avoids the deprecated `ComfyApp.graph` getter.

## Troubleshooting

- **The arrange commands are not visible:** Right-click an empty area of the graph canvas rather than a node.
- **The browser extension does not load:** Confirm the repository is located at `ComfyUI/custom_nodes/phantom-god-comfyui-nodes`, restart the ComfyUI server, and hard-refresh the browser.
- **The package fails during startup:** Check the ComfyUI terminal for Python import errors and confirm the installed ComfyUI version meets the minimum requirement.

## Development

The repository keeps the frontend extension and tests separate:

~~~~text
.
├── __init__.py
├── features/
│   ├── __init__.py
│   ├── prompt_adherence_enhancer_pro.py
│   └── _paa_*.py              # private enhancer implementation modules
├── web/
│   └── js/
│       ├── graphArrange.js
│       └── prompt_adherence_enhancer_pro.js
├── tests/
│   ├── graphArrange.test.mjs
│   ├── test_feature_registry.py
│   └── test_*enhancer*.py
├── CHANGELOG.md
├── LICENSE
├── package.json
└── pyproject.toml
~~~~

The `features` package retains automatic discovery for future Python node modules. The current package does not register any workflow nodes.

Run validation commands from the repository root:

~~~~bash
python -m py_compile __init__.py features/*.py
python -m unittest discover -s tests -p 'test_*.py' -v
node --check web/js/graphArrange.js
node --check web/js/prompt_adherence_enhancer_pro.js
node --test
~~~~

GitHub Actions installs CPU-only PyTorch for the synthetic model-adapter tests, then runs Python package and registry checks, JavaScript syntax validation, and frontend tests.

## Attribution and licensing

The Auto Arrange Graph implementation is adapted from the graph-arrangement feature in [pythongosssss/ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts/blob/609f3afaa74b2f88ef9ce8d939626065e3247469/web/js/graphArrange.js), Copyright (c) 2023 pythongosssss. The upstream project is MIT-licensed; its copyright attribution is retained in this repository's LICENSE file.

The remaining original Phantom God project code is Copyright (c) 2026 midnight-god-01. This project is distributed under the MIT License. See LICENSE for the complete license text.
