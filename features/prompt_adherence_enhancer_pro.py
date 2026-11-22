"""Multi-architecture, MODEL-only prompt-adherence enhancer for ComfyUI."""
from __future__ import annotations

import threading
from contextlib import ExitStack
from typing import Any

from ._paa_model_detection_info import detect_model_info
from ._paa_architecture_adapters import (
    SUPPORTED_ARCHITECTURES,
    detect_architecture,
    run_anima_text_context_scale,
    run_qwen_text_projection_scale,
    run_text_module_output_scale,
    temporary_module_forward,
)
from ._paa_enhancer_math import (
    DEFAULT_OUTPUT_LIMIT,
    STRENGTH_MAX,
    STRENGTH_MIN,
    TEXT_SCALE_MAX,
    TEXT_SCALE_MIN,
    bounded_float,
    enhanced_txtfusion_forward,
    get_schedule_progress,
    scheduled_strength,
)

OPTION_KEY = "prompt_adherence_enhancer_pro"
WRAPPER_KEY = "prompt_adherence_enhancer_pro"
_PATCH_LOCK = threading.RLock()
_PATCH_STATE = threading.local()


def _transformer_options(args: tuple, kwargs: dict) -> dict | None:
    value = kwargs.get("transformer_options")
    if isinstance(value, dict) and OPTION_KEY in value:
        return value
    # ComfyUI's native MODEL wrappers pass transformer_options positionally in
    # several model families. Prefer the dict carrying our own node config.
    for candidate in reversed(args):
        if isinstance(candidate, dict) and OPTION_KEY in candidate:
            return candidate
    if isinstance(value, dict):
        return value
    for candidate in reversed(args):
        if isinstance(candidate, dict) and ("sample_sigmas" in candidate or "sigmas" in candidate):
            return candidate
    return None


def _apply_krea2(diffusion_model, executor, args, kwargs, strength, config, text_scale, diagnostics):
    """Krea 2's original txtfusion two-pass residual enhancement."""
    txtfusion = diffusion_model.txtfusion
    txtmlp = diffusion_model.txtmlp
    original_txtfusion_forward = txtfusion.forward
    original_txtmlp_forward = txtmlp.forward

    def enhanced_forward(x, mask=None, transformer_options=None):
        output, details = enhanced_txtfusion_forward(
            txtfusion,
            x,
            original_txtfusion_forward,
            strength=strength,
            profile=config.get("layer_profile", "legacy"),
            output_limit=bounded_float(
                config.get("output_limit", DEFAULT_OUTPUT_LIMIT),
                DEFAULT_OUTPUT_LIMIT,
                0.0,
                2.0,
            ),
            mask=mask,
            transformer_options=transformer_options or {},
            collect_debug=bool(config.get("debug", False)),
        )
        diagnostics.update(details or {})
        return output

    def scaled_txtmlp_forward(*call_args, **call_kwargs):
        return original_txtmlp_forward(*call_args, **call_kwargs) * text_scale

    patch_fusion = strength > 0.0 and bounded_float(
        config.get("output_limit", DEFAULT_OUTPUT_LIMIT), DEFAULT_OUTPUT_LIMIT, 0.0, 2.0
    ) > 0.0
    patch_mlp = text_scale != 1.0

    # Restore exact module instance state; do not leave bound-method objects
    # stored in module.__dict__ after sampling.
    with ExitStack() as stack:
        if patch_fusion:
            stack.enter_context(temporary_module_forward(txtfusion, enhanced_forward))
        if patch_mlp:
            stack.enter_context(temporary_module_forward(txtmlp, scaled_txtmlp_forward))
        return executor(*args, **kwargs)


