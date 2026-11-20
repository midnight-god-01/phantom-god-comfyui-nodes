"""Phantom God ComfyUI custom-node and frontend extension pack."""

from .features import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

if NODE_CLASS_MAPPINGS:
    print(
        "[Phantom God] Registered workflow nodes: {}".format(
            ", ".join(sorted(NODE_CLASS_MAPPINGS))
        )
    )
else:
    print("[Phantom God] No workflow nodes registered; frontend extensions loaded.")

# ComfyUI serves every JavaScript extension in this directory.
WEB_DIRECTORY = "./web/js"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
