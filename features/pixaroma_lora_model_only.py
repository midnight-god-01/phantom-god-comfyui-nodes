"""Pixaroma-inspired stacked LoRA loader for the diffusion MODEL only.

The frontend stores each row in node.properties and mirrors the execution state
into a standard STRING widget hidden from the UI. ComfyUI serializes that widget
through its normal prompt path. The node has one visible MODEL input and one
MODEL output; it does not expose CLIP or prompt-trigger sockets.
"""

import json
import math
import ntpath
import os
import struct

import comfy.sd
import comfy.utils
import folder_paths

MAX_ROWS = 64
MAX_SAFETENSORS_HEADER = 16 * 1024 * 1024


def _parse_state(value):
    """Normalize workflow state; malformed values degrade to an empty stack."""
    try:
        raw = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}

    raw_rows = raw.get("loras", [])
    if not isinstance(raw_rows, list):
        raw_rows = []

    rows = []
    for item in raw_rows[:MAX_ROWS]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()

        try:
            strength = float(item.get("strength", 1.0))
        except (TypeError, ValueError, OverflowError):
            strength = 0.0
        if not math.isfinite(strength) or not -100.0 <= strength <= 100.0:
            strength = 0.0

        rows.append({
            "name": name,
            "on": bool(item.get("on", True)),
            "strength": strength,
        })

    cache_mode = raw.get("cacheMode", "last")
    if cache_mode not in ("last", "all", "none"):
        cache_mode = "last"
    return {"loras": rows, "cacheMode": cache_mode}


def _resolve(name):
    """Resolve a ComfyUI LoRA library name; never accept arbitrary filesystem paths."""
    if not isinstance(name, str) or not name or "\x00" in name:
        return None

    portable = name.replace("\\", "/")
    drive, _tail = ntpath.splitdrive(name)
    if drive or portable.startswith("/") or os.path.isabs(name) or ntpath.isabs(name):
        return None
    if any(part == ".." for part in portable.split("/")):
        return None

    # Workflows may move between Windows and POSIX hosts, whose model-list
    # path separators differ. Try both without allowing absolute paths.
    candidates = [name, portable, portable.replace("/", "\\")]
    candidates = list(dict.fromkeys(candidates))

    for candidate in candidates:
        try:
            path = folder_paths.get_full_path("loras", candidate)
        except (OSError, TypeError, ValueError):
            path = None
        if path and os.path.isfile(path):
            return path
    return None


class PixaromaLoraModelOnly:
    DESCRIPTION = (
        "Stack multiple LoRAs in one node. Each row has its own file, model "
        "strength and on/off switch. LoRAs are applied to the diffusion MODEL "
        "only. The node has one MODEL input and one MODEL output, with no CLIP "
        "or trigger-string sockets."
    )
    SEARCH_ALIASES = ["lora", "load lora", "apply lora", "lora loader", "model only"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL", {"tooltip": "The diffusion model to modify."}),
                # Standard ComfyUI widget input; the frontend hides it while
                # keeping it in prompt serialization for backend execution.
                "lora_state": ("STRING", {"default": "{}"}),
            },
        }

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("MODEL",)
    OUTPUT_TOOLTIPS = ("The diffusion model with enabled LoRAs applied in row order.",)
    FUNCTION = "apply"
    CATEGORY = "👑 Phantom God/🧰 Utility"

    def __init__(self):
        self._cache = {}
        self._last_path = None

    @classmethod
    def IS_CHANGED(cls, lora_state="{}", **kwargs):
        """Invalidate ComfyUI's cache when an enabled LoRA appears or changes on disk."""
        state = _parse_state(lora_state)
        try:
            available = set(folder_paths.get_filename_list("loras"))
        except Exception:
            # Force another execution attempt if the model library becomes
            # available again after a transient folder-listing failure.
            return float("nan")

        stamps = []
        for row in state["loras"]:
            # Disabled and zero-strength rows cannot change the MODEL output.
            if not row["on"] or row["strength"] == 0:
                continue
            name = row["name"]
            portable = name.replace("\\", "/")
            variants = (name, portable, portable.replace("/", "\\"))
            hit = next((candidate for candidate in variants if candidate in available), None)
            if hit is None:
                stamps.append("missing:" + name)
                continue
            try:
                path = folder_paths.get_full_path("loras", hit)
                if not path:
                    raise OSError("LoRA path no longer resolves")
                stat = os.stat(path)
                stamps.append(f"{hit}:{stat.st_size}:{stat.st_mtime_ns}")
            except (OSError, TypeError, ValueError):
                stamps.append("missing:" + hit)
        return "|".join(stamps)

    def _load(self, path):
        stat = os.stat(path)
        stamp = (stat.st_size, stat.st_mtime_ns)
        cached = self._cache.get(path)
        if cached and cached[1] == stamp:
            return cached[0], cached[2]

        try:
            weights, metadata = comfy.utils.load_torch_file(
                path, safe_load=True, return_metadata=True
            )
        except TypeError as exc:
            # Compatibility fallback only for older signatures lacking this keyword.
            if "return_metadata" not in str(exc):
                raise
            weights = comfy.utils.load_torch_file(path, safe_load=True)
            metadata = None

        self._cache[path] = (weights, stamp, metadata)
        return weights, metadata

    def apply(self, model, lora_state="{}"):
        state = _parse_state(lora_state)
        cache_mode = state["cacheMode"]
        last_this_run = None
        used_paths = set()

        for row in state["loras"]:
            if not row["on"] or row["strength"] == 0:
                continue

            path = _resolve(row["name"])
            if path is None:
                print(f"[Phantom God LoRA] Skipped missing or unsafe LoRA: {row['name']}")
                continue

            strength = row["strength"]
            try:
                weights, metadata = self._load(path)
                try:
                    model, _unused_clip = comfy.sd.load_lora_for_models(
                        model, None, weights, strength, 0.0,
                        lora_metadata=metadata,
                    )
                except TypeError as exc:
                    if "lora_metadata" not in str(exc):
                        raise
                    model, _unused_clip = comfy.sd.load_lora_for_models(
                        model, None, weights, strength, 0.0
                    )

                used_paths.add(path)
                if cache_mode != "all":
                    if last_this_run is not None and last_this_run != path:
                        self._cache.pop(last_this_run, None)
                    last_this_run = path
            except Exception as exc:
                print(f"[Phantom God LoRA] Failed to apply {row['name']}: {exc}")

        if cache_mode == "none":
            self._cache.clear()
            self._last_path = None
        elif cache_mode == "all":
            for path in list(self._cache):
                if path not in used_paths:
                    del self._cache[path]
        else:
            keep = last_this_run
            if keep is None and self._last_path in used_paths:
                keep = self._last_path
            for path in list(self._cache):
                if path != keep:
                    del self._cache[path]
            self._last_path = keep

        return (model,)


