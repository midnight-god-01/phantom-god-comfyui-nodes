"""Model-only multi-LoRA stack node for ComfyUI."""

import json
import math


MAX_LORAS = 64
MIN_STRENGTH = -100.0
MAX_STRENGTH = 100.0


def _parse_state(raw_state):
    """Parse and validate the JSON state sent by the frontend."""
    if isinstance(raw_state, dict):
        state = raw_state
    elif isinstance(raw_state, str):
        try:
            state = json.loads(raw_state or "{}")
        except (TypeError, ValueError) as exc:
            raise ValueError("LoRA stack state is not valid JSON.") from exc
    else:
        state = {}

    if not isinstance(state, dict):
        raise ValueError("LoRA stack state must be a JSON object.")

    rows = state.get("loras", [])
    if not isinstance(rows, list):
        raise ValueError("The LoRA stack must contain a list of rows.")
    if len(rows) > MAX_LORAS:
        raise ValueError("The LoRA stack limit is {} rows.".format(MAX_LORAS))

    result = []
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError("LoRA row {} is invalid.".format(position))

        name = row.get("name", "")
        if not isinstance(name, str):
            raise ValueError("The LoRA name in row {} must be text.".format(position))
        name = name.strip().replace("\\", "/")

        enabled = row.get("on", True) is True
        try:
            strength = float(row.get("strength", 1.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("The strength in LoRA row {} is invalid.".format(position)) from exc

        if not math.isfinite(strength):
            raise ValueError("The strength in LoRA row {} must be finite.".format(position))
        if strength < MIN_STRENGTH or strength > MAX_STRENGTH:
            raise ValueError(
                "The strength in LoRA row {} must be between {} and {}.".format(
                    position, MIN_STRENGTH, MAX_STRENGTH
                )
            )

        result.append({"name": name, "on": enabled, "strength": strength})

    return result


class PhantomGodMultiLoraModelOnly:
    """Apply a configurable stack of LoRAs to MODEL only (no CLIP input/output)."""

    DESCRIPTION = (
        "Stack up to 64 LoRAs in one node. Each row has its own file picker, "
        "strength, on/off toggle, and remove button. Disabled and empty rows are "
        "ignored. This node modifies MODEL only and has no CLIP connection."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL", {"tooltip": "The diffusion model to modify."}),
            },
            "hidden": {
                "LoraStackState": ("STRING", {"default": "{}"}),
            },
        }

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("MODEL",)
    OUTPUT_TOOLTIPS = ("The input model with enabled LoRAs applied in row order.",)
    FUNCTION = "apply"
    CATEGORY = "Phantom God/Model"
    SEARCH_ALIASES = ["lora", "multi lora", "model only lora", "lora stack", "apply loras"]

    def __init__(self):
        # Keep only one LoRA tensor dictionary in memory at a time. The patched
        # MODEL retains its own patches, avoiding a second in-memory copy of the stack.
        self._cached_lora_path = None
        self._cached_lora = None
        self._cached_metadata = None

    @classmethod
    def IS_CHANGED(cls, LoraStackState="{}", **kwargs):
        """Invalidate ComfyUI's node cache when an enabled LoRA file changes."""
        try:
            import os
            import folder_paths

            stamps = []
            seen = set()
            for row in _parse_state(LoraStackState):
                if not row["on"] or not row["name"] or row["strength"] == 0:
                    continue
                name = row["name"]
                if name in seen:
                    continue
                seen.add(name)
                try:
                    path = folder_paths.get_full_path_or_raise("loras", name)
                    stat = os.stat(path)
                    stamps.append("{}:{}:{}".format(name, stat.st_size, stat.st_mtime_ns))
                except Exception:
                    stamps.append("{}:missing".format(name))
            return "|".join(stamps)
        except Exception:
            return "invalid-lora-stack-state"

    def _load_lora(self, path):
        import comfy.utils

        if path == self._cached_lora_path and self._cached_lora is not None:
            return self._cached_lora, self._cached_metadata

        self._cached_lora_path = None
        self._cached_lora = None
        self._cached_metadata = None

        try:
            lora, metadata = comfy.utils.load_torch_file(
                path, safe_load=True, return_metadata=True
            )
        except TypeError:
            # Older ComfyUI builds do not accept return_metadata.
            lora = comfy.utils.load_torch_file(path, safe_load=True)
            metadata = None

        self._cached_lora_path = path
        self._cached_lora = lora
        self._cached_metadata = metadata
        return lora, metadata

    def apply(self, model, LoraStackState="{}"):
        import folder_paths
        import comfy.sd

        if model is None:
            raise ValueError("Connect a MODEL input before applying LoRAs.")

        rows = _parse_state(LoraStackState)
        current_model = model
        applied = 0

        for row in rows:
            if not row["on"] or not row["name"] or row["strength"] == 0:
                continue

            name = row["name"]
            strength = row["strength"]

            try:
                path = folder_paths.get_full_path_or_raise("loras", name)
                lora, metadata = self._load_lora(path)

                try:
                    current_model, _ = comfy.sd.load_lora_for_models(
                        current_model, None, lora, strength, 0.0, lora_metadata=metadata
                    )
                except TypeError:
                    # Compatibility with ComfyUI versions predating lora_metadata.
                    current_model, _ = comfy.sd.load_lora_for_models(
                        current_model, None, lora, strength, 0.0
                    )

                if current_model is None:
                    raise RuntimeError("ComfyUI returned an empty MODEL after applying the LoRA.")
                applied += 1
            except Exception as exc:
                raise RuntimeError(
                    "Phantom God Multi LoRA: could not apply {!r}: {}".format(name, exc)
                ) from exc

        print("[Phantom God Multi LoRA] applied {} LoRA(s).".format(applied))
        return (current_model,)


NODE_CLASS_MAPPINGS = {
    "PhantomGodMultiLoraModelOnly": PhantomGodMultiLoraModelOnly,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PhantomGodMultiLoraModelOnly": "Multi LoRA Loader (Model Only) (Phantom God)",
}
