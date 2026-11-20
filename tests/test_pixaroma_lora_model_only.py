import asyncio
import importlib.util
import json
import math
import struct
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "features" / "pixaroma_lora_model_only.py"


def load_feature():
    routes = {}

    class RouteRegistry:
        def get(self, path):
            def register(function):
                routes[path] = function
                return function
            return register

    folder_paths = types.ModuleType("folder_paths")
    folder_paths.get_filename_list = lambda _kind: ["style.safetensors"]
    folder_paths.get_full_path = lambda _kind, name: f"/loras/{name}"

    comfy = types.ModuleType("comfy")
    comfy.__path__ = []
    sd, utils = types.ModuleType("comfy.sd"), types.ModuleType("comfy.utils")
    comfy.sd, comfy.utils = sd, utils

    server = types.ModuleType("server")
    class PromptServer:
        instance = types.SimpleNamespace(routes=RouteRegistry())
    server.PromptServer = PromptServer

    aiohttp = types.ModuleType("aiohttp")
    aiohttp.web = types.SimpleNamespace(
        json_response=lambda payload, status=200: (status, payload)
    )

    modules = {
        "folder_paths": folder_paths,
        "comfy": comfy,
        "comfy.sd": sd,
        "comfy.utils": utils,
        "server": server,
        "aiohttp": aiohttp,
    }
    with patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("test_pixaroma_lora_model_only", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, folder_paths, sd, utils, routes


class ModelOnlyLoraTests(unittest.TestCase):
    def test_schema_has_only_one_model_input_and_one_model_output(self):
        module, *_ = load_feature()
        node = module.PixaromaLoraModelOnly
        self.assertEqual(["model", "lora_state"], list(node.INPUT_TYPES()["required"]))
        self.assertEqual("MODEL", node.INPUT_TYPES()["required"]["model"][0])
        self.assertEqual("STRING", node.INPUT_TYPES()["required"]["lora_state"][0])
        self.assertNotIn("hidden", node.INPUT_TYPES())
        self.assertNotIn("CLIP", repr(node.INPUT_TYPES()))
        self.assertEqual(("MODEL",), node.RETURN_TYPES)
        self.assertEqual(("MODEL",), node.RETURN_NAMES)

    def test_stacks_loras_using_native_model_only_semantics(self):
        module, folder_paths, sd, utils, _routes = load_feature()
        node = module.PixaromaLoraModelOnly()
        folder_paths.get_full_path = lambda _kind, name: f"/valid/{name}"
        utils.load_torch_file = Mock(side_effect=lambda path, **_kwargs: ({"layer": path}, {"meta": path}))
        with patch.object(module.os.path, "isfile", return_value=True), patch.object(module.os, "stat") as stat:
            stat.return_value.st_size, stat.return_value.st_mtime_ns = 5, 10
            calls = []

            def apply(model, clip, weights, strength_model, strength_clip, **kwargs):
                calls.append((weights["layer"], clip, strength_model, strength_clip, kwargs))
                return model + [strength_model], None

            sd.load_lora_for_models = Mock(side_effect=apply)
            state = {"cacheMode": "all", "loras": [
                {"name": "style-a.safetensors", "on": True, "strength": 0.7},
                {"name": "style-b.safetensors", "on": True, "strength": -0.2},
            ]}
            result = node.apply(["base"], json.dumps(state))

        self.assertEqual((["base", 0.7, -0.2],), result)
        self.assertEqual(2, len(calls))
        self.assertEqual(["/valid/style-a.safetensors", "/valid/style-b.safetensors"], [call[0] for call in calls])
        self.assertTrue(all(call[1] is None and call[3] == 0.0 for call in calls))
        self.assertTrue(all(call[4] == {"lora_metadata": {"meta": call[0]}} for call in calls))


    def test_old_comfyui_loader_signatures_fall_back_without_metadata(self):
        module, folder_paths, sd, utils, _routes = load_feature()
        node = module.PixaromaLoraModelOnly()
        folder_paths.get_full_path = lambda _kind, name: f"/valid/{name}"
        loader_calls = []

        def old_file_loader(path, safe_load=True, **kwargs):
            if "return_metadata" in kwargs:
                raise TypeError("unexpected keyword argument 'return_metadata'")
            loader_calls.append(path)
            return {"layer": "weights"}

        patch_calls = []

        def old_lora_loader(model, clip, weights, strength_model, strength_clip):
            patch_calls.append((clip, strength_model, strength_clip))
            return model + ["patched"], None

        utils.load_torch_file = old_file_loader
        sd.load_lora_for_models = old_lora_loader
        with patch.object(module.os.path, "isfile", return_value=True), patch.object(module.os, "stat") as stat:
            stat.return_value.st_size, stat.return_value.st_mtime_ns = 5, 10
            result = node.apply(["model"], json.dumps({"loras": [
                {"name": "style.safetensors", "strength": 0.8},
            ]}))

        self.assertEqual((["model", "patched"],), result)
        self.assertEqual(["/valid/style.safetensors"], loader_calls)
        self.assertEqual([(None, 0.8, 0.0)], patch_calls)

    def test_cache_modes_keep_all_last_or_no_lora_weights(self):
        module, folder_paths, sd, utils, _routes = load_feature()
        folder_paths.get_full_path = lambda _kind, name: f"/valid/{name}"
        utils.load_torch_file = Mock(side_effect=lambda path, **_kwargs: ({"layer": path}, {}))
        sd.load_lora_for_models = Mock(side_effect=lambda model, _clip, _weights, _sm, _sc, **_kwargs: (model, None))
        rows = [
            {"name": "a.safetensors", "on": True, "strength": 1},
            {"name": "b.safetensors", "on": True, "strength": 1},
        ]
        with patch.object(module.os.path, "isfile", return_value=True), patch.object(module.os, "stat") as stat:
            stat.return_value.st_size, stat.return_value.st_mtime_ns = 10, 20
            all_node = module.PixaromaLoraModelOnly()
            all_node.apply("model", json.dumps({"cacheMode": "all", "loras": rows}))
            self.assertEqual({"/valid/a.safetensors", "/valid/b.safetensors"}, set(all_node._cache))

            last_node = module.PixaromaLoraModelOnly()
            last_node.apply("model", json.dumps({"cacheMode": "last", "loras": rows}))
            self.assertEqual({"/valid/b.safetensors"}, set(last_node._cache))

            no_cache_node = module.PixaromaLoraModelOnly()
            no_cache_node.apply("model", json.dumps({"cacheMode": "none", "loras": rows}))
            self.assertEqual({}, no_cache_node._cache)

    def test_disabled_rows_do_not_apply(self):
        module, _folder_paths, sd, utils, _routes = load_feature()
        node = module.PixaromaLoraModelOnly()
        utils.load_torch_file = Mock()
        state = {"loras": [
            {"name": "style.safetensors", "on": False, "strength": 1},
        ]}
        self.assertEqual(("model",), node.apply("model", json.dumps(state)))
        self.assertFalse(hasattr(sd, "load_lora_for_models"))
        utils.load_torch_file.assert_not_called()

    def test_zero_strength_rows_do_not_load_or_modify_the_model(self):
        module, _folder_paths, sd, utils, _routes = load_feature()
        node = module.PixaromaLoraModelOnly()
        utils.load_torch_file = Mock()
        state = {"loras": [
            {"name": "style.safetensors", "on": True, "strength": 0},
        ]}
        self.assertEqual(("model",), node.apply("model", json.dumps(state)))
        self.assertFalse(hasattr(sd, "load_lora_for_models"))
        utils.load_torch_file.assert_not_called()

    def test_failed_lora_is_skipped_and_original_model_is_returned(self):
        module, folder_paths, sd, utils, _routes = load_feature()
        node = module.PixaromaLoraModelOnly()
        folder_paths.get_full_path = lambda _kind, name: f"/valid/{name}"
        utils.load_torch_file = Mock(return_value=({"layer": "weights"}, {"meta": "value"}))
        sd.load_lora_for_models = Mock(side_effect=ValueError("incompatible LoRA tensors"))
        with patch.object(module.os.path, "isfile", return_value=True), patch.object(module.os, "stat") as stat:
            stat.return_value.st_size, stat.return_value.st_mtime_ns = 5, 10
            result = node.apply("model", json.dumps({"loras": [
                {"name": "style.safetensors", "on": True, "strength": 1},
            ]}))
        self.assertEqual(("model",), result)
        sd.load_lora_for_models.assert_called_once()

    def test_bad_state_non_list_rows_and_invalid_strength_are_normalized(self):
        module, *_ = load_feature()
        self.assertEqual([], module._parse_state("not-json")["loras"])
        self.assertEqual([], module._parse_state(json.dumps({"loras": 4}))["loras"])
        state = module._parse_state(json.dumps({"loras": [
            {"name": "x.safetensors", "strength": 101},
            {"name": "y.safetensors", "strength": "nan"},
            {"name": "z.safetensors", "strength": "inf"},
        ]}))
        self.assertEqual([0.0, 0.0, 0.0], [row["strength"] for row in state["loras"]])
        accepted = module._parse_state(json.dumps({"loras": [
            {"name": "low.safetensors", "strength": -100},
            {"name": "high.safetensors", "strength": 100},
        ]}))
        self.assertEqual([-100.0, 100.0], [row["strength"] for row in accepted["loras"]])
        self.assertTrue(all(set(row) == {"name", "on", "strength"} for row in state["loras"]))
        self.assertNotIn("sep", state)

    def test_unsafe_path_names_are_rejected(self):
        module, *_ = load_feature()
        for name in ("../secret.safetensors", "/tmp/secret.safetensors", "C:\\secret.safetensors", "sub/../../secret.safetensors"):
            self.assertIsNone(module._resolve(name), name)

    def test_safetensors_header_metadata_is_read_without_loading_tensor_payload(self):
        module, *_ = load_feature()
        metadata = {"__metadata__": {"modelspec.title": "Header Test", "ss_network_dim": "32"}}
        header = json.dumps(metadata).encode("utf-8")
        file_path = ROOT / "fake.safetensors"
        file_path.write_bytes(struct.pack("<Q", len(header)) + header + b"tensor-payload")
        try:
            result = module._read_safetensors_metadata(str(file_path))
            self.assertEqual("Header Test", result["modelspec.title"])
            self.assertEqual("32", result["ss_network_dim"])
        finally:
            file_path.unlink(missing_ok=True)

    def test_lora_info_extracts_model_metadata_without_prompt_terms(self):
        module, folder_paths, *_ = load_feature()
        metadata = {
            "modelspec.title": "Test LoRA",
            "modelspec.architecture": "sdxl",
            "ss_network_dim": "16",
        }
        module._read_safetensors_metadata = lambda _path: metadata
        folder_paths.get_full_path = lambda _kind, _name: "/valid/style.safetensors"
        with patch.object(module.os.path, "isfile", return_value=True):
            info = module._lora_info("style.safetensors")
        self.assertEqual("Test LoRA", info["title"])
        self.assertEqual("SDXL", info["base_model"])
        self.assertEqual("16", info["rank"])
        self.assertNotIn("triggers", info)
        self.assertNotIn("explicit_triggers", info)

    def test_metadata_route_returns_json_and_rejects_unlisted_paths(self):
        module, folder_paths, _sd, _utils, routes = load_feature()
        route = routes["/phantom-god/lora-info"]
        module._read_safetensors_metadata = lambda _path: {"ss_network_dim": "16"}
        folder_paths.get_full_path = lambda _kind, name: f"/valid/{name}"
        with patch.object(module.os.path, "isfile", return_value=True):
            ok = asyncio.run(route(types.SimpleNamespace(query={"name": "style.safetensors"})))
            bad = asyncio.run(route(types.SimpleNamespace(query={"name": "../../secret.safetensors"})))
            folder_paths.get_filename_list = lambda _kind: ["nested\\style.safetensors"]
            portable = asyncio.run(route(types.SimpleNamespace(query={"name": "nested/style.safetensors"})))
        self.assertEqual(200, ok[0])
        self.assertTrue(ok[1]["ok"])
        self.assertEqual("16", ok[1]["info"]["rank"])
        self.assertEqual(404, bad[0])
        self.assertEqual(200, portable[0])

    def test_change_signature_is_deterministic_for_missing_files(self):
        module, folder_paths, *_ = load_feature()
        folder_paths.get_filename_list = lambda _kind: []
        state = json.dumps({"loras": [{"name": "missing.safetensors", "on": True}]})
        first = module.PixaromaLoraModelOnly.IS_CHANGED(state)
        second = module.PixaromaLoraModelOnly.IS_CHANGED(state)
        self.assertEqual(first, second)
        self.assertIn("missing:", first)

    def test_change_signature_retries_when_the_lora_library_is_unavailable(self):
        module, folder_paths, *_ = load_feature()
        folder_paths.get_filename_list = Mock(side_effect=OSError("temporary library error"))
        signature = module.PixaromaLoraModelOnly.IS_CHANGED("{}")
        self.assertTrue(math.isnan(signature))

    def test_change_signature_handles_disappearing_paths(self):
        module, folder_paths, *_ = load_feature()
        folder_paths.get_filename_list = lambda _kind: ["style.safetensors"]
        folder_paths.get_full_path = lambda _kind, _name: None
        state = json.dumps({"loras": [{"name": "style.safetensors", "on": True}]})
        signature = module.PixaromaLoraModelOnly.IS_CHANGED(state)
        self.assertIn("missing:style.safetensors", signature)

    def test_zero_strength_rows_do_not_invalidate_the_model_cache(self):
        module, folder_paths, *_ = load_feature()
        state = json.dumps({"loras": [
            {"name": "style.safetensors", "on": True, "strength": 0},
        ]})
        folder_paths.get_filename_list = lambda _kind: []
        missing = module.PixaromaLoraModelOnly.IS_CHANGED(state)
        folder_paths.get_filename_list = lambda _kind: ["style.safetensors"]
        present = module.PixaromaLoraModelOnly.IS_CHANGED(state)
        self.assertEqual("", missing)
        self.assertEqual(missing, present)


if __name__ == "__main__":
    unittest.main()
