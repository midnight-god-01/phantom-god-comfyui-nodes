"""Krea 2 prompt-adherence enhancement math.

This is a clean, configurable implementation of the Krea2T text-fusion
amplification method. It requires the native Krea 2 text-fusion layout.
"""
from __future__ import annotations

import math
from typing import Any

import torch


KREA2_TAP_LAYERS = (2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35)
KREA2_TAP_DIM = 2560
KREA2_CHUNK_COUNT = 24
KREA2_CHUNK_DIM = 1280

# This profile is retained for compatibility with the original Krea2T enhancer.
LEGACY_PROFILE_12 = (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.5, 5.0, 1.1, 4.0, 1.0)
LEGACY_PROFILE_24 = LEGACY_PROFILE_12 + LEGACY_PROFILE_12

# Experimental interpretation: apply each Qwen-layer gain to both halves of
# that layer's 2560-wide feature vector (12 layers x 2 adjacent 1280 chunks).
PER_LAYER_PROFILE_24 = tuple(v for v in LEGACY_PROFILE_12 for _ in range(2))
UNIFORM_PROFILE_24 = (1.0,) * KREA2_CHUNK_COUNT

STRENGTH_MIN = 0.0
STRENGTH_MAX = 2.0
TEXT_SCALE_MIN = 0.25
TEXT_SCALE_MAX = 4.0
DEFAULT_OUTPUT_LIMIT = 0.75


def bounded_float(value: Any, default: float, lo: float, hi: float) -> float:
    """Convert a setting to a finite float and clamp it to its supported range."""
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        result = default
    if not math.isfinite(result):
        result = default
    return max(lo, min(hi, result))


def is_krea2_model(diffusion_model: Any) -> bool:
    """Check the complete native Krea 2 text-fusion signature this patch uses."""
    try:
        txtfusion = getattr(diffusion_model, "txtfusion", None)
        txtmlp = getattr(diffusion_model, "txtmlp", None)
        blocks = getattr(diffusion_model, "blocks", None)
        layerwise = getattr(txtfusion, "layerwise_blocks", None)
        refiners = getattr(txtfusion, "refiner_blocks", None)
        projector = getattr(txtfusion, "projector", None)

        is_sequence = lambda value: isinstance(value, (list, tuple, torch.nn.ModuleList))
        return (
            callable(getattr(diffusion_model, "_unpack_context", None))
            and callable(getattr(txtfusion, "forward", None))
            and callable(getattr(txtmlp, "forward", None))
            and callable(getattr(projector, "forward", None))
            and is_sequence(blocks)
            and len(blocks) > 0
            and is_sequence(layerwise)
            and len(layerwise) >= 2
            and all(callable(getattr(block, "forward", None)) for block in layerwise)
            and is_sequence(refiners)
            and len(refiners) >= 2
            and all(callable(getattr(block, "forward", None)) for block in refiners)
            and int(getattr(diffusion_model, "txtlayers", 0)) == len(KREA2_TAP_LAYERS)
            and int(getattr(diffusion_model, "txtdim", 0)) == KREA2_TAP_DIM
        )
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False


def get_schedule_progress(transformer_options: dict[str, Any]) -> float | None:
    """Return normalized denoising progress (0=start, 1=end), if available.

    ComfyUI exposes the current sigma and complete schedule through
    transformer_options['sigmas'] and ['sample_sigmas']. The nearest schedule
    entry is used, matching the approach used by the upstream community code.
    """
    current = transformer_options.get("sigmas")
    schedule = transformer_options.get("sample_sigmas")
    if not torch.is_tensor(schedule) or schedule.numel() < 2:
        return None

    try:
        schedule_flat = schedule.detach().float().reshape(-1)
        if torch.is_tensor(current):
            current_value = current.detach().float().reshape(-1)[0].to(schedule_flat.device)
        elif isinstance(current, (int, float)):
            current_value = torch.tensor(float(current), device=schedule_flat.device, dtype=torch.float32)
        else:
            return None
        index = int(torch.argmin(torch.abs(schedule_flat - current_value)).item())
        return float(index / max(1, schedule_flat.numel() - 1))
    except (RuntimeError, TypeError, ValueError, IndexError):
        return None


def scheduled_strength(
    base_strength: float,
    schedule: str,
    schedule_amount: float,
    progress: float | None,
) -> float:
    """Apply an optional early-heavy or late-heavy linear strength schedule."""
    strength = bounded_float(base_strength, 0.5, STRENGTH_MIN, STRENGTH_MAX)
    amount = bounded_float(schedule_amount, 0.5, 0.0, 1.0)
    if schedule == "constant" or progress is None:
        return strength

    p = max(0.0, min(1.0, float(progress)))
    if schedule == "strong_to_weak":
        multiplier = 1.0 + amount * (1.0 - 2.0 * p)
    elif schedule == "weak_to_strong":
        multiplier = 1.0 + amount * (2.0 * p - 1.0)
    else:
        multiplier = 1.0
    return bounded_float(strength * multiplier, strength, STRENGTH_MIN, STRENGTH_MAX)


