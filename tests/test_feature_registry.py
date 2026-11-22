import unittest
from pathlib import Path

from features import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS


class FeatureRegistryTests(unittest.TestCase):
    def test_prompt_adherence_node_is_registered_once(self):
        node_id = "PromptAdherenceEnhancerPro"
        self.assertEqual({node_id}, set(NODE_CLASS_MAPPINGS))
        self.assertEqual({node_id}, set(NODE_DISPLAY_NAME_MAPPINGS))
        self.assertEqual(NODE_DISPLAY_NAME_MAPPINGS[node_id], "Prompt Adherence Enhancer Pro")

    def test_helper_modules_are_not_registered_as_nodes(self):
        feature_dir = Path(__file__).resolve().parents[1] / "features"
        self.assertTrue((feature_dir / "prompt_adherence_enhancer_pro.py").is_file())
        self.assertTrue((feature_dir / "_paa_architecture_adapters.py").is_file())
        self.assertTrue((feature_dir / "_paa_enhancer_math.py").is_file())
        self.assertTrue((feature_dir / "_paa_model_detection_info.py").is_file())

    def test_removed_feature_modules_are_absent(self):
        feature_dir = Path(__file__).resolve().parents[1] / "features"
        removed_modules = {
            "concatenate_text.py",
            "environment_manager.py",
            "multi_lora_model_only.py",
        }
        present_modules = {path.name for path in feature_dir.glob("*.py")}
        self.assertTrue(removed_modules.isdisjoint(present_modules))


if __name__ == "__main__":
    unittest.main()
