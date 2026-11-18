import unittest
from unittest.mock import patch

from features.environment_manager import (
    _parse_sage_wheel,
    _parse_torch_tag,
    _sage_report,
    _select_sage_wheel,
    _triton_target,
    _triton_report,
    PhantomGodEnvironmentManager,
    _version_sort_key,
)


class IsolatedImportCheckTests(unittest.TestCase):
    def test_import_check_runs_in_a_child_interpreter(self):
        completed = types.SimpleNamespace(
            returncode=0,
            stdout='"3.9.0"\\n',
            stderr="",
        )
        with patch(
            "features.environment_manager.subprocess.run",
            return_value=completed,
        ) as run, patch(
            "features.environment_manager.importlib.import_module",
            side_effect=AssertionError("must not import native modules in ComfyUI"),
        ):
            imported, version = _safe_import_status("triton")

        self.assertTrue(imported)
        self.assertEqual(version, "3.9.0")
        args, kwargs = run.call_args
        self.assertEqual(args[0][0], __import__("sys").executable)
        self.assertEqual(args[0][1:3], ["-c", args[0][2]])
        self.assertEqual(args[0][-1], "triton")
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["timeout"], 30)

    def test_import_check_reports_child_process_errors(self):
        completed = types.SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="ImportError: missing native runtime",
        )
        with patch(
            "features.environment_manager.subprocess.run",
            return_value=completed,
        ):
            imported, detail = _safe_import_status("sageattention")

        self.assertFalse(imported)
        self.assertIn("missing native runtime", detail)

    def test_import_check_reports_timeout(self):
        with patch(
            "features.environment_manager.subprocess.run",
            side_effect=__import__("subprocess").TimeoutExpired("python", 30),
        ):
            imported, detail = _safe_import_status("triton")

        self.assertFalse(imported)
        self.assertIn("timed out after 30 seconds", detail)


