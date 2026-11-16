"""Phantom God ComfyUI frontend-only extension pack."""

# ComfyUI's V1 custom-node loader requires NODE_CLASS_MAPPINGS to exist.
# An empty mapping is intentional: this repository adds frontend menu actions,
# not draggable or executable backend nodes.
NODE_CLASS_MAPPINGS = {}

# ComfyUI serves JavaScript files from this directory as frontend extensions.
WEB_DIRECTORY = "./web/js"

__all__ = ["NODE_CLASS_MAPPINGS", "WEB_DIRECTORY"]