def profile_gains(profile_name: str, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
    """Return the 24 chunk gains for a named profile."""
    if profile_name == "per_layer":
        values = PER_LAYER_PROFILE_24
    elif profile_name == "uniform":
        values = UNIFORM_PROFILE_24
    else:
        values = LEGACY_PROFILE_24
    return torch.tensor(values, device=device, dtype=torch.float32).to(dtype=dtype)


def run_txtfusion_parts(txtfusion: Any, x: torch.Tensor, mask=None, transformer_options=None) -> torch.Tensor:
    """Run Krea 2's TextFusionTransformer components without changing their weights."""
    options = transformer_options or {}
    batch, sequence, taps, dim = x.shape
    y = x.reshape(batch * sequence, taps, dim)
    for block in txtfusion.layerwise_blocks:
        y = block(y.contiguous(), mask=None, transformer_options=options)
    tap_mix = y.reshape(batch, sequence, taps, dim).permute(0, 1, 3, 2).contiguous()
    projected = txtfusion.projector(tap_mix).squeeze(-1)
    output = projected
    for block in txtfusion.refiner_blocks:
        output = block(output, mask=mask, transformer_options=options)
    return output


def enhanced_txtfusion_forward(
    txtfusion: Any,
    x: torch.Tensor,
    original_forward,
    *,
    strength: float,
    profile: str,
    output_limit: float,
    mask=None,
    transformer_options=None,
    collect_debug: bool = False,
) -> tuple[torch.Tensor, dict[str, float] | None]:
    """Compute the bounded difference between normal and amplified text fusion."""
    options = transformer_options or {}
    # Native Krea 2 supplies (batch, sequence, taps, channels). Keep the
    # adapter fail-safe if a compatible-looking third-party variant changes
    # rank or shape: defer to the model's own forward instead of unpacking
    # malformed dimensions here.
    if not torch.is_tensor(x) or x.ndim != 4:
        return original_forward(x, mask=mask, transformer_options=options), None
    batch, sequence, taps, dim = x.shape
    if taps != len(KREA2_TAP_LAYERS) or dim != KREA2_TAP_DIM:
        return original_forward(x, mask=mask, transformer_options=options), None

    strength = bounded_float(strength, 0.5, STRENGTH_MIN, STRENGTH_MAX)
    cap = bounded_float(output_limit, DEFAULT_OUTPUT_LIMIT, 0.0, 2.0)
    reference = original_forward(x, mask=mask, transformer_options=options)
    if strength == 0.0 or cap == 0.0:
        diagnostics = {"relative_delta": 0.0, "mean_token_scale": 0.0} if collect_debug else None
        return reference, diagnostics

    gains = profile_gains(profile, x.device, x.dtype)
    # Keep the same global multiplier as the original method.
    global_multiplier = 1.0 + strength * (15.0 - 1.0)
    scaled_x = (
        x.reshape(batch, sequence, KREA2_CHUNK_COUNT, KREA2_CHUNK_DIM)
        * (1.0 + strength * (gains.view(1, 1, KREA2_CHUNK_COUNT, 1) - 1.0))
        * global_multiplier
    ).reshape_as(x)

    candidate = run_txtfusion_parts(txtfusion, scaled_x, mask=mask, transformer_options=options)
    # Match the original method's inference-only, bounded residual calculation.
    delta = candidate.detach().float() - reference.detach().float()
    base_rms = torch.sqrt(torch.mean(reference.detach().float().square(), dim=-1, keepdim=True)).clamp_min(1e-8)
    delta_rms = torch.sqrt(torch.mean(delta.square(), dim=-1, keepdim=True)).clamp_min(1e-8)
    relative = delta_rms / base_rms
    token_scale = (cap / relative).clamp(max=1.0)
    output = (reference.detach().float() + delta * token_scale).to(candidate.dtype)

    diagnostics = None
    if collect_debug:
        reference_float = reference.detach().float()
        output_delta = output.detach().float() - reference_float
        diagnostics = {
            "relative_delta": float(
                output_delta.square().mean().sqrt().item()
                / reference_float.square().mean().sqrt().clamp_min(1e-8).item()
            ),
            "mean_token_scale": float(token_scale.mean().item()),
        }
    return output, diagnostics