NODE_CLASS_MAPPINGS = {"PixaromaLoraModelOnly": PixaromaLoraModelOnly}
NODE_DISPLAY_NAME_MAPPINGS = {
    "PixaromaLoraModelOnly": "LoRA Loader (Model Only) - Phantom God"
}


def _read_safetensors_metadata(path):
    """Read only the bounded safetensors JSON header, never the tensor payload."""
    try:
        with open(path, "rb") as handle:
            raw_length = handle.read(8)
            if len(raw_length) != 8:
                return {}
            length = struct.unpack("<Q", raw_length)[0]
            if length <= 1 or length > MAX_SAFETENSORS_HEADER:
                return {}
            header = handle.read(length)
            if len(header) != length:
                return {}
        parsed = json.loads(header)
        metadata = parsed.get("__metadata__", {}) if isinstance(parsed, dict) else {}
        return metadata if isinstance(metadata, dict) else {}
    except (OSError, ValueError, TypeError, struct.error, json.JSONDecodeError):
        return {}


def _lora_info(name):
    """Return offline metadata for a LoRA library name, or None when unavailable."""
    path = _resolve(name)
    if path is None:
        return None

    metadata = _read_safetensors_metadata(path)
    model_text = " ".join(str(metadata.get(key, "")) for key in (
        "ss_base_model_version", "ss_sd_model_name", "modelspec.architecture",
        "modelspec.implementation",
    )).lower()
    if "flux" in model_text:
        family = "Flux"
    elif "sd3" in model_text or "stable-diffusion-3" in model_text:
        family = "SD3"
    elif any(value in model_text for value in ("sdxl", "xl_base", "illustrious", "pony")):
        family = "SDXL"
    elif any(value in model_text for value in ("sd_v2", "sd2", "v2-1", "768-v")):
        family = "SD2"
    elif any(value in model_text for value in ("sd_v1", "sd1", "v1-5", "v1.5", "sd-v1")):
        family = "SD1.5"
    else:
        family = ""

    title = metadata.get("modelspec.title") or metadata.get("ss_output_name")
    if not isinstance(title, str) or not title.strip():
        title = os.path.splitext(os.path.basename(path))[0]

    return {
        "title": title,
        "base_model": family,
        "rank": str(metadata.get("ss_network_dim", "") or ""),
        "alpha": str(metadata.get("ss_network_alpha", "") or ""),
        "num_images": str(metadata.get("ss_num_train_images", "") or ""),
        "date": str(metadata.get("modelspec.date", "") or ""),
    }


# Read-only metadata lookup. The route accepts only names in ComfyUI's own LoRA
# library and resolves them through folder_paths; it never accepts disk paths.
try:
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.get("/phantom-god/lora-info")
    async def phantom_god_lora_info(request):
        name = request.query.get("name", "")
        if not isinstance(name, str) or not name:
            return web.json_response({"ok": False, "error": "LoRA name is required."}, status=400)

        try:
            available = set(folder_paths.get_filename_list("loras"))
        except Exception:
            return web.json_response({"ok": False, "error": "LoRA library is unavailable."}, status=503)

        normalized = name.replace("\\", "/")
        candidates = {name, normalized, normalized.replace("/", "\\")}
        if not candidates.intersection(available):
            return web.json_response({"ok": False, "error": "LoRA not found."}, status=404)

        info = _lora_info(name)
        if info is None:
            return web.json_response({"ok": False, "error": "Could not read this LoRA file."}, status=404)
        return web.json_response({"ok": True, "info": info})

except Exception as exc:
    print(f"[Phantom God LoRA] Metadata route was not registered: {exc}")
