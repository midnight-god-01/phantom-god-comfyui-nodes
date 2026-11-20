import unittest
from pathlib import Path

from features import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS


class FeatureRegistryTests(unittest.TestCase):
    def test_no_workflow_nodes_are_registered(self):
        self.assertEqual({}, NODE_CLASS_MAPPINGS)
        self.assertEqual({}, NODE_DISPLAY_NAME_MAPPINGS)

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
