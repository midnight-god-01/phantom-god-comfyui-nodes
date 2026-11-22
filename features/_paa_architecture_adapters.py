"""Architecture-specific, MODEL-only text-adherence adapters.

Supported native ComfyUI diffusion-model families:
- Krea 2: original 12-tap txtfusion residual enhancer (in enhancer_math.py).
- Anima: scale the post-LLM-adapter text context before the diffusion blocks.
- MOSS-Image: scale the output of its native text embedder.
- Qwen-Image 2.1: scale its native text projection before sequence construction.
- Z-Image-Turbo: scale its native caption embedding projection before context refinement.

The non-Krea adapters wrap only the relevant text-conditioned module for the
active model forward, then restore its original method in a finally block. Anima
uses a call-local context replacement because its LLM adapter runs before the
diffusion-model wrapper. They do not replace attention kernels or create extra
attention matrices.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

import torch

from ._paa_enhancer_math import is_krea2_model


SUPPORTED_ARCHITECTURES = ("krea2", "anima", "moss_image", "qwen_image21", "z_image")

# These are architecture families, not checkpoint-name allowlists. Standard,
# distilled/Turbo checkpoints and LoRA variants are compatible whenever they
# retain the corresponding native ComfyUI module layout. A LoRA normally
# changes parameters, not these modules, so there is deliberately no separate
# "Turbo LoRA" detector or switch.
SUPPORTED_VARIANT_TYPES = (
    "base checkpoint",
    "distilled/Turbo checkpoint",
    "Turbo or acceleration LoRA",
    "other LoRA fine-tune",
)


def _has_blocks_with(module: Any, attribute: str) -> bool:
    blocks = getattr(module, "blocks", None)
    if not isinstance(blocks, (list, tuple, torch.nn.ModuleList)) or len(blocks) == 0:
        return False
    return all(hasattr(block, attribute) for block in blocks)


def detect_architecture(diffusion_model: Any) -> str | None:
    """Return an architecture family using structure rather than checkpoint names.

    Turbo LoRAs are not identifiable from the diffusion model's class or module
    layout, and do not need to be: their patched weights are used by the same
    native modules wrapped by this node. Keeping detection independent of
    weights, LoRA filenames and variant labels makes the adapters work with
    standard ModelPatcher LoRA clones as well as base checkpoints.
    """
    if is_krea2_model(diffusion_model):
        return "krea2"

    # Current ComfyUI Anima owns its cross-attention blocks inside
    # llm_adapter.blocks, not on the diffusion-model root. The adapter runs
    # before MiniTrainDIT's wrapped forward, so the runtime intervention scales
    # the resulting context tensor rather than patching these already-finished
    # attention modules.
    llm_adapter = getattr(diffusion_model, "llm_adapter", None)
    if (
        llm_adapter is not None
        and callable(getattr(diffusion_model, "preprocess_text_embeds", None))
        and _has_blocks_with(llm_adapter, "cross_attn")
    ):
        return "anima"

    # Native ComfyUI MOSS-Image has a text embedder and its own image stream.
    if (
        callable(getattr(getattr(diffusion_model, "text_embedder", None), "forward", None))
        and callable(getattr(getattr(diffusion_model, "video_embedder", None), "forward", None))
        and callable(getattr(getattr(diffusion_model, "shared_block_modulation", None), "forward", None))
        and isinstance(getattr(diffusion_model, "layers", None), torch.nn.ModuleList)
        and len(diffusion_model.layers) > 0
    ):
        return "moss_image"

    # Restrict this adapter to the Qwen-Image 2.1 layout. Older Qwen Image
    # models have different projection and sequence-building semantics.
    if (
        callable(getattr(getattr(diffusion_model, "txt_in", None), "forward", None))
        and callable(getattr(diffusion_model, "build_sequence", None))
        and callable(getattr(getattr(diffusion_model, "img_in", None), "forward", None))
        and callable(getattr(getattr(diffusion_model, "modulation", None), "forward", None))
        and callable(getattr(getattr(diffusion_model, "proj_out", None), "forward", None))
        and hasattr(diffusion_model, "prefix_cache")
        and hasattr(diffusion_model, "prefix_cache_enabled")
        and isinstance(getattr(diffusion_model, "transformer_blocks", None), torch.nn.ModuleList)
        and len(diffusion_model.transformer_blocks) > 0
    ):
        return "qwen_image21"

    # Z-Image (including Turbo and compatible distilled/LoRA variants) is
    # implemented by ComfyUI's NextDiT. Identify the family from the core
    # 3840-wide, 30-head, Z-Image timestep-scaled layout and its caption
    # refinement path. Do not require learned pad-token parameters: those are
    # configuration details, not the architecture itself. This intentionally
    # excludes ordinary Lumina 2 (2304-wide), Ming-Image (has __ming_image__),
    # and pixel-space Z-Image (has dec_net).
    if (
        getattr(diffusion_model, "dim", None) == 3840
        and getattr(diffusion_model, "time_scale", None) == 1000.0
        and getattr(diffusion_model, "n_heads", None) == 30
        and callable(getattr(getattr(diffusion_model, "cap_embedder", None), "forward", None))
        and isinstance(getattr(diffusion_model, "context_refiner", None), torch.nn.ModuleList)
        and len(diffusion_model.context_refiner) > 0
        and isinstance(getattr(diffusion_model, "noise_refiner", None), torch.nn.ModuleList)
        and len(diffusion_model.noise_refiner) > 0
        and isinstance(getattr(diffusion_model, "layers", None), torch.nn.ModuleList)
        and len(diffusion_model.layers) > 0
        and not hasattr(diffusion_model, "__ming_image__")
        and not hasattr(diffusion_model, "dec_net")
    ):
        return "z_image"

    return None


@contextmanager
def temporary_module_forward(module: Any, replacement: Callable) -> Iterator[None]:
    """Temporarily replace forward without leaving an instance override behind.

    Most nn.Module.forward methods are class attributes. Assigning the resolved
    bound method back after a temporary patch leaves that bound method stored
    in the module instance dictionary. Restore the exact prior instance state:
    delete the temporary attribute if it did not previously exist, or restore
    the original instance override when it did.
    """
    instance_dict = getattr(module, "__dict__", {})
    had_instance_forward = "forward" in instance_dict
    previous_instance_forward = instance_dict.get("forward")
    module.forward = replacement
    try:
        yield
    finally:
        if had_instance_forward:
            module.forward = previous_instance_forward
        else:
            try:
                delattr(module, "forward")
            except AttributeError:
                pass


def _scale_module_output(module: Any, executor: Callable, args: tuple, kwargs: dict, multiplier: float):
    """Scale one module's tensor output for a single model forward, restoring it afterwards."""
    original_forward = module.forward

    def scaled_forward(*call_args, **call_kwargs):
        result = original_forward(*call_args, **call_kwargs)
        if isinstance(result, torch.Tensor):
            return result * multiplier
        return result

    with temporary_module_forward(module, scaled_forward):
        return executor(*args, **kwargs)