def prompt_adherence_enhancer_pro_wrapper(executor, *args, **kwargs):
    """Dispatch a safe, architecture-specific enhancement during model sampling."""
    transformer_options = _transformer_options(args, kwargs)
    if transformer_options is None:
        return executor(*args, **kwargs)

    config = transformer_options.get(OPTION_KEY, {})
    if not config or not config.get("enabled", True):
        return executor(*args, **kwargs)
    # The temporary module-forward hooks below are shared model state. Guard
    # recursive invocation per thread, not in transformer_options: a shared
    # config flag would accidentally skip enhancement in parallel sampler
    # calls that are waiting on the patch lock.
    if getattr(_PATCH_STATE, "active", False):
        return executor(*args, **kwargs)

    diffusion_model = executor.class_obj
    architecture = detect_architecture(diffusion_model)
    if architecture not in SUPPORTED_ARCHITECTURES:
        if config.get("debug", False):
            print(
                "[PromptAdherenceEnhancerPro] "
                f"unsupported_model={type(diffusion_model).__name__}; "
                "passing MODEL through unchanged"
            )
        return executor(*args, **kwargs)

    schedule_name = config.get("schedule", "constant")
    progress = get_schedule_progress(transformer_options) if schedule_name != "constant" else None
    strength = scheduled_strength(
        config.get("strength", 0.5),
        schedule_name,
        config.get("schedule_amount", 0.5),
        progress,
    )
    text_scale = bounded_float(config.get("text_scale", 1.0), 1.0, TEXT_SCALE_MIN, TEXT_SCALE_MAX)

    if strength == 0.0 and text_scale == 1.0:
        return executor(*args, **kwargs)

    diagnostics: dict[str, Any] = {}
    with _PATCH_LOCK:
        if getattr(_PATCH_STATE, "active", False):
            return executor(*args, **kwargs)
        _PATCH_STATE.active = True
        try:
            if architecture == "krea2":
                result = _apply_krea2(
                    diffusion_model, executor, args, kwargs,
                    strength, config, text_scale, diagnostics,
                )
            elif architecture == "anima":
                # Anima preprocesses its text through llm_adapter before the
                # native MiniTrainDIT diffusion wrapper runs. Scale the final
                # adapted context at that boundary, not the already-executed
                # LLMAdapter cross-attention modules.
                multiplier = bounded_float((1.0 + strength) * text_scale, 1.0, 0.25, 4.0)
                result, context_scaled = run_anima_text_context_scale(
                    executor, args, kwargs, multiplier
                )
                diagnostics["text_context_multiplier"] = multiplier
                diagnostics["context_scaled"] = context_scaled
            elif architecture in ("moss_image", "qwen_image21", "z_image"):
                # Scale the model family's native text pathway before its normal
                # transformer blocks. This preserves ComfyUI's selected
                # attention backend and leaves image/reference tokens untouched.
                text_module = {
                    "moss_image": "text_embedder",
                    "qwen_image21": "txt_in",
                    "z_image": "cap_embedder",
                }[architecture]
                multiplier = bounded_float((1.0 + strength) * text_scale, 1.0, 0.25, 4.0)
                if architecture == "qwen_image21":
                    # The Qwen prefix cache keys on the original context, not
                    # our enhanced projection. Varying schedules must bypass
                    # that cache or later denoising steps can reuse stale K/V.
                    schedule_is_dynamic = (
                        schedule_name != "constant"
                        and progress is not None
                        and bounded_float(config.get("schedule_amount", 0.5), 0.5, 0.0, 1.0) > 0.0
                    )
                    result = run_qwen_text_projection_scale(
                        diffusion_model, executor, args, kwargs, multiplier,
                        disable_prefix_cache=schedule_is_dynamic,
                    )
                    diagnostics["prefix_cache_disabled_for_schedule"] = schedule_is_dynamic
                else:
                    result = run_text_module_output_scale(
                        diffusion_model, text_module, executor, args, kwargs, multiplier
                    )
                diagnostics["text_embedding_multiplier"] = multiplier
                diagnostics["text_module"] = text_module
            else:  # Defensive; detect_architecture is closed over the supported architecture names.
                result = executor(*args, **kwargs)
        finally:
            _PATCH_STATE.active = False

    if config.get("debug", False):
        count = int(config.get("_debug_prints", 0))
        if count < 8:
            config["_debug_prints"] = count + 1
            print(
                "[PromptAdherenceEnhancerPro] "
                f"model={type(diffusion_model).__name__} architecture={architecture} "
                f"strength={strength:.3f} "
                f"text_scale={text_scale:.3f} progress={progress if progress is not None else 'n/a'} "
                f"diagnostics={diagnostics}"
            )
    return result


