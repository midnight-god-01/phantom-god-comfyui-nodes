# Phantom God ComfyUI Nodes

A modular ComfyUI custom-node pack. Features are kept in separate Python and JavaScript modules so new tools can be added without rewriting the package entry point or disturbing existing features.

## Features

### Auto Arrange Graph

Right-click an empty area of the graph canvas to access two commands:

- **Arrange (float left)** — delegates to ComfyUI's native graph.arrange() layout.
- **Arrange (float right)** — arranges nodes by execution order, moves upstream nodes toward their earliest downstream use, and right-aligns nodes inside each column. SaveImage and PreviewImage nodes are prioritized at the top of their column.

These are canvas context-menu commands, not draggable workflow nodes.

### Concatenate Text (Phantom God)

Find **Concatenate Text (Phantom God)** under **Phantom God / Text**.

- Starts with two multiline text fields.
- Click **Add Text** to add as many more fields as needed.
- The Add Text control has rounded corners and matching text-field labels/placeholders such as **Text 3**.
- Every text field can be typed into or connected to another ComfyUI STRING output.
- Use the matching **× Text N** control to remove any individual field, including either of the initial two fields.
- All text fields are optional, so removing every text field does not leave a required-input validation error.
- Set a custom delimiter. The default is one space; commas, pipes, and newline separators work too.
- Fields are concatenated in numeric order: text_1, text_2, text_3, and so on.
- Empty fields are skipped, so they do not create duplicate delimiters.
- Remaining dynamic fields restore by widget name on recent frontends and fall back to positional values for older workflow files.

The node returns one STRING output.

### Multi LoRA Loader (Model Only) (Phantom God)

Find **Multi LoRA Loader (Model Only) (Phantom God)** under **Phantom God / Model**.

- Connect one **MODEL** input and receive one modified **MODEL** output.
- There is deliberately no CLIP input or CLIP output. This node applies LoRAs to the diffusion model only.
- Click **＋ Add LoRA** to add up to 64 rows.
- Each row has its own LoRA file picker, strength control, **ON/OFF** toggle, and **×** remove button.
- The file picker is populated from ComfyUI's current `/models/loras` endpoint. Use the refresh button after adding or removing LoRA files while ComfyUI is running.
- Rows are applied in their displayed order. Disabled, blank, and zero-strength rows are skipped.
- Strength supports negative and positive values from -100 to 100.
- The selected files, strengths, toggles, and row order are saved with the workflow.
- The backend uses ComfyUI's `comfy.utils.load_torch_file` and `comfy.sd.load_lora_for_models` APIs. It keeps only one raw LoRA state dictionary cached at a time rather than retaining a full stack of large tensors in node memory.
- A missing or incompatible enabled LoRA produces a clear node execution error instead of silently returning an unchanged model.

## Install

Run this from your ComfyUI custom_nodes directory:

~~~~bash
git clone https://github.com/midnight-god-01/phantom-god-comfyui-nodes.git
~~~~

Restart the ComfyUI server, then hard-refresh the browser (Ctrl+Shift+R).

## Update

~~~~bash
cd phantom-god-comfyui-nodes
git pull
~~~~

Restart ComfyUI and hard-refresh the browser after updating.

## Add future features

The package uses automatic feature discovery. You do not need to edit the root __init__.py when adding another Python node.

1. Create a new Python module inside features/, for example features/my_new_node.py.
2. Define your node class in that file.
3. Export NODE_CLASS_MAPPINGS and, optionally, NODE_DISPLAY_NAME_MAPPINGS from that module.

~~~~python
class MyNewNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"text": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING",)
    FUNCTION = "run"
    CATEGORY = "Phantom God/My Category"

    def run(self, text):
        return (text,)

NODE_CLASS_MAPPINGS = {"PhantomGodMyNewNode": MyNewNode}
NODE_DISPLAY_NAME_MAPPINGS = {"PhantomGodMyNewNode": "My New Node"}
~~~~

4. When a node needs custom frontend behavior, create a separate JavaScript file directly inside web/js/, for example web/js/myNewNode.js. Register it with app.registerExtension() and give it a unique extension name. Keep each frontend feature in its own file.
5. Add tests under tests/, then run the checks below.

The registry imports every non-private Python module directly inside features/ and merges its node mappings. Private modules whose names start with an underscore are ignored. Avoid duplicate node mapping keys.

## Development checks

No third-party Python or JavaScript runtime dependencies are required by this repository.

~~~~bash
python -m py_compile __init__.py features/*.py
python -m unittest discover -s tests -p 'test_*.py'
node --check web/js/graphArrange.js
node --check web/js/concatenateText.js
node --check web/js/multiLoraModelOnly.js
node --test
~~~~

GitHub Actions runs the Python and JavaScript checks on pushes and pull requests. Dependabot checks workflow actions weekly.

## Compatibility and implementation

The package targets ComfyUI v0.45.0 and newer. The current compatibility audit checked core v0.45.0 with its bundled frontend 1.58.5, plus standalone frontend 1.61.2. The Python entry point exports NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, and WEB_DIRECTORY = "./web/js". Python node definitions are loaded from features/; frontend extension files are loaded from web/js/.

Concatenate Text uses an optional-input mapping that accepts dynamically named STRING inputs. Its frontend adds/removes the matching widget and socket together, and restores the remaining text widget values when a workflow is reopened.

Multi LoRA Loader stores its UI state in node properties and injects that state into a hidden STRING input during graphToPrompt. The Python backend applies enabled LoRAs sequentially to MODEL using ComfyUI's model patching API and passes no CLIP object to the loader API.

Auto Arrange Graph continues to use ComfyUI's app.registerExtension() and getCanvasMenuItems() APIs. It does not patch LGraphCanvas prototypes or import deprecated /scripts/ui.js APIs.

## Troubleshooting

1. Confirm the repository is directly inside ComfyUI/custom_nodes/phantom-god-comfyui-nodes/ and that its root __init__.py is present.
2. Restart the ComfyUI server after updating. A browser refresh alone cannot load new Python node definitions.
3. Hard-refresh the browser after the server restarts.
4. Confirm the ComfyUI startup log contains no import error for phantom-god-comfyui-nodes.
5. Open the browser developer console and check for [Phantom God] messages from the frontend extensions.
6. Auto Arrange Graph commands appear when right-clicking an empty canvas area. Concatenate Text appears under Phantom God / Text. Multi LoRA Loader appears under Phantom God / Model.
7. If the LoRA dropdown is stale after copying a new model file, use its refresh button. Ensure the LoRA is inside one of ComfyUI's configured `loras` model directories.

## Source and attribution

The Auto Arrange Graph placement behavior is adapted from the Auto Arrange Graph script in [pythongosssss/ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts). The upstream MIT copyright notice is retained in LICENSE.
