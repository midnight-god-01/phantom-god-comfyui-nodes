import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def load_registry():
    folder_paths = types.ModuleType("folder_paths")
    folder_paths.get_filename_list = lambda _kind: []
    folder_paths.get_full_path = lambda _kind, name: name
    comfy = types.ModuleType("comfy")
    comfy.__path__ = []
    comfy.sd = types.ModuleType("comfy.sd")
    comfy.utils = types.ModuleType("comfy.utils")
    server = types.ModuleType("server")
    class Routes:
        def get(self, _path):
            return lambda function: function
    class PromptServer:
        instance = types.SimpleNamespace(routes=Routes())
    server.PromptServer = PromptServer
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.web = types.SimpleNamespace(json_response=lambda payload, status=200: (payload, status))
    modules = {"folder_paths": folder_paths, "comfy": comfy, "comfy.sd": comfy.sd,
               "comfy.utils": comfy.utils, "server": server, "aiohttp": aiohttp}
    with patch.dict(sys.modules, modules):
        from features import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
        return NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS


class FeatureRegistryTests(unittest.TestCase):
    def test_expected_model_only_node_is_registered(self):
        classes, names = load_registry()
        self.assertIn("PixaromaLoraModelOnly", classes)
        self.assertIn("PixaromaLoraModelOnly", names)
        self.assertEqual("LoRA Loader (Model Only) - Phantom God", names["PixaromaLoraModelOnly"])

    def test_removed_feature_modules_remain_absent(self):
        feature_dir = Path(__file__).resolve().parents[1] / "features"
        removed_modules = {"concatenate_text.py", "environment_manager.py", "multi_lora_model_only.py"}
        present_modules = {path.name for path in feature_dir.glob("*.py")}
        self.assertTrue(removed_modules.isdisjoint(present_modules))


if __name__ == "__main__":
    unittest.main()