class EnvironmentManagerCompatibilityTests(unittest.TestCase):
    def test_triton_windows_tracks_pytorch_minor(self):
        target = _triton_target("2.15.0+cu130", "Windows")
        self.assertEqual(target["package"], "triton-windows")
        self.assertEqual(target["minor"], 9)
        self.assertEqual(target["spec"], ">=3.9,<3.10")

    def test_triton_linux_uses_official_package(self):
        target = _triton_target("2.14.1+cu128", "Linux")
        self.assertEqual(target["package"], "triton")
        self.assertEqual(target["minor"], 8)

    def test_linux_supports_pytorch_2_15_triton_3_9(self):
        target = _triton_target("2.15.0+cu130", "Linux")
        self.assertEqual(target["package"], "triton")
        self.assertEqual(target["minor"], 9)
        self.assertEqual(target["spec"], ">=3.9,<3.10")

    def test_unknown_linux_triton_mapping_is_not_guessed(self):
        self.assertIsNone(_triton_target("2.16.0+cu130", "Linux"))


    def test_triton_rejects_python_above_official_wheel_range(self):
        env = {
            "torch": "2.13.1+cu130", "python": "3.15.0",
            "system": "Linux", "machine": "x86_64",
            "cuda_available": True, "cuda": "13.0", "capability": [8, 6],
        }
        with patch("features.environment_manager._latest_pypi_version", return_value="3.7.1"), patch(
            "features.environment_manager._distribution_version", return_value=None
        ):
            report = _triton_report(env)
        self.assertFalse(report["supported"])
        self.assertEqual(report["status"], "Unsupported Python")
        self.assertIn("through 3.14", report["message"])

    def test_triton_39_accepts_python_315_on_linux(self):
        env = {
            "torch": "2.15.0+cu130", "python": "3.15.0",
            "system": "Linux", "machine": "x86_64",
            "cuda_available": True, "cuda": "13.0", "capability": [8, 6],
        }
        with patch(
            "features.environment_manager._latest_pypi_version",
            return_value="3.9.0",
        ), patch(
            "features.environment_manager._distribution_version",
            return_value=None,
        ):
            report = _triton_report(env)

        self.assertTrue(report["supported"])
        self.assertEqual(report["status"], "Not installed")
        self.assertEqual(report["target_minor"], 9)

    def test_triton_windows_39_accepts_python_315_abi3_wheel(self):
        env = {
            "torch": "2.15.0+cu130", "python": "3.15.0",
            "system": "Windows", "machine": "AMD64",
            "cuda_available": True, "cuda": "13.0", "capability": [8, 6],
        }
        with patch(
            "features.environment_manager._latest_pypi_version",
            return_value="3.9.0.post30",
        ), patch(
            "features.environment_manager._distribution_version",
            return_value=None,
        ):
            report = _triton_report(env)

        self.assertTrue(report["supported"])
        self.assertEqual(report["status"], "Not installed")
        self.assertEqual(report["target_minor"], 9)

    def test_triton_rejects_python_below_supported_minimum(self):
        env = {
            "torch": "2.10.1+cu128", "python": "3.8.18",
            "system": "Linux", "machine": "x86_64",
            "cuda_available": True, "cuda": "12.8", "capability": [8, 6],
        }
        report = _triton_report(env)
        self.assertFalse(report["supported"])
        self.assertEqual(report["status"], "Unsupported Python")
        self.assertIn("Python 3.10", report["message"])

    def test_triton_preserves_windows_legacy_package_conflict_status(self):
        env = {
            "torch": "2.15.0+cu130", "python": "3.13.0",
            "system": "Windows", "machine": "AMD64",
            "cuda_available": True, "cuda": "13.0", "capability": [8, 6],
        }
        def package_version(name):
            return {"triton": "3.2.0", "triton-windows": "3.9.0"}.get(name)
        with patch("features.environment_manager._distribution_version", side_effect=package_version), patch(
            "features.environment_manager._latest_pypi_version", return_value="3.9.1"
        ), patch("features.environment_manager._safe_import_status", return_value=(True, None)):
            report = _triton_report(env)
        self.assertTrue(report["supported"])
        self.assertEqual(report["status"], "Package conflict")
        self.assertIn("Legacy 'triton' 3.2.0", report["message"])
        self.assertIn("Current triton-windows state: Update available", report["message"])

    def test_windows_sageattention_is_blocked_by_legacy_triton_conflict(self):
        wheel = {
            "version": "2.2.0+cu130torch215",
            "url": "https://example.invalid/sageattention.whl",
        }
        env = {
            "torch": "2.15.0+cu130", "python": "3.13.0", "cuda": "13.0",
            "cuda_available": True, "system": "Windows",
            "machine": "AMD64", "capability": [8, 6],
        }
        def package_version(name):
            return {
                "sageattention": wheel["version"],
                "triton-windows": "3.9.0",
                "triton": "3.2.0",
            }.get(name)
        with patch("features.environment_manager._load_sage_wheels", return_value=([wheel], None)), patch(
            "features.environment_manager._select_sage_wheel", return_value=(wheel, "Exact match")
        ), patch("features.environment_manager._distribution_version", side_effect=package_version), patch(
            "features.environment_manager._safe_import_status", return_value=(True, None)
        ):
            report = _sage_report(env)
        self.assertFalse(report["supported"])
        self.assertEqual(report["status"], "Prerequisite missing")
        self.assertIn("Conflicting legacy 'triton' 3.2.0", report["triton_note"])

    def test_post_release_sorts_after_base_version(self):
        self.assertGreater(_version_sort_key("3.6.0.post2"), _version_sort_key("3.6.0"))
        self.assertGreater(_version_sort_key("3.6.0.post10"), _version_sort_key("3.6.0.post2"))

    def test_torch_wheel_tags_accept_compact_and_dotted_versions(self):
        self.assertEqual(_parse_torch_tag("210"), (2, 10))
        self.assertEqual(_parse_torch_tag("2.11"), (2, 11))

    def test_parse_sageattention_wheel_name(self):
        wheel = _parse_sage_wheel(
            "sageattention-2.2.0+cu128torch210-cp312-cp312-win_amd64.whl",
            "https://example.invalid/wheel.whl",
        )
        self.assertEqual(wheel["torch_pair"], (2, 10))
        self.assertEqual(wheel["cuda_tag"], "128")
        self.assertEqual(wheel["python_tag"], "312")

    def test_parse_sageattention_dotted_torch_tag(self):
        wheel = _parse_sage_wheel(
            "sageattention-2.2.0+cu130torch2.9-cp313-cp313-win_amd64.whl",
            "https://example.invalid/wheel.whl",
        )
        self.assertEqual(wheel["torch_pair"], (2, 9))
        self.assertEqual(wheel["cuda_tag"], "130")

    def test_sageattention_selects_only_exact_environment_wheel(self):
        wheels = [
            _parse_sage_wheel(
                "sageattention-2.2.0+cu128torch210-cp312-cp312-win_amd64.whl",
                "https://example.invalid/torch210.whl",
            ),
            _parse_sage_wheel(
                "sageattention-2.2.0+cu130torch210-cp312-cp312-win_amd64.whl",
                "https://example.invalid/cu130.whl",
            ),
            _parse_sage_wheel(
                "sageattention-2.2.0+cu128torch29-cp312-cp312-win_amd64.whl",
                "https://example.invalid/torch29.whl",
            ),
        ]
        selected, reason = _select_sage_wheel(
            wheels, (3, 12), "2.10.0+cu128", "12.8",
            "Windows", "AMD64", capability=(8, 9),
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected["torch_pair"], (2, 10))
        self.assertEqual(selected["cuda_tag"], "128")
        self.assertIn("Exact", reason)

    def test_sageattention_rejects_pre_ampere_gpu(self):
        wheel = _parse_sage_wheel(
            "sageattention-2.2.0+cu128torch210-cp312-cp312-win_amd64.whl",
            "https://example.invalid/wheel.whl",
        )
        selected, reason = _select_sage_wheel(
            [wheel], (3, 12), "2.10.0", "12.8",
            "Windows", "AMD64", capability=(7, 5),
        )
        self.assertIsNone(selected)
        self.assertIn("support NVIDIA compute capabilities", reason)

    def test_sageattention_rejects_mismatched_cuda(self):
        wheel = _parse_sage_wheel(
            "sageattention-2.2.0+cu128torch210-cp312-cp312-win_amd64.whl",
            "https://example.invalid/wheel.whl",
        )
        selected, _ = _select_sage_wheel(
            [wheel], (3, 12), "2.10.0", "12.6",
            "Windows", "AMD64", capability=(8, 9),
        )
        self.assertIsNone(selected)

    def test_sageattention_enforces_ada_cuda_12_4_minimum(self):
        wheel = _parse_sage_wheel(
            "sageattention-2.2.0+cu123torch210-cp312-cp312-win_amd64.whl",
            "https://example.invalid/wheel.whl",
        )
        selected, reason = _select_sage_wheel(
            [wheel], (3, 12), "2.10.0", "12.3",
            "Windows", "AMD64", capability=(8, 9),
        )
        self.assertIsNone(selected)
        self.assertIn("requires CUDA 12.4 or newer", reason)

    def test_sageattention_enforces_hopper_cuda_12_3_minimum(self):
        wheel = _parse_sage_wheel(
            "sageattention-2.2.0+cu123torch210-cp312-cp312-win_amd64.whl",
            "https://example.invalid/wheel.whl",
        )
        selected, reason = _select_sage_wheel(
            [wheel], (3, 12), "2.10.0", "12.2",
            "Windows", "AMD64", capability=(9, 0),
        )
        self.assertIsNone(selected)
        self.assertIn("requires CUDA 12.3 or newer", reason)

    def test_sageattention_enforces_blackwell_cuda_12_8_minimum(self):
        wheel = _parse_sage_wheel(
            "sageattention-2.2.0+cu128torch210-cp312-cp312-win_amd64.whl",
            "https://example.invalid/wheel.whl",
        )
        selected, reason = _select_sage_wheel(
            [wheel], (3, 12), "2.10.0", "12.6",
            "Windows", "AMD64", capability=(12, 1),
        )
        self.assertIsNone(selected)
        self.assertIn("requires CUDA 12.8 or newer", reason)

    def test_sageattention_linux_checks_glibc(self):
        wheel = _parse_sage_wheel(
            "sageattention-2.2.0+cu128torch210-cp312-cp312-manylinux_2_34_x86_64.whl",
            "https://example.invalid/wheel.whl",
        )
        selected, reason = _select_sage_wheel(
            [wheel], (3, 12), "2.10.0", "12.8",
            "Linux", "x86_64", glibc_version="2.31", capability=(8, 0),
        )
        self.assertIsNone(selected)
        self.assertIn("glibc 2.34", reason)
    def test_sageattention_rejects_unsupported_compute_capability(self):
        wheel = _parse_sage_wheel(
            "sageattention-2.2.0+cu128torch210-cp312-cp312-win_amd64.whl",
            "https://example.invalid/wheel.whl",
        )
        selected, reason = _select_sage_wheel(
            [wheel], (3, 12), "2.10.0", "12.8",
            "Windows", "AMD64", capability=(8, 5),
        )
        self.assertIsNone(selected)
        self.assertIn("support NVIDIA compute capabilities", reason)

    def test_sageattention_accepts_blackwell_compute_capability_12_1(self):
        wheel = _parse_sage_wheel(
            "sageattention-2.2.0+cu128torch210-cp312-cp312-win_amd64.whl",
            "https://example.invalid/wheel.whl",
        )
        selected, _ = _select_sage_wheel(
            [wheel], (3, 12), "2.10.0", "12.8",
            "Windows", "AMD64", capability=(12, 1),
        )
        self.assertIsNotNone(selected)

    def test_sageattention_rejects_cuda_11_even_if_a_matching_wheel_is_listed(self):
        wheel = _parse_sage_wheel(
            "sageattention-2.2.0+cu118torch210-cp312-cp312-win_amd64.whl",
            "https://example.invalid/wheel.whl",
        )
        selected, reason = _select_sage_wheel(
            [wheel], (3, 12), "2.10.0", "11.8",
            "Windows", "AMD64", capability=(8, 6),
        )
        self.assertIsNone(selected)
        self.assertIn("CUDA 12.0 or newer", reason)

    def test_environment_manager_is_not_an_automatic_workflow_output(self):
        self.assertFalse(PhantomGodEnvironmentManager.OUTPUT_NODE)

