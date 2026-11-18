import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from features.multi_lora_model_only import (
    PhantomGodMultiLoraModelOnly,
    _model_patch_delta,
    _parse_state,
)


def fake_comfy(sd=None, utils=None):
    package = types.ModuleType("comfy")
    package.__path__ = []
    package.sd = sd or types.SimpleNamespace()
    package.utils = utils or types.SimpleNamespace()
    return package


class MultiLoraStateTests(unittest.TestCase):
    def test_empty_state(self):
        self.assertEqual(_parse_state("{}"), [])

    def test_parses_enabled_and_disabled_rows_in_order(self):
        self.assertEqual(
            _parse_state({"loras": [
                {"name": "one.safetensors", "on": True, "strength": 0.75},
                {"name": "two.safetensors", "on": False, "strength": -0.25},
            ]}),
            [
                {"name": "one.safetensors", "on": True, "strength": 0.75},
                {"name": "two.safetensors", "on": False, "strength": -0.25},
            ],
        )

    def test_normalizes_windows_separators(self):
        rows = _parse_state({"loras": [{"name": "folder\\style.safetensors"}]})
        self.assertEqual(rows[0]["name"], "folder/style.safetensors")

    def test_rejects_absolute_and_traversal_paths(self):
        for name in (
            "../outside.safetensors",
            "folder/../../outside.safetensors",
            "/absolute/model.safetensors",
            "C:\\models\\outside.safetensors",
            "folder//model.safetensors",
            "folder/./model.safetensors",
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "relative path"):
                    _parse_state({"loras": [{"name": name}]})

    def test_rejects_invalid_json(self):
        with self.assertRaises(ValueError):
            _parse_state("{broken")

    def test_accepts_more_than_the_previous_64_row_limit(self):
        rows = _parse_state({"loras": [
            {"name": "lora-{}.safetensors".format(index)}
            for index in range(70)
        ]})
        self.assertEqual(len(rows), 70)

    def test_rejects_non_finite_strength(self):
        with self.assertRaises(ValueError):
            _parse_state({"loras": [{"name": "a.safetensors", "strength": "nan"}]})

    def test_rejects_strength_outside_supported_range(self):
        with self.assertRaises(ValueError):
            _parse_state({"loras": [{"name": "a.safetensors", "strength": 101}] })


