"""Human-readable model detection metadata for the ComfyUI node UI."""
from __future__ import annotations

from ._paa_architecture_adapters import SUPPORTED_ARCHITECTURES, detect_architecture

ARCHITECTURE_INFO = {
    "krea2": {
        "name": "Krea 2",
        "adapter": "12-tap txtfusion residual + txtmlp scaling",
        "scope": "Krea text-fusion representations",
    },
    "anima": {
        "name": "Anima",
        "adapter": "post-LLM-adapter text-context scaling",
        "scope": "Adapted text context",
    },
    "moss_image": {
        "name": "MOSS-Image",
        "adapter": "text_embedder output scaling",
        "scope": "Text-token representations; image/video streams are not scaled",
    },
    "qwen_image21": {
        "name": "Qwen-Image 2.1",
        "adapter": "txt_in text-projection scaling",
        "scope": "Text-prefix representations; image/reference tokens are not scaled",
    },
    "z_image": {
        "name": "Z-Image",
        "adapter": "cap_embedder caption-projection scaling",
        "scope": "Caption-token representations",
    },
}

SUPPORTED_MODELS_SUMMARY = "Krea 2, Anima, MOSS-Image, Qwen-Image 2.1, and Z-Image (including architecture-compatible base, distilled/Turbo, and LoRA variants)."


def _get_diffusion_model(model_patcher):
    """Resolve the underlying diffusion module from a ComfyUI MODEL object."""
    getter = getattr(model_patcher, "get_model_object", None)
    if callable(getter):
        try:
            diffusion_model = getter("diffusion_model")
            if diffusion_model is not None:
                return diffusion_model
        except Exception:
            # A foreign/custom MODEL wrapper may not expose this lookup path;
            # continue with the documented ModelPatcher.model fallback.
            pass

    base_model = getattr(model_patcher, "model", None)
    diffusion_model = getattr(base_model, "diffusion_model", None)
    if diffusion_model is not None:
        return diffusion_model

    # Some extensions pass an already-unwrapped model object. Structural
    # detection keeps this fallback safe and does not rely on class names.
    return model_patcher


def detect_model_info(model_patcher) -> dict[str, str | bool | None]:
    """Return display-ready detection data without changing the MODEL object.

    The family is identified from the actual diffusion module layout. This
    deliberately does not infer a checkpoint's marketing name, training stage,
    or Turbo status from a filename or LoRA name.
    """
    lookup_failed = False
    try:
        diffusion_model = _get_diffusion_model(model_patcher)
    except Exception:
        # A nonstandard/custom MODEL wrapper may expose attributes that raise.
        # Treat inspection as diagnostic only; never block normal MODEL flow.
        diffusion_model = model_patcher
        lookup_failed = True

    try:
        architecture = detect_architecture(diffusion_model)
    except Exception:
        architecture = None
        lookup_failed = True
    model_class = type(diffusion_model).__name__

    if architecture in SUPPORTED_ARCHITECTURES:
        info = ARCHITECTURE_INFO[architecture]
        details = f"Class: {model_class} | Adapter: {info['adapter']}"
        return {
            "detected_model": info["name"],
            "detection_details": details,
            "architecture": architecture,
            "model_class": model_class,
            "supported": True,
        }

    inspection_status = " Model inspection was incomplete." if lookup_failed else ""
    details = (
        f"Class: {model_class} | No supported adapter matched; "
        f"the MODEL is passed through unchanged.{inspection_status} Supported families: "
        f"{SUPPORTED_MODELS_SUMMARY}"
    )
    return {
        "detected_model": "Unsupported model — pass-through",
        "detection_details": details,
        "architecture": None,
        "model_class": model_class,
        "supported": False,
    }