def run_anima_text_context_scale(
    executor: Callable,
    args: tuple,
    kwargs: dict,
    multiplier: float,
) -> tuple[Any, bool]:
    """Scale Anima's already-adapted text context for this diffusion forward.

    In native ComfyUI Anima, Anima.forward runs llm_adapter first and only then
    calls MiniTrainDIT.forward. The DIFFUSION_MODEL wrapper therefore sees the
    final context as the third positional argument (or a context keyword),
    before the diffusion transformer consumes it.
    """
    call_kwargs = dict(kwargs)
    if len(args) >= 3 and isinstance(args[2], torch.Tensor):
        call_args = list(args)
        call_args[2] = call_args[2] * multiplier
        return executor(*call_args, **call_kwargs), True

    if isinstance(call_kwargs.get("context"), torch.Tensor):
        call_kwargs["context"] = call_kwargs["context"] * multiplier
        return executor(*args, **call_kwargs), True

    return executor(*args, **kwargs), False


def run_qwen_text_projection_scale(
    diffusion_model: Any,
    executor: Callable,
    args: tuple,
    kwargs: dict,
    multiplier: float,
    *,
    disable_prefix_cache: bool = False,
):
    """Scale Qwen-Image 2.1 text projection and keep dynamic schedules cache-safe.

    Qwen's prefix-cache key is based on the original context tensor, while the
    cached K/V values are produced from projected text tokens. When a
    non-constant enhancer schedule changes the projection multiplier, that key
    would otherwise match old K/V values. Disable caching for the active call
    and clear any old internal cache before using a varying multiplier.
    """
    module = getattr(diffusion_model, "txt_in", None)
    if module is None or not hasattr(module, "forward"):
        return executor(*args, **kwargs)

    old_cache_enabled = getattr(diffusion_model, "prefix_cache_enabled", None)
    if disable_prefix_cache and isinstance(old_cache_enabled, bool):
        try:
            if getattr(diffusion_model, "prefix_cache", None) is not None:
                reset_cache = getattr(diffusion_model, "reset_prefix_cache", None)
                if callable(reset_cache):
                    reset_cache(False)
                else:
                    diffusion_model.prefix_cache = None
            diffusion_model.prefix_cache_enabled = False
            return _scale_module_output(module, executor, args, kwargs, multiplier)
        finally:
            diffusion_model.prefix_cache_enabled = old_cache_enabled

    return _scale_module_output(module, executor, args, kwargs, multiplier)


def run_text_module_output_scale(
    diffusion_model: Any,
    module_name: str,
    executor: Callable,
    args: tuple,
    kwargs: dict,
    multiplier: float,
):
    """Scale a model-family's own text module without replacing its attention backend."""
    module = getattr(diffusion_model, module_name, None)
    if module is None or not hasattr(module, "forward"):
        return executor(*args, **kwargs)
    return _scale_module_output(module, executor, args, kwargs, multiplier)
