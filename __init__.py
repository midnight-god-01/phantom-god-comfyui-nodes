"""Phantom God ComfyUI custom-node and frontend extension pack."""

from .features import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Make backend registration visible in the ComfyUI startup console. This is
# useful when a newly installed node does not yet appear in the frontend search.
print(
    "[Phantom God] Registered workflow nodes: {}".format(
        ", ".join(sorted(NODE_CLASS_MAPPINGS))
    )
)

# ComfyUI serves every JavaScript extension in this directory.
WEB_DIRECTORY = "./web/js"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
