# Phantom God ComfyUI Nodes

A modular custom-node pack for ComfyUI. It combines focused workflow utilities with frontend controls, while keeping each feature isolated in its own Python and JavaScript module.

**Current version:** 1.4.0  
**Minimum requirements:** ComfyUI 0.45.0 or newer; Python 3.9 or newer

## Features

### Auto Arrange Graph

Adds two commands to the graph canvas context menu:

- **Arrange (float left)** uses ComfyUI's native graph arrangement.
- **Arrange (float right)** places nodes by execution order, right-aligns nodes within columns, and moves upstream nodes toward their earliest downstream use. Save Image and Preview Image nodes are prioritized within each column.

To access the commands, right-click an empty area of the graph canvas. These are canvas actions, not workflow nodes.

### Concatenate Text (Phantom God)

Find the node under **Phantom God / Text**.

- Starts with two optional multiline text fields.
- Use **Add Text** to create additional fields. Each field has a matching STRING input socket.
- Every field has an individual remove control, including the first two default fields.
- All text fields are optional, so the node remains valid when every field is removed.
- Choose any delimiter, including spaces, commas, pipes, or newline characters. The default delimiter is one space.
- Values are joined in numeric field order: Text 1, Text 2, Text 3, and so on.
- Empty values are skipped, preventing unwanted repeated delimiters.
- Remaining field values are restored when a workflow is reopened. Named widget values are preferred, with a positional fallback for older workflow data.

The node returns a single STRING output.

### Multi LoRA Loader (Model Only) (Phantom God)

Find the node under **Phantom God / Model**.

- Accepts one MODEL input and returns one modified MODEL output. It has no CLIP input or output.
- Supports up to 64 ordered LoRA rows.
- Each row has its own file selector, strength value, ON/OFF control, and remove button.
- The selector reads the available files from ComfyUI's LoRA model directory endpoint. Use **Refresh** after adding or removing model files while ComfyUI is running.
- Enabled rows are applied sequentially in their displayed order. Disabled, unselected, and zero-strength rows are skipped.
- Strength values can range from -100 to +100.
- Row order, filenames, strengths, and enabled states are saved with the workflow. The workflow stores references to model files, not copies of the LoRA weights.
- The backend uses ComfyUI's safe tensor-loading and model-patching APIs. It retains at most one raw LoRA state dictionary in the node cache.
- Changes to a LoRA file at the same path are detected using its file signature; the cached state dictionary is reloaded when the file changes.
- Missing or incompatible enabled LoRAs produce a node execution error with the affected filename.



### Responsive node controls (1.5.0)

The Concatenate Text and Multi LoRA nodes use width-aware control layouts. Concatenate Text provides an individual enable/disable toggle and a separate delete button for every text field. Multi LoRA has no fixed row-count limit; the row list expands with the widget content. Both nodes refresh their layout on resize, with separate sizing behavior for Classic LiteGraph and Nodes 2.0.

### Environment Manager (Phantom God)

Find the node under **Phantom God / System**. It inspects the active ComfyUI Python environment and lets you check, install, update, or repair Triton and SageAttention independently.

- Reports the exact Python executable, Python version, pip availability/version, PyTorch version, PyTorch CUDA runtime, CUDA availability, NVIDIA GPU, compute capability, and driver version when available.
- Checks Triton against the PyTorch-compatible version line. On Windows it uses the `triton-windows` distribution; on Linux it uses the official `triton` distribution.
- Checks SageAttention against a prebuilt wheel matching the active Python, PyTorch, CUDA runtime, operating system, and GPU architecture. It also checks the required Triton 3.0+ runtime. It uses the Comfy-Org wheel index and does not guess a nearby build.
- Installs into the same Python executable that is running ComfyUI. Triton and SageAttention have separate install/update controls.
- Does not upgrade, uninstall, or replace PyTorch or its dependencies. Installs use pip with dependency resolution disabled.
- Requires a restart of ComfyUI after a successful installation before testing the package.

The node requires a CUDA-enabled NVIDIA PyTorch environment for these two packages. SageAttention prebuilt wheels require an Ampere-class or newer GPU (compute capability 8.0+). If the exact SageAttention wheel is not available for the active environment, the node reports the mismatch instead of attempting a source build.

