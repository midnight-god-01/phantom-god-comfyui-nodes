"""Phantom God ComfyUI custom-node and frontend extension pack."""

from pathlib import Path
import gzip

from .features import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Expand the tracked, compressed browser source before ComfyUI serves WEB_DIRECTORY.
_PACKAGE_ROOT = Path(__file__).resolve().parent
_COMPRESSED_FRONTEND = _PACKAGE_ROOT / "web" / "js" / "pixaromaLoraModelOnly.js.gz"
_FRONTEND = _PACKAGE_ROOT / "web" / "js" / "pixaromaLoraModelOnly.js"
if _COMPRESSED_FRONTEND.is_file():
    try:
        _temporary = _FRONTEND.with_suffix(".js.tmp")
        _temporary.write_bytes(gzip.decompress(_COMPRESSED_FRONTEND.read_bytes()))
        _temporary.replace(_FRONTEND)
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        print(f"[Phantom God] Could not restore LoRA frontend asset: {exc}")

if NODE_CLASS_MAPPINGS:
    print(
        "[Phantom God] Registered workflow nodes: {}".format(
            ", ".join(sorted(NODE_CLASS_MAPPINGS))
        )
    )
else:
    print("[Phantom God] No workflow nodes registered; frontend extensions loaded.")

WEB_DIRECTORY = "./web/js"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