class PromptAdherenceEnhancerPro:
    """Automatic multi-architecture enhancer with one MODEL input and output."""

    DESCRIPTION = (
        "PROMPT ADHERENCE ENHANCER PRO — automatic, architecture-aware text-path enhancement.\n\n"
        "AUTO-DETECTION: The connected MODEL is inspected automatically when this node executes. "
        "The read-only Auto-detected model display reports the recognized model family, diffusion "
        "module class, and selected adapter. Detection is structural: it checks the native diffusion "
        "module layout, not checkpoint filenames or LoRA names. Unsupported models are passed through "
        "unchanged.\n\n"
        "SUPPORTED MODEL FAMILIES AND ADAPTERS:\n"
        "• Krea 2 (Comfy-Org/Krea-2) — native 12-tap txtfusion residual enhancer, with optional txtmlp text scaling.\n"
        "• Anima (circlestone-labs/Anima) — scales the post-LLM-adapter text context before the MiniTrainDIT diffusion blocks.\n"
        "• MOSS-Image (Comfy-Org/MOSS-Image) — scales the native text_embedder output before text/image sequence assembly.\n"
        "• Qwen-Image 2.1 (Comfy-Org/Qwen-Image-2.1) — scales the native txt_in text projection; image/reference tokens are not scaled.\n"
        "• Z-Image / Z-Image-Turbo (Comfy-Org/Z-Image-Turbo) — scales the native cap_embedder caption output before context refinement.\n\n"
        "VARIANTS: Architecture-compatible base, distilled/Turbo checkpoints and LoRA fine-tunes are "
        "supported when they retain the corresponding native module structure. The node does not "
        "claim to identify a checkpoint's exact training variant or Turbo label from architecture alone.\n\n"
        "PLACEMENT: Connect after the diffusion model loader and all model/LoRA loaders, before KSampler. "
        "This node has exactly one MODEL input and one MODEL output; all remaining controls are widgets. "
        "No prompt, CLIP, image, latent, or conditioning sockets are added."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL", {"tooltip": "Connect a diffusion MODEL. The node automatically identifies Krea 2, Anima, MOSS-Image, Qwen-Image 2.1, or Z-Image from the underlying native module structure and displays the detected family after execution."}),
                "enabled": ("BOOLEAN", {"default": True}),
                "strength": ("FLOAT", {
                    "default": 0.2, "min": STRENGTH_MIN, "max": STRENGTH_MAX, "step": 0.05,
                    "tooltip": "Krea 2 uses its text-fusion enhancer. Anima scales its post-LLM-adapter text context. MOSS, Qwen 2.1 and Z-Image scale native text representations. Base/Turbo variants and compatible Turbo LoRAs use the same architecture adapter.",
                }),
                "text_scale": ("FLOAT", {
                    "default": 1.0, "min": TEXT_SCALE_MIN, "max": TEXT_SCALE_MAX, "step": 0.05,
                    "tooltip": "Additional text-influence multiplier. For Krea 2 it scales txtmlp; for the other supported models it adjusts the architecture-specific text boost. Scheduled Qwen 2.1 enhancement temporarily bypasses its prefix cache to keep per-step scaling correct.",
                }),
                "layer_profile": (["legacy", "per_layer", "uniform"], {
                    "default": "legacy",
                    "tooltip": "Krea 2 only. Legacy preserves the original gain layout; per_layer and uniform are experimental alternatives.",
                }),
                "output_limit": ("FLOAT", {
                    "default": DEFAULT_OUTPUT_LIMIT, "min": 0.0, "max": 2.0, "step": 0.05,
                    "tooltip": "Krea 2 only. Maximum text-fusion residual RMS relative to each token's original RMS. 0.75 matches the original cap.",
                }),
                "schedule": (["constant", "strong_to_weak", "weak_to_strong"], {
                    "default": "constant",
                    "tooltip": "Optional sampling schedule for the main strength. Falls back to constant if the active sampler does not expose its sigma schedule.",
                }),
                "schedule_amount": ("FLOAT", {
                    "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Ramp amount for non-constant schedules. 0 means constant strength.",
                }),
                "debug": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    FUNCTION = "apply"
    CATEGORY = "model/prompt adherence"
    OUTPUT_TOOLTIPS = (
        "Enhanced MODEL for supported architectures. Unsupported architectures pass through unchanged.",
    )

    def apply(
        self,
        model,
        enabled=True,
        strength=0.2,
        text_scale=1.0,
        layer_profile="legacy",
        output_limit=DEFAULT_OUTPUT_LIMIT,
        schedule="constant",
        schedule_amount=0.5,
        debug=False,
    ):
        import comfy.patcher_extension as patcher_extension

        # Detect immediately from the connected MODEL so the result is visible
        # in the node as soon as its normal graph execution completes. The
        # sampling wrapper repeats structural detection at runtime before it
        # applies any architecture-specific enhancement.
        detection = detect_model_info(model)

        patched = model.clone()
        options = patched.model_options.setdefault("transformer_options", {})
        options[OPTION_KEY] = {
            "enabled": bool(enabled),
            "strength": bounded_float(strength, 0.2, STRENGTH_MIN, STRENGTH_MAX),
            "text_scale": bounded_float(text_scale, 1.0, TEXT_SCALE_MIN, TEXT_SCALE_MAX),
            "layer_profile": layer_profile if layer_profile in ("legacy", "per_layer", "uniform") else "legacy",
            "output_limit": bounded_float(output_limit, DEFAULT_OUTPUT_LIMIT, 0.0, 2.0),
            "schedule": schedule if schedule in ("constant", "strong_to_weak", "weak_to_strong") else "constant",
            "schedule_amount": bounded_float(schedule_amount, 0.5, 0.0, 1.0),
            "debug": bool(debug),
        }

        if hasattr(patched, "remove_wrappers_with_key"):
            patched.remove_wrappers_with_key(patcher_extension.WrappersMP.DIFFUSION_MODEL, WRAPPER_KEY)
        wrapper_map = options.get("wrappers", {}).get(patcher_extension.WrappersMP.DIFFUSION_MODEL, {})
        wrapper_map.pop(WRAPPER_KEY, None)
        patched.add_wrapper_with_key(
            patcher_extension.WrappersMP.DIFFUSION_MODEL,
            WRAPPER_KEY,
            prompt_adherence_enhancer_pro_wrapper,
        )
        return {
            "ui": {
                "detected_model": [detection["detected_model"]],
                "detection_details": [detection["detection_details"]],
            },
            "result": (patched,),
        }


NODE_CLASS_MAPPINGS = {"PromptAdherenceEnhancerPro": PromptAdherenceEnhancerPro}
NODE_DISPLAY_NAME_MAPPINGS = {"PromptAdherenceEnhancerPro": "Prompt Adherence Enhancer Pro"}