class MultiLoraNodeTests(unittest.TestCase):
    def setUp(self):
        self.node = PhantomGodMultiLoraModelOnly()

    def test_declares_model_only_input_and_output(self):
        inputs = PhantomGodMultiLoraModelOnly.INPUT_TYPES()
        self.assertEqual(set(inputs["required"]), {"model"})
        self.assertIn("LoraStackState", inputs["hidden"])
        self.assertEqual(self.node.RETURN_TYPES, ("MODEL",))
        self.assertNotIn("clip", str(inputs).lower())

    def test_empty_stack_passes_model_through(self):
        model = object()
        self.assertIs(self.node.apply(model, "{}")[0], model)

    def test_disabled_empty_and_zero_strength_rows_are_skipped(self):
        model = object()
        state = json.dumps({"loras": [
            {"name": "disabled.safetensors", "on": False, "strength": 1.0},
            {"name": "", "on": True, "strength": 1.0},
            {"name": "zero.safetensors", "on": True, "strength": 0.0},
        ]})
        package = fake_comfy()
        with patch.dict(sys.modules, {
            "folder_paths": types.ModuleType("folder_paths"),
            "comfy": package,
            "comfy.sd": package.sd,
            "comfy.utils": package.utils,
        }):
            self.assertIs(self.node.apply(model, state)[0], model)

    def test_applies_enabled_loras_sequentially_to_model_only(self):
        model = object()
        lora_a, lora_b = object(), object()
        metadata = {"format": "test"}
        folder_paths = types.SimpleNamespace(
            get_full_path_or_raise=lambda category, name: "/loras/" + name
        )
        utils = types.SimpleNamespace(load_torch_file=MagicMock())
        applied = []

        def apply_lora(current, clip, lora, strength, clip_strength, **kwargs):
            applied.append((current, clip, lora, strength, clip_strength, kwargs))
            return (("patched", len(applied)), None)

        sd = types.SimpleNamespace(load_lora_for_models=apply_lora)
        package = fake_comfy(sd, utils)
        with patch.dict(sys.modules, {
            "folder_paths": folder_paths,
            "comfy": package,
            "comfy.sd": sd,
            "comfy.utils": utils,
        }), patch("os.stat", return_value=types.SimpleNamespace(
            st_size=100,
            st_mtime=1.0,
            st_mtime_ns=1_000_000_000,
            st_ino=1,
        )):
            node = PhantomGodMultiLoraModelOnly()
            utils.load_torch_file.side_effect = [(lora_a, metadata), (lora_b, metadata)]
            state = json.dumps({"loras": [
                {"name": "one.safetensors", "on": True, "strength": 0.8},
                {"name": "off.safetensors", "on": False, "strength": 1.0},
                {"name": "two.safetensors", "on": True, "strength": -0.4},
            ]})
            result = node.apply(model, state)

        self.assertEqual(result, (("patched", 2),))
        self.assertEqual(len(applied), 2)
        self.assertTrue(all(call[1] is None and call[4] == 0.0 for call in applied))
        self.assertEqual([call[3] for call in applied], [0.8, -0.4])
        self.assertEqual(utils.load_torch_file.call_count, 2)

    def test_reload_cache_when_file_changes_at_same_path(self):
        utils = types.SimpleNamespace(load_torch_file=MagicMock(
            side_effect=[({"weights": 1}, {"revision": 1}), ({"weights": 2}, {"revision": 2})]
        ))
        package = fake_comfy(utils=utils)
        stat_values = iter([
            types.SimpleNamespace(st_size=10, st_mtime=1.0, st_mtime_ns=1_000_000_000, st_ino=1),
            types.SimpleNamespace(st_size=10, st_mtime=1.0, st_mtime_ns=1_000_000_000, st_ino=1),
            types.SimpleNamespace(st_size=12, st_mtime=2.0, st_mtime_ns=2_000_000_000, st_ino=1),
        ])
        with patch.dict(sys.modules, {
            "comfy": package,
            "comfy.utils": utils,
        }), patch("os.stat", side_effect=lambda _path: next(stat_values)):
            node = PhantomGodMultiLoraModelOnly()
            first, first_metadata = node._load_lora("/loras/example.safetensors")
            cached, cached_metadata = node._load_lora("/loras/example.safetensors")
            refreshed, refreshed_metadata = node._load_lora("/loras/example.safetensors")

        self.assertEqual(first, {"weights": 1})
        self.assertEqual(first_metadata, {"revision": 1})
        self.assertEqual(cached, first)
        self.assertEqual(cached_metadata, first_metadata)
        self.assertEqual(refreshed, {"weights": 2})
        self.assertEqual(refreshed_metadata, {"revision": 2})
        self.assertEqual(utils.load_torch_file.call_count, 2)

    def test_raises_a_clear_error_when_a_lora_is_missing(self):
        folder_paths = types.SimpleNamespace(
            get_full_path_or_raise=MagicMock(side_effect=FileNotFoundError("missing"))
        )
        package = fake_comfy()
        with patch.dict(sys.modules, {
            "folder_paths": folder_paths,
            "comfy": package,
            "comfy.sd": package.sd,
            "comfy.utils": package.utils,
        }):
            with self.assertRaisesRegex(RuntimeError, "could not apply"):
                self.node.apply(object(), json.dumps({
                    "loras": [{"name": "missing.safetensors", "on": True, "strength": 1.0}]
                }))


    def test_accepts_none_hidden_state_as_empty_stack(self):
        model = object()
        self.assertIs(self.node.apply(model, None)[0], model)

    def test_accepts_legacy_lowercase_hidden_state_argument(self):
        model = object()
        self.assertIs(
            self.node.apply(model, None, lora_stack_state="{}")[0],
            model,
        )

    def test_missing_lora_error_identifies_the_filename(self):
        folder_paths = types.SimpleNamespace(
            get_full_path_or_raise=MagicMock(side_effect=FileNotFoundError("missing"))
        )
        package = fake_comfy()
        with patch.dict(sys.modules, {
            "folder_paths": folder_paths,
            "comfy": package,
            "comfy.sd": package.sd,
            "comfy.utils": package.utils,
        }):
            with self.assertRaisesRegex(RuntimeError, "missing.safetensors"):
                self.node.apply(object(), json.dumps({
                    "loras": [{"name": "missing.safetensors", "on": True, "strength": 1.0}]
                }))


    def test_declares_hidden_input_for_api_prompt_serialization(self):
        hidden = PhantomGodMultiLoraModelOnly.INPUT_TYPES()["hidden"]
        self.assertEqual(hidden["LoraStackState"][0], "STRING")
        self.assertEqual(hidden["LoraStackState"][1]["default"], "{}")

    def test_lora_application_uses_current_comfyui_metadata_argument(self):
        model = object()
        patched = object()
        weights = {"weight": object()}
        metadata = {"format": "test"}
        folder_paths = types.SimpleNamespace(
            get_full_path_or_raise=lambda category, name: "/loras/" + name
        )
        utils = types.SimpleNamespace(
            load_torch_file=MagicMock(return_value=(weights, metadata))
        )
        calls = []
        def load_for_models(current, clip, lora, strength, clip_strength, **kwargs):
            calls.append((current, clip, lora, strength, clip_strength, kwargs))
            return patched, None
        sd = types.SimpleNamespace(load_lora_for_models=load_for_models)
        package = fake_comfy(sd, utils)
        stat = types.SimpleNamespace(st_size=1, st_mtime=1, st_mtime_ns=1, st_ino=1)
        with patch.dict(sys.modules, {
            "folder_paths": folder_paths,
            "comfy": package,
            "comfy.sd": sd,
            "comfy.utils": utils,
        }), patch("os.stat", return_value=stat):
            result = PhantomGodMultiLoraModelOnly().apply(
                model,
                json.dumps({"loras": [{"name": "a.safetensors", "strength": 0.5}]})
            )
        self.assertIs(result[0], patched)
        self.assertIs(calls[0][0], model)
        self.assertIsNone(calls[0][1])
        self.assertEqual(calls[0][3:5], (0.5, 0.0))
        self.assertEqual(calls[0][5], {"lora_metadata": metadata})

    def test_does_not_mask_internal_type_error_as_api_compatibility(self):
        model = object()
        folder_paths = types.SimpleNamespace(
            get_full_path_or_raise=lambda category, name: "/loras/a.safetensors"
        )
        utils = types.SimpleNamespace(load_torch_file=MagicMock(return_value=({"weight": 1}, None)))
        sd = types.SimpleNamespace(
            load_lora_for_models=MagicMock(side_effect=TypeError("internal tensor error"))
        )
        package = fake_comfy(sd, utils)
        with patch.dict(sys.modules, {
            "folder_paths": folder_paths,
            "comfy": package,
            "comfy.sd": sd,
            "comfy.utils": utils,
        }), patch("os.stat", return_value=types.SimpleNamespace(st_size=1, st_mtime=1, st_mtime_ns=1, st_ino=1)):
            with self.assertRaisesRegex(RuntimeError, "internal tensor error"):
                PhantomGodMultiLoraModelOnly().apply(
                    model,
                    json.dumps({"loras": [{"name": "a.safetensors", "strength": 1}]})
                )


    def test_rejects_lora_when_comfyui_adds_no_model_patches(self):
        original_uuid = object()
        model = types.SimpleNamespace(
            patches_uuid=original_uuid,
            patches={},
            object_patches={},
            weight_wrapper_patches={},
        )
        unchanged = types.SimpleNamespace(
            patches_uuid=original_uuid,
            patches={},
            object_patches={},
            weight_wrapper_patches={},
        )
        folder_paths = types.SimpleNamespace(
            get_full_path_or_raise=lambda category, name: "/loras/" + name
        )
        utils = types.SimpleNamespace(load_torch_file=MagicMock(return_value=({"text_encoder.weight": 1}, None)))
        sd = types.SimpleNamespace(load_lora_for_models=lambda *args, **kwargs: (unchanged, None))
        package = fake_comfy(sd, utils)
        stat = types.SimpleNamespace(st_size=1, st_mtime=1, st_mtime_ns=1, st_ino=1)
        with patch.dict(sys.modules, {
            "folder_paths": folder_paths,
            "comfy": package,
            "comfy.sd": sd,
            "comfy.utils": utils,
        }), patch("os.stat", return_value=stat):
            with self.assertRaisesRegex(RuntimeError, "no weights compatible"):
                PhantomGodMultiLoraModelOnly().apply(
                    model,
                    json.dumps({"loras": [{"name": "text-only.safetensors", "strength": 1}]})
                )

    def test_detects_model_patches_added_to_existing_patch_keys(self):
        before_uuid = object()
        after_uuid = object()
        before = types.SimpleNamespace(
            patches_uuid=before_uuid,
            patches={"layer.weight": [("old",)]},
            object_patches={},
            weight_wrapper_patches={},
        )
        after = types.SimpleNamespace(
            patches_uuid=after_uuid,
            patches={"layer.weight": [("old",), ("new",)]},
            object_patches={},
            weight_wrapper_patches={},
        )
        self.assertIs(_model_patch_delta(before, after), True)

    def test_does_not_fallback_for_internal_lora_file_type_error(self):
        utils = types.SimpleNamespace(
            load_torch_file=MagicMock(side_effect=[
                TypeError("tensor shape decode failed"),
                ({"weight": 1}, None),
            ])
        )
        package = fake_comfy(utils=utils)
        with patch.dict(sys.modules, {"comfy": package, "comfy.utils": utils}), patch(
            "os.stat",
            return_value=types.SimpleNamespace(st_size=1, st_mtime=1, st_mtime_ns=1, st_ino=1),
        ):
            with self.assertRaisesRegex(TypeError, "tensor shape decode failed"):
                PhantomGodMultiLoraModelOnly()._load_lora("/loras/test.safetensors")
        utils.load_torch_file.assert_called_once_with(
            "/loras/test.safetensors", safe_load=True, return_metadata=True
        )


if __name__ == "__main__":
    unittest.main()
