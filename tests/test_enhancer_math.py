import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import torch

from features._paa_enhancer_math import (
    KREA2_TAP_DIM,
    KREA2_TAP_LAYERS,
    LEGACY_PROFILE_24,
    PER_LAYER_PROFILE_24,
    UNIFORM_PROFILE_24,
    bounded_float,
    enhanced_txtfusion_forward,
    get_schedule_progress,
    is_krea2_model,
    profile_gains,
    scheduled_strength,
)
from features.prompt_adherence_enhancer_pro import PromptAdherenceEnhancerPro, OPTION_KEY, WRAPPER_KEY, prompt_adherence_enhancer_pro_wrapper


class AddBlock(torch.nn.Module):
    def forward(self, x, mask=None, transformer_options=None):
        return x + 0.01


class FakeTxtFusion:
    def __init__(self):
        self.layerwise_blocks = [AddBlock(), AddBlock()]
        class MeanProjector(torch.nn.Module):
            def forward(self, value):
                return value.mean(dim=-1, keepdim=True)
        self.projector = MeanProjector()
        self.refiner_blocks = [AddBlock(), AddBlock()]

    def forward(self, x, mask=None, transformer_options=None):
        b, seq, taps, dim = x.shape
        y = x.reshape(b * seq, taps, dim)
        for block in self.layerwise_blocks:
            y = block(y.contiguous(), mask=None, transformer_options=transformer_options)
        y = y.reshape(b, seq, taps, dim).permute(0, 1, 3, 2).contiguous()
        y = self.projector(y).squeeze(-1)
        for block in self.refiner_blocks:
            y = block(y, mask=mask, transformer_options=transformer_options)
        return y


class FakeDiffusionModel:
    def __init__(self):
        self.txtfusion = FakeTxtFusion()
        self.txtmlp = torch.nn.Linear(KREA2_TAP_DIM, 4, bias=False)
        self.blocks = [object()]
        self.txtlayers = len(KREA2_TAP_LAYERS)
        self.txtdim = KREA2_TAP_DIM

    def _unpack_context(self, context):
        return context


class FakeExecutor:
    def __init__(self, class_obj):
        self.class_obj = class_obj

    def __call__(self, *args, **kwargs):
        sample = torch.ones(1, 2, 12, KREA2_TAP_DIM)
        fused = self.class_obj.txtfusion.forward(sample, transformer_options=kwargs.get("transformer_options", {}))
        mlp_input = torch.ones(1, 1, KREA2_TAP_DIM)
        projected = self.class_obj.txtmlp(mlp_input)
        return fused, projected


