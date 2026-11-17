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
- Every text field can be typed into or connected to another ComfyUI STRING output.
- Set a custom delimiter. The default is one space; commas, pipes, and newline separators work too.
- Fields are concatenated in numeric order: text_1, text_2, text_3, and so on.
- Empty fields are skipped, so they do not create duplicate delimiters.
- Dynamic fields and their values are restored when a workflow is reopened.

The node returns one STRING output.

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
node --test
~~~~

GitHub Actions runs the Python and JavaScript checks on pushes and pull requests. Dependabot checks workflow actions weekly.

## Compatibility and implementation

The package supports ComfyUI v0.45.0 and newer. The Python entry point exports NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, and WEB_DIRECTORY = "./web/js". Python node definitions are loaded from features/; frontend extension files are loaded from web/js/.

The Concatenate Text backend accepts explicitly defined text_1 and text_2 inputs plus validated dynamic text_N inputs. Its frontend extension adds matching multiline widgets and STRING sockets, restores those fields from saved workflows, and supplies the Add Text button. The backend's optional-input mapping follows ComfyUI's documented dynamic-input pattern.

Auto Arrange Graph continues to use ComfyUI's app.registerExtension() and getCanvasMenuItems() APIs. It does not patch LGraphCanvas prototypes or import deprecated /scripts/ui.js APIs.

## Troubleshooting

1. Confirm the repository is directly inside ComfyUI/custom_nodes/phantom-god-comfyui-nodes/ and that its root __init__.py is present.
2. Restart the ComfyUI server after updating. A browser refresh alone cannot load new Python node definitions.
3. Hard-refresh the browser after the server restarts.
4. Confirm the ComfyUI startup log contains no import error for phantom-god-comfyui-nodes.
5. Open the browser developer console and check for [Phantom God] messages from the frontend extensions.
6. Auto Arrange Graph commands appear when right-clicking an empty canvas area. The Concatenate Text node appears in the node search under Phantom God / Text.

## Source and attribution

The Auto Arrange Graph placement behavior is adapted from the Auto Arrange Graph script in [pythongosssss/ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts). The upstream MIT copyright notice is retained in LICENSE.