class SageAttentionPrerequisiteTests(unittest.TestCase):
    def test_wheel_is_not_installable_without_pytorch_matched_triton(self):
        wheel = {
            "version": "2.2.0+cu130torch214",
            "url": "https://example.invalid/sageattention.whl",
        }
        env = {
            "torch": "2.14.1+cu130",
            "cuda": "13.0",
            "cuda_available": True,
            "system": "Windows",
            "machine": "AMD64",
            "capability": [8, 6],
        }
        with patch("features.environment_manager._load_sage_wheels", return_value=([wheel], None)), patch("features.environment_manager._select_sage_wheel", return_value=(wheel, "Exact match")), patch("features.environment_manager._distribution_version", side_effect=lambda name: "2.2.0+cu130torch214" if name == "sageattention" else None), patch("features.environment_manager._safe_import_status", return_value=(True, None)):
            report = _sage_report(env)

        self.assertFalse(report["supported"])
        self.assertEqual(report["status"], "Prerequisite missing")
        self.assertFalse(report["triton_ready"])
        self.assertEqual(report["wheel_url"], wheel["url"])

    def test_sageattention_requires_the_expected_triton_minor(self):
        wheel = {
            "version": "2.2.0+cu130torch214",
            "url": "https://example.invalid/sageattention.whl",
        }
        env = {
            "torch": "2.14.1+cu130",
            "cuda": "13.0",
            "cuda_available": True,
            "system": "Windows",
            "machine": "AMD64",
            "capability": [8, 6],
        }
        def package_version(name):
            return {"sageattention": wheel["version"], "triton-windows": "3.7.1"}.get(name)
        with patch("features.environment_manager._load_sage_wheels", return_value=([wheel], None)), patch("features.environment_manager._select_sage_wheel", return_value=(wheel, "Exact match")), patch("features.environment_manager._distribution_version", side_effect=package_version), patch("features.environment_manager._safe_import_status", return_value=(True, None)):
            report = _sage_report(env)

        self.assertFalse(report["supported"])
        self.assertEqual(report["triton_target"], "3.8")
        self.assertEqual(report["triton_version"], "3.7.1")
        self.assertEqual(report["status"], "Prerequisite missing")

if __name__ == "__main__":
    unittest.main()
