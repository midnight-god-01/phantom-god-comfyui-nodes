"""Model-only multi-LoRA stack node for ComfyUI."""

import json
import math

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

    result = []
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError("LoRA row {} is invalid.".format(position))

        name = row.get("name", "")
        if not isinstance(name, str):
            raise ValueError("The LoRA name in row {} must be text.".format(position))
        name = name.strip().replace("\\", "/")

        # Workflow files are user-controlled input. Accept relative paths so
        # LoRAs can live in subdirectories, but reject absolute paths and
        # traversal segments before passing a name to ComfyUI's path resolver.
        if name and (
            "\x00" in name
            or name.startswith("/")
            or (len(name) >= 2 and name[1] == ":")
            or any(part in ("", ".", "..") for part in name.split("/"))
        ):
            raise ValueError(
                "The LoRA name in row {} must be a relative path inside the LoRA folder.".format(
                    position
                )
            )

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



def _model_patch_delta(previous_model, patched_model):
    """Return True/False when ComfyUI's model-patcher state exposes a delta."""
    if previous_model is None or patched_model is None:
        return None

    before_uuid = getattr(previous_model, "patches_uuid", None)
    after_uuid = getattr(patched_model, "patches_uuid", None)
    if before_uuid is not None and after_uuid is not None and before_uuid != after_uuid:
        return True

    inspected = False
    before_patches = getattr(previous_model, "patches", None)
    after_patches = getattr(patched_model, "patches", None)
    if isinstance(before_patches, dict) and isinstance(after_patches, dict):
        inspected = True
        for key, entries in after_patches.items():
            old_entries = before_patches.get(key, ())
            try:
                if len(entries) > len(old_entries):
                    return True
            except TypeError:
                if entries is not old_entries:
                    return True

    for attribute in ("object_patches", "weight_wrapper_patches"):
        before = getattr(previous_model, attribute, None)
        after = getattr(patched_model, attribute, None)
        if isinstance(before, dict) and isinstance(after, dict):
            inspected = True
            for key, value in after.items():
                if key not in before or before[key] is not value:
                    return True

    return False if inspected or (before_uuid is not None and after_uuid is not None) else None


class PhantomGodMultiLoraModelOnly:
    """Apply a configurable stack of LoRAs to MODEL only (no CLIP input/output)."""

    DESCRIPTION = (
        "Stack any number of LoRAs in one node. Each row has its own file picker, "
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
        # Keep at most one raw LoRA state dictionary in memory. The key includes
        # the file signature so replacing a file at the same path reloads it.
        self._cached_lora_signature = None
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
                    stamps.append(
                        "{}:{}:{}:{}".format(
                            name,
                            stat.st_size,
                            stat.st_mtime_ns,
                            getattr(stat, "st_ino", 0),
                        )
                    )
                except Exception:
                    stamps.append("{}:missing".format(name))
            return "|".join(stamps)
        except Exception:
            return "invalid-lora-stack-state"

    def _load_lora(self, path):
        import os
        import comfy.utils

        stat = os.stat(path)
        signature = (
            path,
            stat.st_size,
            getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
            getattr(stat, "st_ino", 0),
        )
        if signature == self._cached_lora_signature and self._cached_lora is not None:
            return self._cached_lora, self._cached_metadata

        self._cached_lora_signature = None
        self._cached_lora = None
        self._cached_metadata = None

        try:
            lora, metadata = comfy.utils.load_torch_file(
                path, safe_load=True, return_metadata=True
            )
        except TypeError as exc:
            # Only fall back when an older ComfyUI rejects this keyword;
            # preserve TypeErrors raised while actually deserializing weights.
            if "return_metadata" not in str(exc):
                raise
            lora = comfy.utils.load_torch_file(path, safe_load=True)
            metadata = None

        self._cached_lora_signature = signature
        self._cached_lora = lora
        self._cached_metadata = metadata
        return lora, metadata

    def apply(self, model, LoraStackState="{}", **kwargs):
        """Apply each enabled LoRA in order, cloning model patches sequentially."""
        if LoraStackState in (None, ""):
            LoraStackState = kwargs.get("lora_stack_state", "{}")
        if model is None:
            raise ValueError("Connect a MODEL input before applying LoRAs.")

        rows = _parse_state(LoraStackState)
        active_rows = [
            row for row in rows
            if row["on"] and row["name"] and row["strength"] != 0
        ]
        if not active_rows:
            return (model,)

        import folder_paths
        import comfy.sd

        current_model = model
        applied = 0
        for row in active_rows:
            name = row["name"]
            strength = row["strength"]
            try:
                path = folder_paths.get_full_path_or_raise("loras", name)
                lora, metadata = self._load_lora(path)
                # Match ComfyUI's native LoraLoaderModelOnly execution path.
                previous_model = current_model
                current_model, _ = comfy.sd.load_lora_for_models(
                    previous_model, None, lora, strength, 0.0,
                    lora_metadata=metadata,
                )
                if current_model is None:
                    raise RuntimeError("ComfyUI did not return a patched MODEL.")
                if _model_patch_delta(previous_model, current_model) is False:
                    raise RuntimeError(
                        "The LoRA contains no weights compatible with this diffusion model. "
                        "Check whether it was trained for this model architecture or only "
                        "contains text-encoder weights."
                    )
                applied += 1
            except TypeError as exc:
                # Only fall back for an older API that rejects this keyword;
                # do not hide unrelated TypeErrors raised inside ComfyUI.
                if "lora_metadata" not in str(exc):
                    raise RuntimeError(
                        "Phantom God Multi LoRA: could not apply {!r}: {}".format(name, exc)
                    ) from exc
                try:
                    previous_model = current_model
                    current_model, _ = comfy.sd.load_lora_for_models(
                        previous_model, None, lora, strength, 0.0
                    )
                    if current_model is None:
                        raise RuntimeError("ComfyUI returned an empty MODEL.")
                    if _model_patch_delta(previous_model, current_model) is False:
                        raise RuntimeError(
                            "The LoRA contains no weights compatible with this diffusion model."
                        )
                    applied += 1
                except Exception as fallback_exc:
                    raise RuntimeError(
                        "Phantom God Multi LoRA: could not apply {!r}: {}".format(
                            name, fallback_exc
                        )
                    ) from fallback_exc
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
