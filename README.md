# Phantom God ComfyUI Nodes

A lightweight ComfyUI custom-node package with graph arrangement tools and a Pixaroma-style stacked LoRA loader that modifies the diffusion model only.

**Current version:** 1.6.3  
**Minimum requirements:** ComfyUI 0.46.0 or newer; Python 3.10 or newer

## Features

### Auto Arrange Graph

Adds two commands to the graph canvas context menu:

- **Arrange (float left)** uses ComfyUI's native graph arrangement.
- **Arrange (float right)** arranges nodes by execution order, right-aligns nodes within columns, and moves upstream nodes toward their earliest downstream use. Save Image and Preview Image nodes are prioritized within each column.

Right-click an empty area of the graph canvas to access the commands. These are canvas actions, not workflow nodes.

### LoRA Loader (Model Only) - Phantom God

A stacked LoRA node styled after Pixaroma's LoRA Loader. It has exactly one visible `MODEL` input and one `MODEL` output containing the model after the enabled LoRAs are applied. It has no `CLIP` socket, CLIP output, CLIP strength control, or trigger-string socket.

Each row has a searchable LoRA file selector, an independent model-strength field (-100 to 100, matching ComfyUI), an information button, and an on/off switch. Add up to 64 rows, toggle all rows together, and right-click a row to move, duplicate, or remove it. The gear menu controls default strength, strength step, file-extension display, accent colour, and LoRA memory use. Missing files are marked in the UI; the backend skips missing or failed LoRAs and reports them in the ComfyUI console.

The information panel reads the embedded safetensors header (without loading tensor weights) and displays available base-model, rank, alpha, training-image count, and date metadata. Metadata lookup is offline; Pixaroma's optional Civitai lookup, thumbnail editing, and XY Plot sweep integration are not included in this implementation.

LoRAs are applied in row order through ComfyUI's `comfy.sd.load_lora_for_models(model, None, weights, strength_model, 0.0)` API, following the native `LoraLoaderModelOnly` behavior. The serialized LoRA stack is stored in a standard STRING widget that the frontend hides while preserving normal ComfyUI prompt serialization. The visible controls are rendered as a DOM widget. The frontend supports Classic LiteGraph and adapts DOM widget visibility for Nodes 2.0.

The LoRA browser source is tracked as `web/js/pixaromaLoraModelOnly.js.gz` and expanded automatically when this custom-node package is imported. GitHub Actions also expands it before running browser syntax and regression tests.

## Installation

1. Close ComfyUI.
2. Open a terminal in the ComfyUI `custom_nodes` directory.
3. Clone this repository:

```bash
git clone https://github.com/midnight-god-01/phantom-god-comfyui-nodes.git
```

4. Start ComfyUI again and refresh the browser interface.

No separate pip or npm installation is required. The package uses the Python and frontend APIs provided by ComfyUI.

## Updating

From the custom node directory, run:

```bash
cd phantom-god-comfyui-nodes
git pull
```

Restart the ComfyUI server after updating, then refresh the browser interface.

## Compatibility

The package targets ComfyUI 0.46.0 or newer and Python 3.10 or newer. It uses the supported `getCanvasMenuItems` extension hook for Auto Arrange Graph, standard ComfyUI widget serialization for the hidden LoRA stack state, and the native model-only LoRA patching API.

## Troubleshooting

- **The arrange commands are not visible:** Right-click an empty area of the graph canvas rather than a node.
- **The browser extension does not load:** Confirm the repository is located at `ComfyUI/custom_nodes/phantom-god-comfyui-nodes`, restart the ComfyUI server, and hard-refresh the browser.
- **The package fails during startup:** Check the ComfyUI terminal for Python import errors and confirm the installed ComfyUI version meets the minimum requirement.
- **The LoRA list is empty:** Confirm the files are inside ComfyUI's configured `models/loras` directories and that the server can read them.

## Development and validation

The repository keeps the frontend extensions, Python node, and tests separate:

```text
.
├── __init__.py
├── features/
│   ├── __init__.py
│   └── pixaroma_lora_model_only.py
├── web/js/
│   ├── graphArrange.js
│   └── pixaromaLoraModelOnly.js.gz
├── tests/
│   ├── graphArrange.test.mjs
│   ├── pixaromaLoraModelOnly.test.mjs
│   ├── test_feature_registry.py
│   └── test_pixaroma_lora_model_only.py
├── .github/workflows/validate.yml
├── CHANGELOG.md
├── LICENSE
├── package.json
└── pyproject.toml
```

For a fresh checkout, run this once before local Node.js checks/tests:

```bash
python -c "import gzip,pathlib; p=pathlib.Path('web/js/pixaromaLoraModelOnly.js.gz'); p.with_suffix('').write_bytes(gzip.decompress(p.read_bytes()))"
```

Then run from the repository root:

```bash
python -m py_compile __init__.py features/*.py
python -m unittest discover -s tests -p 'test_*.py' -v
node --check web/js/graphArrange.js
node --check web/js/pixaromaLoraModelOnly.js
node --test
```

GitHub Actions runs Python checks on Python 3.10 and 3.13, JavaScript syntax checks, and frontend tests.

## Attribution and licensing

The LoRA loader's visual design and interaction pattern are inspired by [Pixaroma's ComfyUI-Pixaroma](https://github.com/pixaroma/ComfyUI-Pixaroma), Copyright (c) 2026 pixaroma, MIT License. This implementation is independently integrated into Phantom God and does not import Pixaroma's shared frontend framework or server routes.

The Auto Arrange Graph implementation is adapted from [pythongosssss/ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts/blob/609f3afaa74b2f88ef9ce8d939626065e3247469/web/js/graphArrange.js), Copyright (c) 2023 pythongosssss, MIT License.

The remaining original Phantom God project code is Copyright (c) 2026 midnight-god-01. See [LICENSE](LICENSE) for the MIT license terms and retained notices.