## Installation

1. Close ComfyUI.
2. Open a terminal in the ComfyUI custom_nodes directory.
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

Restart the ComfyUI server after updating Python code. Then refresh the browser interface. A browser refresh alone does not reload Python node definitions.

## Compatibility

The package declares ComfyUI 0.45.0 or newer and Python 3.9 or newer. The compatibility review used ComfyUI core 0.45.0 with its bundled frontend 1.58.5, and standalone frontend 1.61.2. ComfyUI frontend APIs can evolve independently of the core application, so behavior may vary across frontend builds.

The Auto Arrange Graph extension uses ComfyUI's extension registration and canvas-menu APIs. It reads graph links through the current Map-based link collection rather than patching legacy canvas prototypes.

The Concatenate Text node uses dynamically named optional STRING inputs. Its frontend keeps each widget, socket, and remove control synchronized.

The Multi LoRA Loader stores its interface state in node properties and inserts that state into the hidden backend input when ComfyUI builds the execution prompt. The backend applies LoRAs to MODEL only, using no CLIP object.

## Troubleshooting

- **A node does not appear:** Confirm the repository is located at ComfyUI/custom_nodes/phantom-god-comfyui-nodes and that the server was restarted.
- **The browser controls do not appear:** Refresh the browser after restarting ComfyUI. Check the browser developer console for messages beginning with [Phantom God].
- **A LoRA is missing from the selector:** Confirm the file is inside one of ComfyUI's configured LoRA directories, then use the selector's Refresh control.
- **A saved workflow reports a missing LoRA:** Restore the referenced file or choose an available replacement in the node.
- **A node fails during startup:** Check the ComfyUI terminal for Python import errors and confirm the installed ComfyUI version meets the minimum requirement.
- **The arrange commands are not visible:** Right-click an empty area of the graph canvas rather than a node.

## Development

The repository keeps backend features, frontend extensions, and tests separate:

~~~~text
.
├── __init__.py
├── features/
│   ├── __init__.py
│   ├── concatenate_text.py
│   └── multi_lora_model_only.py
├── web/
│   └── js/
│       ├── concatenateText.js
│       ├── graphArrange.js
│       └── multiLoraModelOnly.js
├── tests/
├── CHANGELOG.md
├── LICENSE
├── package.json
└── pyproject.toml
~~~~

To add a Python node, create a module directly inside features/ and export NODE_CLASS_MAPPINGS. NODE_DISPLAY_NAME_MAPPINGS is optional. The feature registry discovers non-private Python modules in that directory and merges their mappings; duplicate mapping keys raise an error.

A minimal node module looks like this:

~~~~python
class ExampleNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"text": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING",)
    FUNCTION = "run"
    CATEGORY = "Phantom God/Examples"

    def run(self, text):
        return (text,)


NODE_CLASS_MAPPINGS = {"PhantomGodExampleNode": ExampleNode}
NODE_DISPLAY_NAME_MAPPINGS = {"PhantomGodExampleNode": "Example Node"}
~~~~

For frontend behavior, add a JavaScript module directly inside web/js/ and register it with app.registerExtension(). Add regression tests under tests/.

Run the validation commands from the repository root:

~~~~bash
python -m py_compile __init__.py features/*.py
python -m unittest discover -s tests -p 'test_*.py' -v
node --check web/js/graphArrange.js
node --check web/js/concatenateText.js
node --check web/js/multiLoraModelOnly.js
node --test
~~~~

GitHub Actions runs the Python checks, feature-registry checks, JavaScript syntax checks, and frontend tests on pushes and pull requests.

## Attribution and licensing

The Auto Arrange Graph implementation is adapted from the graph-arrangement feature in [pythongosssss/ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts/blob/609f3afaa74b2f88ef9ce8d939626065e3247469/web/js/graphArrange.js), Copyright (c) 2023 pythongosssss. The upstream project is MIT-licensed; its copyright attribution is retained in this repository's LICENSE file.

The remaining original Phantom God project code is Copyright (c) 2026 midnight-god-01. This project is distributed under the MIT License. See LICENSE for the complete license text.
