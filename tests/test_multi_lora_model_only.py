import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from features.multi_lora_model_only import (
    PhantomGodMultiLoraModelOnly,
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


if __name__ == "__main__":
    unittest.main()
