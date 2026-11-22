import threading
import unittest
import torch

from features._paa_architecture_adapters import (
    detect_architecture,
    run_anima_text_context_scale,
    run_qwen_text_projection_scale,
    run_text_module_output_scale,
)
from features._paa_model_detection_info import detect_model_info
from features.prompt_adherence_enhancer_pro import (
    PromptAdherenceEnhancerPro,
    OPTION_KEY,
    _PATCH_STATE,
    prompt_adherence_enhancer_pro_wrapper,
)


class FakeKreaTextFusion(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.layerwise_blocks = torch.nn.ModuleList([torch.nn.Identity(), torch.nn.Identity()])
        self.projector = torch.nn.Linear(12, 1, bias=False)
        self.refiner_blocks = torch.nn.ModuleList([torch.nn.Identity(), torch.nn.Identity()])

    def forward(self, x, mask=None, transformer_options=None):
        return x


class FakeKrea(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.txtfusion = FakeKreaTextFusion()
        self.txtmlp = torch.nn.Identity()
        self.blocks = torch.nn.ModuleList([torch.nn.Identity()])
        self.txtlayers = 12
        self.txtdim = 2560

    def _unpack_context(self, context):
        return context


class FakeAnima(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.llm_adapter = torch.nn.Module()
        self.llm_adapter.blocks = torch.nn.ModuleList([torch.nn.Module(), torch.nn.Module()])
        self.preprocess_text_embeds = lambda *args, **kwargs: args[0]
        for block in self.llm_adapter.blocks:
            block.cross_attn = torch.nn.Module()
            block.cross_attn.forward = lambda x: x + 1.0


class FakeMoss(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.text_embedder = torch.nn.Identity()
        self.video_embedder = torch.nn.Identity()
        self.layers = torch.nn.ModuleList([torch.nn.Identity()])
        self.shared_block_modulation = torch.nn.Identity()


class FakeQwen21(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.txt_in = torch.nn.Identity()
        self.img_in = torch.nn.Identity()
        self.modulation = torch.nn.Identity()
        self.proj_out = torch.nn.Identity()
        self.transformer_blocks = torch.nn.ModuleList([torch.nn.Identity()])
        self.prefix_cache = None
        self.prefix_cache_enabled = True

    def reset_prefix_cache(self, enabled):
        self.prefix_cache = None
        self.prefix_cache_enabled = enabled

    def build_sequence(self):
        pass


class FakeZImage(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.dim = 3840
        self.time_scale = 1000.0
        self.pad_tokens_multiple = 32
        self.n_heads = 30
        self.cap_embedder = torch.nn.Identity()
        self.context_refiner = torch.nn.ModuleList([torch.nn.Identity()])
        self.noise_refiner = torch.nn.ModuleList([torch.nn.Identity()])
        self.layers = torch.nn.ModuleList([torch.nn.Identity()])
        self.register_parameter("cap_pad_token", torch.nn.Parameter(torch.zeros(1, 3840)))
        self.register_parameter("x_pad_token", torch.nn.Parameter(torch.zeros(1, 3840)))


class ArchitectureAdapterTests(unittest.TestCase):
    def test_model_info_reports_correct_family_and_native_adapter(self):
        cases = (
            (FakeKrea(), "Krea 2", "txtfusion"),
            (FakeAnima(), "Anima", "post-LLM-adapter"),
            (FakeMoss(), "MOSS-Image", "text_embedder"),
            (FakeQwen21(), "Qwen-Image 2.1", "txt_in"),
            (FakeZImage(), "Z-Image", "cap_embedder"),
        )
        for diffusion_model, expected_name, expected_adapter in cases:
            with self.subTest(model=expected_name):
                report = detect_model_info(diffusion_model)
                self.assertEqual(report["detected_model"], expected_name)
                self.assertTrue(report["supported"])
                self.assertIn(expected_adapter, report["detection_details"])
                self.assertEqual(report["model_class"], type(diffusion_model).__name__)

    def test_model_info_prefers_model_patcher_get_model_object(self):
        diffusion_model = FakeMoss()
        patcher = type("FakePatcher", (), {})()
        patcher.get_model_object = lambda name: diffusion_model if name == "diffusion_model" else None
        report = detect_model_info(patcher)
        self.assertEqual(report["detected_model"], "MOSS-Image")
        self.assertIn("text_embedder", report["detection_details"])

    def test_model_info_uses_model_patcher_diffusion_model_path(self):
        diffusion_model = FakeQwen21()
        patcher = type("FakePatcher", (), {})()
        patcher.model = type("FakeBaseModel", (), {"diffusion_model": diffusion_model})()
        report = detect_model_info(patcher)
        self.assertEqual(report["detected_model"], "Qwen-Image 2.1")
        self.assertIn("txt_in", report["detection_details"])

    def test_unknown_model_info_is_explicit_pass_through(self):
        report = detect_model_info(torch.nn.Linear(2, 2))
        self.assertFalse(report["supported"])
        self.assertIsNone(report["architecture"])
        self.assertEqual(report["detected_model"], "Unsupported model — pass-through")
        self.assertIn("passed through unchanged", report["detection_details"])

    def test_architecture_detection(self):
        self.assertEqual(detect_architecture(FakeKrea()), "krea2")
        self.assertEqual(detect_architecture(FakeAnima()), "anima")
        self.assertEqual(detect_architecture(FakeMoss()), "moss_image")
        self.assertEqual(detect_architecture(FakeQwen21()), "qwen_image21")
        self.assertEqual(detect_architecture(FakeZImage()), "z_image")
        self.assertIsNone(detect_architecture(torch.nn.Linear(2, 2)))

    def test_krea_detection_rejects_incomplete_text_fusion_layout(self):
        incomplete = FakeKrea()
        incomplete.txtfusion = torch.nn.Identity()
        self.assertIsNone(detect_architecture(incomplete))

    def test_architecture_detection_is_variant_and_lora_name_independent(self):
        cases = (
            (FakeKrea(), "krea2"), (FakeAnima(), "anima"),
            (FakeMoss(), "moss_image"), (FakeQwen21(), "qwen_image21"),
            (FakeZImage(), "z_image"),
        )
        for model, expected in cases:
            model.checkpoint_variant = "turbo"
            model.turbo_lora_applied = True
            self.assertEqual(detect_architecture(model), expected)

    def test_turbo_lora_weight_patch_uses_same_text_adapter(self):
        model = FakeMoss()
        model.text_embedder = torch.nn.Linear(4, 4, bias=False)
        with torch.no_grad():
            model.text_embedder.weight.copy_(torch.eye(4))
            model.text_embedder.weight.add_(0.25)
        values = torch.ones(1, 2, 4)
        expected = model.text_embedder(values) * 1.2

        class Executor:
            class_obj = model
            def __call__(self, *args, **kwargs):
                return model.text_embedder(values)

        result = prompt_adherence_enhancer_pro_wrapper(
            Executor(), transformer_options={OPTION_KEY: {"enabled": True, "strength": 0.2, "text_scale": 1.0}}
        )
        torch.testing.assert_close(result, expected)

    def test_model_detection_rejects_missing_text_path_modules(self):
        moss = FakeMoss(); del moss.text_embedder
        qwen = FakeQwen21(); del qwen.txt_in
        z_image = FakeZImage(); del z_image.cap_embedder
        self.assertIsNone(detect_architecture(moss))
        self.assertIsNone(detect_architecture(qwen))
        self.assertIsNone(detect_architecture(z_image))

    def test_z_image_detection_rejects_lumina_ming_and_pixel_variants(self):
        lumina = FakeZImage(); lumina.dim = 2304
        self.assertIsNone(detect_architecture(lumina))
        ming = FakeZImage(); ming.pad_tokens_multiple = None
        ming.register_buffer("__ming_image__", torch.empty(0))
        self.assertIsNone(detect_architecture(ming))
        pixel = FakeZImage(); pixel.dec_net = torch.nn.Identity()
        self.assertIsNone(detect_architecture(pixel))

    def test_z_image_base_variant_without_learned_pad_tokens_is_supported(self):
        base = FakeZImage()
        base.pad_tokens_multiple = None
        delattr(base, "cap_pad_token")
        delattr(base, "x_pad_token")
        self.assertEqual(detect_architecture(base), "z_image")

    def test_moss_text_embedder_output_is_scaled_and_restored(self):
        model = FakeMoss()
        original = model.text_embedder.forward
        def executor(*args, **kwargs):
            return model.text_embedder.forward(torch.ones(1, 3, 4))
        result = run_text_module_output_scale(model, "text_embedder", executor, (), {}, 1.5)
        torch.testing.assert_close(result, torch.full((1, 3, 4), 1.5))
        self.assertEqual(model.text_embedder.forward, original)
        self.assertNotIn("forward", model.text_embedder.__dict__)

    def test_qwen21_text_projection_scales_with_reference_edit_inputs_too(self):
        model = FakeQwen21()
        original = model.txt_in.forward
        def executor(*args, **kwargs):
            return model.txt_in.forward(torch.ones(1, 4, 16))
        result = run_text_module_output_scale(model, "txt_in", executor, (), {}, 1.25)
        torch.testing.assert_close(result, torch.full((1, 4, 16), 1.25))
        self.assertEqual(model.txt_in.forward, original)

    def test_text_module_method_is_restored_after_exception(self):
        model = FakeMoss()
        original = model.text_embedder.forward
        def broken(*args, **kwargs):
            model.text_embedder.forward(torch.ones(1, 2, 3))
            raise RuntimeError("expected text-module failure")
        with self.assertRaisesRegex(RuntimeError, "expected text-module failure"):
            run_text_module_output_scale(model, "text_embedder", broken, (), {}, 1.4)
        self.assertEqual(model.text_embedder.forward, original)
        self.assertNotIn("forward", model.text_embedder.__dict__)

    def test_anima_detection_uses_llm_adapter_blocks_not_root_blocks(self):
        model = FakeAnima()
        self.assertFalse(hasattr(model, "blocks"))
        self.assertEqual(detect_architecture(model), "anima")

    def test_anima_context_is_scaled_at_diffusion_boundary(self):
        context = torch.ones(1, 4, 8)
        image_latents = torch.ones(1, 4, 2, 2)
        def executor(x, timestep, actual_context):
            return x, actual_context
        result, applied = run_anima_text_context_scale(
            executor, (image_latents, torch.zeros(1), context), {}, 1.25
        )
        self.assertTrue(applied)
        torch.testing.assert_close(result[0], image_latents)
        torch.testing.assert_close(result[1], torch.full_like(context, 1.25))
        torch.testing.assert_close(context, torch.ones_like(context))

    def test_anima_context_keyword_is_scaled_and_fallback_is_safe(self):
        context = torch.ones(1, 2, 8)
        result, applied = run_anima_text_context_scale(
            lambda **kwargs: kwargs["context"], (), {"context": context}, 1.5
        )
        self.assertTrue(applied)
        torch.testing.assert_close(result, torch.full_like(context, 1.5))
        result, applied = run_anima_text_context_scale(lambda x: x, (7,), {}, 2.0)
        self.assertFalse(applied)
        self.assertEqual(result, 7)

    def test_node_remains_model_only(self):
        required = PromptAdherenceEnhancerPro.INPUT_TYPES()["required"]
        self.assertEqual(list(required.keys())[0], "model")
        self.assertEqual([name for name, spec in required.items() if spec[0] == "MODEL"], ["model"])
        self.assertEqual(PromptAdherenceEnhancerPro.RETURN_TYPES, ("MODEL",))
        self.assertEqual(PromptAdherenceEnhancerPro.RETURN_NAMES, ("model",))

    def test_anima_model_wrapper_scales_adapted_context(self):
        model = FakeAnima()
        context = torch.ones(1, 3, 8)
        class Executor:
            class_obj = model
            def __call__(self, x, timestep, actual_context, **kwargs):
                return actual_context
        options = {OPTION_KEY: {"enabled": True, "strength": 0.2, "text_scale": 1.0}}
        result = prompt_adherence_enhancer_pro_wrapper(
            Executor(), torch.zeros(1, 4, 2, 2), torch.zeros(1), context, transformer_options=options
        )
        torch.testing.assert_close(result, torch.full_like(context, 1.2))
        torch.testing.assert_close(context, torch.ones_like(context))

    def test_moss_model_wrapper_scales_text_embedder_and_restores(self):
        model = FakeMoss()
        original = model.text_embedder.forward
        options = {OPTION_KEY: {"enabled": True, "strength": 0.5, "text_scale": 1.0}}
        class Executor:
            class_obj = model
            def __call__(self, *args, **kwargs):
                return model.text_embedder.forward(torch.ones(1, 2, 4))
        result = prompt_adherence_enhancer_pro_wrapper(Executor(), transformer_options=options)
        torch.testing.assert_close(result, torch.full((1, 2, 4), 1.5))
        self.assertEqual(model.text_embedder.forward, original)

    def test_moss_native_positional_transformer_options_signature(self):
        model = FakeMoss()
        seen = {}
        class NativeMossTextEmbedder(torch.nn.Module):
            def forward(self, x, pe, transformer_options, mask=None):
                seen["pe"] = pe
                seen["transformer_options"] = transformer_options
                seen["mask"] = mask
                return x
        model.text_embedder = NativeMossTextEmbedder()
        options = {OPTION_KEY: {"enabled": True, "strength": 0.4, "text_scale": 1.0}}
        values = torch.ones(1, 3, 4)
        rope = torch.zeros(1, 3, 2)
        text_mask = torch.ones(1, 3, dtype=torch.bool)
        class NativeMossExecutor:
            class_obj = model
            def __call__(self, x, timestep, context, transformer_options):
                return model.text_embedder(context, rope, transformer_options, text_mask)
        original_forward = model.text_embedder.forward
        result = prompt_adherence_enhancer_pro_wrapper(
            NativeMossExecutor(), torch.zeros(1, 4, 2, 2), torch.zeros(1), values, options
        )
        torch.testing.assert_close(result, torch.full_like(values, 1.4))
        self.assertIs(seen["transformer_options"], options)
        self.assertIs(seen["pe"], rope)
        self.assertIs(seen["mask"], text_mask)
        self.assertEqual(model.text_embedder.forward, original_forward)
        self.assertNotIn("forward", model.text_embedder.__dict__)

    def test_qwen21_model_wrapper_scales_text_projection_for_reference_edit(self):
        model = FakeQwen21()
        options = {OPTION_KEY: {"enabled": True, "strength": 0.5, "text_scale": 1.0}}
        refs = [torch.zeros(1, 16, 2, 2)]
        class Executor:
            class_obj = model
            def __call__(self, *args, **kwargs):
                return model.txt_in.forward(torch.ones(1, 4, 16))
        result = prompt_adherence_enhancer_pro_wrapper(
            Executor(), torch.zeros(1, 16, 2, 3), torch.zeros(1), torch.zeros(1, 4, 4096),
            refs, [], options,
        )
        torch.testing.assert_close(result, torch.full((1, 4, 16), 1.5))
        self.assertNotIn("optimized_attention_override", options)

    def test_qwen_dynamic_schedule_disables_prefix_cache_and_restores_state(self):
        model = FakeQwen21()
        model.prefix_cache = object()
        context = torch.ones(1, 2, 4)
        observed = {}
        def executor(*args, **kwargs):
            observed["cache_enabled_inside"] = model.prefix_cache_enabled
            return model.txt_in(context)
        result = run_qwen_text_projection_scale(model, executor, (), {}, 1.3, disable_prefix_cache=True)
        torch.testing.assert_close(result, torch.full_like(context, 1.3))
        self.assertFalse(observed["cache_enabled_inside"])
        self.assertTrue(model.prefix_cache_enabled)
        self.assertIsNone(model.prefix_cache)

    def test_qwen_dynamic_cache_and_text_hook_restore_after_error(self):
        model = FakeQwen21()
        original_forward = model.txt_in.forward
        model.prefix_cache = object()
        def broken(*args, **kwargs):
            model.txt_in(torch.ones(1, 2, 4))
            self.assertFalse(model.prefix_cache_enabled)
            raise RuntimeError("qwen failure")
        with self.assertRaisesRegex(RuntimeError, "qwen failure"):
            run_qwen_text_projection_scale(model, broken, (), {}, 1.2, disable_prefix_cache=True)
        self.assertEqual(model.txt_in.forward, original_forward)
        self.assertNotIn("forward", model.txt_in.__dict__)
        self.assertTrue(model.prefix_cache_enabled)
        self.assertIsNone(model.prefix_cache)

    def test_qwen_model_wrapper_bypasses_cache_when_schedule_is_dynamic(self):
        model = FakeQwen21()
        model.prefix_cache = object()
        context = torch.ones(1, 2, 4)
        observed = {}
        class Executor:
            class_obj = model
            def __call__(self, x, timestep, ctx, *rest):
                observed["cache_enabled_inside"] = model.prefix_cache_enabled
                return model.txt_in(ctx)
        options = {
            OPTION_KEY: {"enabled": True, "strength": 0.2, "text_scale": 1.0,
                         "schedule": "strong_to_weak", "schedule_amount": 0.5},
            "sigmas": torch.tensor([1.0]),
            "sample_sigmas": torch.tensor([1.0, 0.5, 0.0]),
        }
        result = prompt_adherence_enhancer_pro_wrapper(
            Executor(), torch.zeros(1, 4, 2, 2), torch.zeros(1), context, options
        )
        self.assertFalse(observed["cache_enabled_inside"])
        torch.testing.assert_close(result, torch.full_like(context, 1.3))
        self.assertTrue(model.prefix_cache_enabled)
        self.assertIsNone(model.prefix_cache)

    def test_z_image_cap_embedder_output_is_scaled_and_restored(self):
        model = FakeZImage()
        original = model.cap_embedder.forward
        def executor(*args, **kwargs):
            return model.cap_embedder(torch.ones(1, 5, 3840))
        result = run_text_module_output_scale(model, "cap_embedder", executor, (), {}, 1.4)
        torch.testing.assert_close(result, torch.full((1, 5, 3840), 1.4))
        self.assertEqual(model.cap_embedder.forward, original)

    def test_z_image_cap_embedder_method_restored_after_exception(self):
        model = FakeZImage()
        original = model.cap_embedder.forward
        def broken(*args, **kwargs):
            model.cap_embedder(torch.ones(1, 2, 3840))
            raise RuntimeError("expected Z-Image embedding failure")
        with self.assertRaisesRegex(RuntimeError, "expected Z-Image embedding failure"):
            run_text_module_output_scale(model, "cap_embedder", broken, (), {}, 1.2)
        self.assertEqual(model.cap_embedder.forward, original)
        self.assertNotIn("forward", model.cap_embedder.__dict__)

    def test_z_image_model_wrapper_scales_cap_embedder_and_restores(self):
        model = FakeZImage()
        original = model.cap_embedder.forward
        options = {OPTION_KEY: {"enabled": True, "strength": 0.2, "text_scale": 1.0}}
        class Executor:
            class_obj = model
            def __call__(self, *args, **kwargs):
                return model.cap_embedder(torch.ones(1, 3, 3840))
        result = prompt_adherence_enhancer_pro_wrapper(Executor(), transformer_options=options)
        torch.testing.assert_close(result, torch.full((1, 3, 3840), 1.2))
        self.assertEqual(model.cap_embedder.forward, original)

    def test_thread_local_recursion_guard_does_not_skip_parallel_sampler_thread(self):
        model = FakeMoss()
        values = torch.ones(1, 2, 4)
        options = {OPTION_KEY: {"enabled": True, "strength": 0.2, "text_scale": 1.0}}
        class Executor:
            class_obj = model
            def __call__(self, *args, **kwargs):
                return model.text_embedder(values)
        results = []
        errors = []
        def worker():
            try:
                results.append(prompt_adherence_enhancer_pro_wrapper(Executor(), transformer_options=options))
            except BaseException as exc:
                errors.append(exc)
        _PATCH_STATE.active = True
        try:
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "worker thread did not finish")
        finally:
            del _PATCH_STATE.active
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 1)
        torch.testing.assert_close(results[0], torch.full_like(values, 1.2))
        self.assertNotIn("forward", model.text_embedder.__dict__)

    def test_non_krea_multipliers_are_bounded(self):
        model = FakeAnima()
        context = torch.ones(1, 2, 8)
        options = {OPTION_KEY: {"enabled": True, "strength": 2.0, "text_scale": 4.0}}
        class Executor:
            class_obj = model
            def __call__(self, x, timestep, actual_context, **kwargs):
                return actual_context
        result = prompt_adherence_enhancer_pro_wrapper(
            Executor(), torch.zeros(1, 4, 2, 2), torch.zeros(1), context,
            transformer_options=options
        )
        torch.testing.assert_close(result, torch.full_like(context, 4.0))


class ModelDetectionFailureSafetyTests(unittest.TestCase):
    def test_detection_failure_is_reported_as_passthrough(self):
        class BrokenPatcher:
            @property
            def model(self):
                raise RuntimeError("test inspection failure")
        result = detect_model_info(BrokenPatcher())
        self.assertEqual(result["detected_model"], "Unsupported model — pass-through")
        self.assertFalse(result["supported"])
        self.assertIn("inspection was incomplete", result["detection_details"])


if __name__ == "__main__":
    unittest.main()
