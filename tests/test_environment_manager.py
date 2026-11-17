import unittest
from unittest.mock import patch

from features.environment_manager import (
    _parse_sage_wheel,
    _parse_torch_tag,
    _sage_report,
    _select_sage_wheel,
    _triton_target,
    PhantomGodEnvironmentManager,
    _version_sort_key,
)


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
        self.assertIn("compute capability 8.0", reason)

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
