# Phantom God ComfyUI Nodes

A ComfyUI custom-node pack for graph arrangement and architecture-aware model enhancement.

**Current version:** 1.6.1  
**Requirements:** ComfyUI 0.46.0 or newer; Python 3.10 or newer

## Features

### Auto Arrange Graph

Adds two commands to the graph canvas context menu:

- **Arrange (float left)** uses ComfyUI's native graph arrangement.
- **Arrange (float right)** arranges nodes by execution order, right-aligns nodes within columns, and moves upstream nodes toward their earliest downstream use. Save Image and Preview Image nodes are prioritized within each column.

To access the commands, right-click an empty area of the graph canvas. These are canvas actions, not workflow nodes.

### Prompt Adherence Enhancer Pro

Adds an architecture-aware workflow node with exactly one `MODEL` input and one `MODEL` output. All controls are widgets. It adds no CLIP, conditioning, prompt, image, latent, or text-encoder sockets.

The node structurally detects the connected diffusion model and selects the matching adapter:

| Model family | Enhancement path |
|---|---|
| Krea 2 | Native 12-tap `txtfusion` residual enhancement, with optional `txtmlp` scaling |
| Anima | Post-LLM-adapter text-context scaling |
| MOSS-Image | Native `text_embedder` output scaling |
| Qwen-Image 2.1 | Native `txt_in` projection scaling |
| Z-Image / Z-Image-Turbo | Native `cap_embedder` caption scaling |

Detection is based on the underlying diffusion-model structure, not checkpoint or LoRA filenames. Architecture-compatible base, distilled/Turbo, and LoRA variants use the same adapter. The node does not guess a checkpoint's exact training variant from its architecture. Unsupported architectures are reported as unsupported and passed through unchanged.

**The detection display supports both ComfyUI renderers.** Nodes 2.0 uses read-only text widgets. Classic LiteGraph draws a compact detection panel directly on the node canvas. Both displays use the same backend detection result and retain the last result in node properties.

Place the node after the diffusion model loader and all model/LoRA loaders, before KSampler. A built-in ComfyUI ModelPatcher clone normally retains the wrapper; placing the node after all loaders is recommended for compatibility with third-party loaders.

The adapters are architecture-specific inference-time modifications. They do not train weights or rewrite prompts, and improved image quality or prompt adherence is not guaranteed. See the node's Info description and `NOTICE-PROMPT-ADHERENCE.md` for model support, implementation scope, limitations, and attribution.

## Installation

1. Close ComfyUI.
2. Open a terminal in the ComfyUI `custom_nodes` directory.
3. Clone this repository:

```bash
git clone https://github.com/midnight-god-01/phantom-god-comfyui-nodes.git
```

4. Start ComfyUI again and refresh the browser interface.

No separate pip or npm installation is required for normal ComfyUI use. The enhancer uses the PyTorch installation already provided by ComfyUI and ComfyUI's own Python/frontend APIs.

## Updating

From the custom node directory:

```bash
cd phantom-god-comfyui-nodes
git pull
```

Restart the ComfyUI server after updating, then hard-refresh the browser interface with **Ctrl + Shift + R** so the frontend extensions reload.

## Compatibility

The package targets ComfyUI 0.46.0 or newer and Python 3.10 or newer. Both Classic LiteGraph and Nodes 2.0 are supported. The detection display uses ComfyUI's `Comfy.VueNodes.Enabled` setting to select its renderer-specific presentation; switching renderers updates the display without requiring a different node or workflow.

Auto Arrange Graph uses ComfyUI's `getCanvasMenuItems` extension hook and the active canvas graph. It reads links from the graph's Map-based link collection and does not use the deprecated `ComfyApp.graph` getter.

## Troubleshooting

- **The arrange commands are not visible:** Right-click an empty area of the graph canvas rather than a node.
- **The detected model still says "Not detected yet":** Queue the workflow at least once. Detection runs when the node executes, not merely when a MODEL wire is connected.
- **The model is reported as unsupported:** Check that the loaded diffusion model uses one of the five supported native architectures. A similar checkpoint name is not sufficient for detection.
- **The display is missing in Classic mode:** Confirm the custom node's JavaScript extension loaded, restart ComfyUI, and hard-refresh the browser. The Classic display is drawn below the node's regular widgets.
- **The browser extension does not load:** Confirm the repository is located at `ComfyUI/custom_nodes/phantom-god-comfyui-nodes`, restart the ComfyUI server, and hard-refresh the browser.
- **The package fails during startup:** Check the ComfyUI terminal for Python import errors and confirm the installed ComfyUI version meets the minimum requirement.

## Development

The repository keeps backend feature modules, frontend extensions, and tests separate:

```text
.
├── __init__.py
├── features/
│   ├── __init__.py
│   ├── prompt_adherence_enhancer_pro.py
│   └── _paa_*.py
├── web/
│   └── js/
│       ├── graphArrange.js
│       └── prompt_adherence_enhancer_pro.js
├── tests/
│   ├── graphArrange.test.mjs
│   ├── promptAdherenceEnhancer.test.mjs
│   ├── test_architecture_adapters.py
│   ├── test_enhancer_math.py
│   ├── test_feature_registry.py
│   └── test_registration.py
├── .editorconfig
├── .gitattributes
├── .github/workflows/validate.yml
├── .gitignore
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── NOTICE-PROMPT-ADHERENCE.md
├── package.json
└── pyproject.toml
```

The `features` package automatically discovers Python modules that do not start with an underscore. The enhancer's underscored helper modules are deliberately private and are imported by its main node module; they do not register separate nodes. The pack currently registers one workflow node: Prompt Adherence Enhancer Pro.

Run validation commands from the repository root:

```bash
python -m py_compile __init__.py features/*.py
python -m unittest discover -s tests -p 'test_*.py' -v
npm run check:js
npm test
git diff --check
```

GitHub Actions runs the Python package and synthetic architecture tests on Python 3.10 and 3.13. It installs CPU-only PyTorch for CI, validates the frontend JavaScript, and runs the Node.js tests. No model weights are downloaded by the test suite.

## Attribution and licensing

The Auto Arrange Graph implementation is adapted from the graph-arrangement feature in [pythongosssss/ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts/blob/609f3afaa74b2f88ef9ce8d939626065e3247469/web/js/graphArrange.js), Copyright (c) 2023 pythongosssss. The upstream project's MIT copyright attribution is retained in `LICENSE`.

The Krea 2 legacy enhancement method includes code and profile values derived from the MIT-licensed ComfyUI-Krea2T-Enhancer project. Its separate copyright and license notice is retained in `NOTICE-PROMPT-ADHERENCE.md`.

The remaining original Phantom God project code is Copyright (c) 2026 midnight-god-01. The project is distributed under the MIT License; see `LICENSE` and the component notice for details.