class EnhancerMathTests(unittest.TestCase):
    def test_bounded_float_handles_bad_values(self):
        self.assertEqual(bounded_float(float("nan"), 0.5, 0.0, 2.0), 0.5)
        self.assertEqual(bounded_float("bad", 0.5, 0.0, 2.0), 0.5)
        self.assertEqual(bounded_float(9.0, 0.5, 0.0, 2.0), 2.0)
        self.assertEqual(bounded_float(-1.0, 0.5, 0.0, 2.0), 0.0)

    def test_profiles_are_the_expected_shapes(self):
        self.assertEqual(len(LEGACY_PROFILE_24), 24)
        self.assertEqual(len(PER_LAYER_PROFILE_24), 24)
        self.assertEqual(len(UNIFORM_PROFILE_24), 24)
        self.assertEqual(PER_LAYER_PROFILE_24[14:20], (2.5, 2.5, 5.0, 5.0, 1.1, 1.1))
        self.assertEqual(LEGACY_PROFILE_24[12:24], LEGACY_PROFILE_24[:12])
        self.assertEqual(UNIFORM_PROFILE_24, (1.0,) * 24)

    def test_schedule_progress_and_strength(self):
        opts = {"sigmas": torch.tensor([0.75]), "sample_sigmas": torch.tensor([1.0, 0.75, 0.5, 0.0])}
        self.assertAlmostEqual(get_schedule_progress(opts), 1.0 / 3.0, places=6)
        self.assertAlmostEqual(scheduled_strength(1.0, "strong_to_weak", 0.5, 0.0), 1.5)
        self.assertAlmostEqual(scheduled_strength(1.0, "strong_to_weak", 0.5, 1.0), 0.5)
        self.assertAlmostEqual(scheduled_strength(1.0, "weak_to_strong", 0.5, 0.0), 0.5)
        self.assertEqual(scheduled_strength(1.0, "strong_to_weak", 0.5, None), 1.0)

    def test_model_signature(self):
        self.assertTrue(is_krea2_model(FakeDiffusionModel()))
        self.assertFalse(is_krea2_model(object()))

    def test_krea2_turbo_lora_does_not_change_architecture_signature(self):
        model = FakeDiffusionModel()
        model.checkpoint_variant = "turbo"
        model.turbo_lora_applied = True
        self.assertTrue(is_krea2_model(model))

    def test_strength_zero_returns_original_forward(self):
        fusion = FakeTxtFusion()
        x = torch.randn(1, 2, 12, 2560)
        original = fusion.forward
        expected = original(x)
        actual, _ = enhanced_txtfusion_forward(
            fusion, x, original, strength=0.0, profile="legacy", output_limit=0.75
        )
        torch.testing.assert_close(actual, expected)

    def test_output_delta_is_capped_per_token(self):
        fusion = FakeTxtFusion()
        x = torch.randn(1, 2, 12, 2560)
        original = fusion.forward
        reference = original(x)
        actual, _ = enhanced_txtfusion_forward(
            fusion, x, original, strength=0.5, profile="legacy", output_limit=0.3
        )
        delta_rms = (actual.float() - reference.float()).square().mean(dim=-1, keepdim=True).sqrt()
        base_rms = reference.float().square().mean(dim=-1, keepdim=True).sqrt().clamp_min(1e-8)
        self.assertTrue(torch.all(delta_rms <= base_rms * 0.30001))

    def test_wrong_tensor_layout_falls_back(self):
        fusion = FakeTxtFusion()
        x = torch.randn(1, 2, 8, 2560)
        original = lambda value, **kwargs: value
        expected = original(x)
        actual, diagnostics = enhanced_txtfusion_forward(
            fusion, x, original, strength=1.0, profile="legacy", output_limit=0.75
        )
        torch.testing.assert_close(actual, expected)
        self.assertIsNone(diagnostics)

    def test_malformed_rank_falls_back_to_native_forward(self):
        fusion = FakeTxtFusion()
        x = torch.randn(1, 2, 2560)
        original = lambda value, **kwargs: value
        expected = original(x)
        actual, diagnostics = enhanced_txtfusion_forward(
            fusion, x, original, strength=1.0, profile="legacy", output_limit=0.75
        )
        torch.testing.assert_close(actual, expected)
        self.assertIsNone(diagnostics)

    def test_debug_diagnostics_are_opt_in(self):
        fusion = FakeTxtFusion()
        x = torch.randn(1, 1, 12, 2560)
        original = fusion.forward
        _, quiet = enhanced_txtfusion_forward(
            fusion, x, original, strength=0.5, profile="legacy", output_limit=0.75
        )
        _, verbose = enhanced_txtfusion_forward(
            fusion, x, original, strength=0.5, profile="legacy", output_limit=0.75, collect_debug=True
        )
        self.assertIsNone(quiet)
        self.assertIn("relative_delta", verbose)
        self.assertIn("mean_token_scale", verbose)

    def test_model_only_node_registration(self):
        input_types = PromptAdherenceEnhancerPro.INPUT_TYPES()["required"]
        self.assertEqual(list(input_types.keys())[0], "model")
        self.assertEqual(PromptAdherenceEnhancerPro.RETURN_TYPES, ("MODEL",))
        self.assertEqual(PromptAdherenceEnhancerPro.RETURN_NAMES, ("model",))
        self.assertEqual(len(PromptAdherenceEnhancerPro.RETURN_TYPES), 1)

    def test_wrapper_restores_methods_after_run(self):
        model = FakeDiffusionModel()
        original_fusion = model.txtfusion.forward
        original_mlp = model.txtmlp.forward
        opts = {OPTION_KEY: {"enabled": True, "strength": 0.5, "text_scale": 1.2,
                             "layer_profile": "legacy", "output_limit": 0.75,
                             "schedule": "constant", "schedule_amount": 0.5}}
        executor = FakeExecutor(model)
        result, projected = prompt_adherence_enhancer_pro_wrapper(executor, transformer_options=opts)
        self.assertEqual(result.shape, (1, 2, 2560))
        self.assertEqual(projected.shape, (1, 1, 4))
        baseline_projected = original_mlp(torch.ones(1, 1, KREA2_TAP_DIM))
        torch.testing.assert_close(projected, baseline_projected * 1.2)
        self.assertEqual(model.txtfusion.forward, original_fusion)
        self.assertEqual(model.txtmlp.forward, original_mlp)
        self.assertNotIn("forward", model.txtfusion.__dict__)
        self.assertNotIn("forward", model.txtmlp.__dict__)
        self.assertNotIn("_active", opts[OPTION_KEY])

    def test_constant_schedule_does_not_read_sampler_progress(self):
        model = FakeDiffusionModel()
        opts = {OPTION_KEY: {"enabled": True, "strength": 0.5, "text_scale": 1.0,
                             "layer_profile": "legacy", "output_limit": 0.75,
                             "schedule": "constant"},
                "sigmas": torch.tensor([0.75]),
                "sample_sigmas": torch.tensor([1.0, 0.75, 0.5, 0.0])}
        executor = FakeExecutor(model)
        with patch("features.prompt_adherence_enhancer_pro.get_schedule_progress") as progress_reader:
            prompt_adherence_enhancer_pro_wrapper(executor, transformer_options=opts)
        progress_reader.assert_not_called()

    def test_non_krea2_model_is_passed_through(self):
        class PassThroughExecutor:
            class_obj = object()
            def __call__(self, *args, **kwargs):
                return "unchanged"
        opts = {OPTION_KEY: {"enabled": True, "strength": 0.5}}
        self.assertEqual(prompt_adherence_enhancer_pro_wrapper(PassThroughExecutor(), transformer_options=opts),
                         "unchanged")

    def test_wrapper_restores_methods_on_exception(self):
        model = FakeDiffusionModel()
        original_fusion = model.txtfusion.forward
        original_mlp = model.txtmlp.forward
        opts = {OPTION_KEY: {"enabled": True, "strength": 0.5, "text_scale": 1.2}}
        def broken_executor(*args, **kwargs):
            model.txtfusion.forward(torch.ones(1, 1, 12, KREA2_TAP_DIM))
            raise RuntimeError("deliberate test exception")
        broken_executor.class_obj = model
        with self.assertRaisesRegex(RuntimeError, "deliberate test exception"):
            prompt_adherence_enhancer_pro_wrapper(broken_executor, transformer_options=opts)
        self.assertEqual(model.txtfusion.forward, original_fusion)
        self.assertEqual(model.txtmlp.forward, original_mlp)
        self.assertNotIn("forward", model.txtfusion.__dict__)
        self.assertNotIn("forward", model.txtmlp.__dict__)
        self.assertNotIn("_active", opts[OPTION_KEY])


if __name__ == "__main__":
    unittest.main()
