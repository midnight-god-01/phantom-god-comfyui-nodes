import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class FakeWrappersMP:
    DIFFUSION_MODEL = "diffusion_model"


class FakeModel:
    def __init__(self, base_model=None):
        self.model = base_model
        self.model_options = {}
        self.wrappers = {}

    def clone(self):
        cloned = FakeModel(self.model)
        cloned.model_options = {k: dict(v) if isinstance(v, dict) else v for k, v in self.model_options.items()}
        cloned.wrappers = {k: dict(v) for k, v in self.wrappers.items()}
        return cloned

    def remove_wrappers_with_key(self, wrapper_type, key):
        self.wrappers.get(wrapper_type, {}).pop(key, None)

    def add_wrapper_with_key(self, wrapper_type, key, wrapper):
        self.wrappers.setdefault(wrapper_type, {})[key] = [wrapper]
        self.model_options.setdefault("transformer_options", {}).setdefault("wrappers", {}).setdefault(wrapper_type, {})[key] = [wrapper]


class RegistrationTests(unittest.TestCase):
    def test_visible_node_name_is_prompt_adherence_enhancer_pro(self):
        from features.prompt_adherence_enhancer_pro import (
            NODE_CLASS_MAPPINGS,
            NODE_DISPLAY_NAME_MAPPINGS,
            PromptAdherenceEnhancerPro,
        )
        node_id = "PromptAdherenceEnhancerPro"
        self.assertEqual(set(NODE_CLASS_MAPPINGS), {node_id})
        self.assertEqual(set(NODE_DISPLAY_NAME_MAPPINGS), {node_id})
        self.assertIs(NODE_CLASS_MAPPINGS[node_id], PromptAdherenceEnhancerPro)
        self.assertEqual(NODE_DISPLAY_NAME_MAPPINGS[node_id], "Prompt Adherence Enhancer Pro")

    def test_apply_clones_and_attaches_only_model_wrapper(self):
        from features.prompt_adherence_enhancer_pro import PromptAdherenceEnhancerPro, WRAPPER_KEY
        fake_module = types.SimpleNamespace(WrappersMP=FakeWrappersMP)
        original = FakeModel()
        with patch.dict(sys.modules, {"comfy": types.ModuleType("comfy"), "comfy.patcher_extension": fake_module}):
            output = PromptAdherenceEnhancerPro().apply(original)
        result, = output["result"]
        self.assertEqual(output["ui"]["detected_model"][0], "Unsupported model — pass-through")
        self.assertIsNot(result, original)
        self.assertIn(WRAPPER_KEY, result.wrappers[FakeWrappersMP.DIFFUSION_MODEL])
        self.assertNotIn("transformer_options", original.model_options)
        self.assertEqual(PromptAdherenceEnhancerPro.RETURN_TYPES, ("MODEL",))

    def test_enhancer_wrapper_survives_standard_lora_model_clone(self):
        from features.prompt_adherence_enhancer_pro import PromptAdherenceEnhancerPro, OPTION_KEY, WRAPPER_KEY
        fake_module = types.SimpleNamespace(WrappersMP=FakeWrappersMP)
        original = FakeModel()
        with patch.dict(sys.modules, {"comfy": types.ModuleType("comfy"), "comfy.patcher_extension": fake_module}):
            enhanced_output = PromptAdherenceEnhancerPro().apply(original)
            enhanced, = enhanced_output["result"]
            turbo_lora_result = enhanced.clone()
        self.assertIn(WRAPPER_KEY, turbo_lora_result.wrappers[FakeWrappersMP.DIFFUSION_MODEL])
        self.assertIn(OPTION_KEY, turbo_lora_result.model_options["transformer_options"])
        self.assertTrue(turbo_lora_result.model_options["transformer_options"][OPTION_KEY]["enabled"])

    def test_apply_reports_detected_architecture_in_ui_output(self):
        import torch
        from features.prompt_adherence_enhancer_pro import PromptAdherenceEnhancerPro

        class FakeMoss(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.text_embedder = torch.nn.Identity()
                self.video_embedder = torch.nn.Identity()
                self.shared_block_modulation = torch.nn.Identity()
                self.layers = torch.nn.ModuleList([torch.nn.Identity()])

        base_model = types.SimpleNamespace(diffusion_model=FakeMoss())
        original = FakeModel(base_model)
        fake_module = types.SimpleNamespace(WrappersMP=FakeWrappersMP)
        with patch.dict(sys.modules, {"comfy": types.ModuleType("comfy"), "comfy.patcher_extension": fake_module}):
            output = PromptAdherenceEnhancerPro().apply(original)
        self.assertEqual(output["ui"]["detected_model"], ["MOSS-Image"])
        details = output["ui"]["detection_details"][0]
        self.assertIn("text_embedder", details)
        self.assertIn("FakeMoss", details)
        self.assertEqual(len(output["result"]), 1)

    def test_frontend_detection_widgets_are_configured_as_display_only(self):
        root = Path(__file__).resolve().parents[1]
        extension = (root / "web" / "js" / "prompt_adherence_enhancer_pro.js").read_text()
        package_init = (root / "__init__.py").read_text()
        self.assertIn('WEB_DIRECTORY = "./web/js"', package_init)
        self.assertIn("beforeRegisterNodeDef", extension)
        self.assertIn("onExecuted", extension)
        self.assertIn("Auto-detected model", extension)
        self.assertIn("Detection / adapter details", extension)
        self.assertIn("widget.serialize = false", extension)
        self.assertIn("serialize: false", extension)

    def test_node_info_explains_supported_families_and_detection(self):
        from features.prompt_adherence_enhancer_pro import PromptAdherenceEnhancerPro
        description = PromptAdherenceEnhancerPro.DESCRIPTION
        for family in ("Krea 2", "Anima", "MOSS-Image", "Qwen-Image 2.1", "Z-Image"):
            self.assertIn(family, description)
        self.assertIn("structur", description.lower())
        self.assertIn("Turbo", description)


if __name__ == "__main__":
    unittest.main()
