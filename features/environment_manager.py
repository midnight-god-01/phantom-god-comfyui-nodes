"""ComfyUI environment checker and safe Triton/SageAttention installer."""

import asyncio
import html.parser
import importlib
import importlib.metadata
import importlib.util
import json
import platform
import re
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import unquote, urljoin
from urllib.request import Request, urlopen

SAGE_WHEEL_INDEX = "https://comfy-org.github.io/wheels/sageattention/"
TRITON_MINOR_MAP = {
    (2, 4): 1, (2, 5): 1, (2, 6): 2, (2, 7): 3,
    (2, 8): 4, (2, 9): 5, (2, 10): 6, (2, 11): 6,
    (2, 12): 7, (2, 13): 7, (2, 14): 8, (2, 15): 9,
}
TRITON_WINDOWS_MAP = {**TRITON_MINOR_MAP, (2, 15): 9}
# Official Triton release wheel Python ranges by Triton minor.
TRITON_PYTHON_BOUNDS = {
    1: ((3, 8), (3, 12)),
    2: ((3, 9), (3, 13)),
    3: ((3, 9), (3, 13)),
    4: ((3, 9), (3, 13)),
    5: ((3, 10), (3, 14)),
    6: ((3, 10), (3, 14)),
    7: ((3, 10), (3, 14)),
    8: ((3, 10), (3, 14)),
    9: ((3, 10), (3, 14)),
}
SAGE_SUPPORTED_COMPUTE_CAPABILITIES = {
    (8, 0), (8, 6), (8, 9), (9, 0), (10, 0), (12, 0), (12, 1),
}
SAGE_MIN_CUDA_BY_CAPABILITY = {
    (8, 0): (12, 0),
    (8, 6): (12, 0),
    (8, 9): (12, 4),
    (9, 0): (12, 3),
    (10, 0): (12, 8),
    (12, 0): (12, 8),
    (12, 1): (12, 8),
}
PYPI_INDEX = "https://pypi.org/pypi/{}/json"
INSTALL_TIMEOUT_SECONDS = 1800
_JOB_LOCK = threading.Lock()
_INSTALL_LOCK = threading.Lock()
_JOBS = {}
_ACTIVE_JOB = None
_INDEX_CACHE = {"time": 0.0, "wheels": None, "error": None}
_PYPI_CACHE = {}


def _parse_version_pair(value):
    """Return the first major/minor pair from a package version."""
    match = re.match(r"^\s*(\d+)\.(\d+)", str(value or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None


def _parse_cuda_tag(value):
    match = re.match(r"^\s*(\d+)\.(\d+)", str(value or ""))
    return match.group(1) + match.group(2) if match else None


def _parse_torch_tag(value):
    """Parse wheel tags such as torch29, torch210, and torch2.11."""
    value = str(value or "")
    dotted = re.fullmatch(r"(\d+)\.(\d+)", value)
    if dotted:
        return int(dotted.group(1)), int(dotted.group(2))
    compact = re.fullmatch(r"(\d)(\d+)", value)
    if compact:
        return int(compact.group(1)), int(compact.group(2))
    return None


def _triton_target(torch_version, system=None):
    """Return the PyTorch-matched Triton distribution and minor version."""
    torch_pair = _parse_version_pair(torch_version)
    if not torch_pair:
        return None
    system = system or platform.system()
    table = TRITON_WINDOWS_MAP if system == "Windows" else TRITON_MINOR_MAP
    minor = table.get(torch_pair)
    if minor is None:
        return None
    if system == "Windows":
        return {
            "distribution": "triton-windows",
            "import_name": "triton",
            "minor": minor,
            "spec": ">=3.{0},<3.{1}".format(minor, minor + 1),
            "package": "triton-windows",
        }
    if system == "Linux":
        return {
            "distribution": "triton",
            "import_name": "triton",
            "minor": minor,
            "spec": ">=3.{0},<3.{1}".format(minor, minor + 1),
            "package": "triton",
        }
    return None


class _WheelParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def _parse_sage_wheel(filename, url):
    """Decode environment tags embedded in a Comfy-Org SageAttention wheel."""
    match = re.match(
        r"^sageattention-(?P<version>.+?)-cp(?P<python>\d+)-cp(?P<abi>\d+)-(?P<platform>.+)\.whl$",
        filename,
        re.IGNORECASE,
    )
    if not match:
        return None
    version = match.group("version")
    local = re.search(r"\+cu(?P<cuda>\d+)torch(?P<torch>\d+(?:\.\d+)?)$", version)
    if not local:
        return None
    torch_pair = _parse_torch_tag(local.group("torch"))
    if not torch_pair:
        return None
    return {
        "filename": filename,
        "url": url,
        "version": version,
        "python_tag": match.group("python"),
        "abi_tag": match.group("abi"),
        "platform_tag": match.group("platform"),
        "cuda_tag": local.group("cuda"),
        "torch_pair": torch_pair,
    }


def _select_sage_wheel(wheels, python_version, torch_version, cuda_version,
                       system, machine, glibc_version=None, capability=None):
    """Choose only an exact Python/PyTorch/CUDA/platform wheel."""
    capability_pair = tuple(capability) if capability else None
    if capability_pair not in SAGE_SUPPORTED_COMPUTE_CAPABILITIES:
        supported = ", ".join("{}.{}".format(*item) for item in sorted(SAGE_SUPPORTED_COMPUTE_CAPABILITIES))
        return None, "SageAttention wheels support NVIDIA compute capabilities {} only; detected {}.".format(
            supported,
            "{}.{}".format(*capability_pair) if capability_pair else "no NVIDIA GPU",
        )
    torch_pair = _parse_version_pair(torch_version)
    cuda_tag = _parse_cuda_tag(cuda_version)
    if not torch_pair or not cuda_tag:
        return None, "A CUDA-enabled PyTorch build is required."
    cuda_pair = _parse_version_pair(cuda_version)
    if not cuda_pair or cuda_pair < (12, 0):
        return None, "SageAttention requires CUDA 12.0 or newer for its supported GPU kernels."
    minimum_cuda = SAGE_MIN_CUDA_BY_CAPABILITY[capability_pair]
    if cuda_pair < minimum_cuda:
        return None, (
            "SageAttention on compute capability {}.{} requires CUDA {}.{} or newer; detected {}."
            .format(
                capability_pair[0], capability_pair[1],
                minimum_cuda[0], minimum_cuda[1], cuda_version,
            )
        )
    if machine.lower() not in ("x86_64", "amd64"):
        return None, "The current Comfy-Org wheel index provides x86-64 builds only."
    py_tag = "{}{}".format(python_version[0], python_version[1])
    if system == "Windows":
        platform_ok = lambda tag: tag == "win_amd64"
    elif system == "Linux":
        glibc_pair = _parse_version_pair(glibc_version or "")
        if not glibc_pair or glibc_pair < (2, 34):
            return None, "Linux wheels require glibc 2.34 or newer."
        platform_ok = lambda tag: "manylinux_2_34_x86_64" in tag
    else:
        return None, "Prebuilt SageAttention wheels are currently provided for Windows and Linux x86-64."
    matching = [
        wheel for wheel in wheels
        if wheel["python_tag"] == py_tag
        and wheel["abi_tag"] == py_tag
        and wheel["torch_pair"] == torch_pair
        and wheel["cuda_tag"] == cuda_tag
        and platform_ok(wheel["platform_tag"])
    ]
    if not matching:
        return None, (
            "No prebuilt SageAttention wheel matches Python {}, PyTorch {}, CUDA {}, and {}."
            .format(python_version[0], torch_version, cuda_version, system)
        )
    matching.sort(
        key=lambda item: _version_sort_key(item["version"].split("+", 1)[0]),
        reverse=True,
    )
    return matching[0], "Exact Python/PyTorch/CUDA wheel match found."


def _load_sage_wheels(force=False):
    now = time.monotonic()
    if not force and _INDEX_CACHE["wheels"] is not None and now - _INDEX_CACHE["time"] < 600:
        return _INDEX_CACHE["wheels"], _INDEX_CACHE["error"]
    request = Request(SAGE_WHEEL_INDEX, headers={"User-Agent": "PhantomGod-ComfyUI-Nodes"})
    try:
        with urlopen(request, timeout=5) as response:
            page = response.read(4 * 1024 * 1024).decode("utf-8", "replace")
        parser = _WheelParser()
        parser.feed(page)
        wheels = []
        for href in parser.links:
            name = unquote(href.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1])
            if not name.lower().endswith(".whl"):
                continue
            parsed = _parse_sage_wheel(name, urljoin(SAGE_WHEEL_INDEX, href))
            if parsed:
                wheels.append(parsed)
        if not wheels:
            raise RuntimeError("The SageAttention wheel index did not return any supported wheel links.")
        _INDEX_CACHE.update({"time": now, "wheels": wheels, "error": None})
        return wheels, None
    except Exception as exc:
        _INDEX_CACHE.update({"time": now, "wheels": None, "error": str(exc)})
        return None, str(exc)


def _version_sort_key(value):
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", str(value))
    if not match:
        return (-1, -1, -1, -1)
    suffix = match.group(4)
    post = re.search(r"post(\d+)", suffix, re.IGNORECASE)
    return (
        int(match.group(1)), int(match.group(2)), int(match.group(3)),
        (1, int(post.group(1))) if post else (0, 0),
    )


def _latest_pypi_version(package, minor):
    """Find the latest published version in one compatible major/minor line."""
    cached = _PYPI_CACHE.get(package)
    if cached and time.monotonic() - cached["time"] < 600:
        releases = cached["releases"]
    else:
        request = Request(PYPI_INDEX.format(package), headers={"User-Agent": "PhantomGod-ComfyUI-Nodes"})
        with urlopen(request, timeout=4) as response:
            data = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
        releases = list(data.get("releases", {}).keys())
        _PYPI_CACHE[package] = {"time": time.monotonic(), "releases": releases}
    candidates = [
        version for version in releases
        if _parse_version_pair(version) == (3, minor)
        and not re.search(r"(a|b|rc|dev)\d*", version, re.IGNORECASE)
    ]
    return max(candidates, key=_version_sort_key) if candidates else None


def _distribution_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def _safe_import_status(module_name):
    try:
        importlib.invalidate_caches()
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            return False, "Python cannot find the module."
        module = importlib.import_module(module_name)
        return True, getattr(module, "__version__", None)
    except Exception as exc:
        return False, "{}: {}".format(type(exc).__name__, str(exc)[:500])


def _environment_details():
    details = {
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "pip_available": False,
        "pip_version": None,
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "torch": None,
        "cuda": None,
        "cuda_available": False,
        "hip": None,
        "gpu_name": None,
        "capability": None,
        "driver": None,
        "glibc": platform.libc_ver()[1] if platform.libc_ver()[0] == "glibc" else None,
        "error": None,
    }
    try:
        pip_result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if pip_result.returncode == 0:
            details["pip_available"] = True
            pip_tokens = (pip_result.stdout or "").strip().split()
            details["pip_version"] = pip_tokens[1] if len(pip_tokens) > 1 else "Available"
    except Exception:
        pass
    try:
        import torch
        details["torch"] = str(torch.__version__)
        details["cuda"] = getattr(torch.version, "cuda", None)
        details["hip"] = getattr(torch.version, "hip", None)
        details["cuda_available"] = bool(torch.cuda.is_available())
        if details["cuda_available"]:
            try:
                device = torch.cuda.current_device()
                props = torch.cuda.get_device_properties(device)
                details["gpu_name"] = str(props.name)
                details["capability"] = [int(props.major), int(props.minor)]
            except Exception as exc:
                details["error"] = "GPU query failed: {}".format(str(exc)[:400])
    except Exception as exc:
        details["error"] = "PyTorch import failed: {}: {}".format(type(exc).__name__, str(exc)[:400])
    if details["system"] == "Windows" or details["system"] == "Linux":
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            if result.returncode == 0:
                details["driver"] = result.stdout.strip().splitlines()[0][:80]
        except Exception:
            pass
    return details


def _triton_report(env):
    torch_version = env.get("torch")
    target = _triton_target(torch_version, env.get("system"))
    windows = env.get("system") == "Windows"
    legacy_version = _distribution_version("triton") if windows else None
    installed = _distribution_version("triton-windows" if windows else "triton")
    result = {
        "supported": False,
        "package": "triton-windows" if windows else "triton",
        "installed": installed,
        "target_minor": None,
        "latest": None,
        "status": "Not checked",
        "message": "",
        "import_ok": False,
        "import_detail": None,
    }
    if not torch_version:
        result.update(status="Blocked", message="PyTorch could not be imported in this ComfyUI environment.")
        return result
    if target is None:
        result.update(
            status="Compatibility unknown",
            message="No verified Triton/PyTorch version mapping is configured for PyTorch {} on {}."
                    .format(torch_version, env.get("system")),
        )
        return result
    result["target_minor"] = target["minor"]
    if env.get("system") not in ("Windows", "Linux"):
        result.update(status="Unsupported", message="Triton installation is configured for Windows and Linux only.")
        return result
    if env.get("machine", "").lower() not in ("x86_64", "amd64"):
        result.update(status="Unsupported", message="This Triton installer currently targets x86-64 environments.")
        return result
    if not env.get("cuda_available") or not env.get("cuda"):
        result.update(status="Blocked", message="A working CUDA-enabled NVIDIA PyTorch environment is required.")
        return result
    capability = env.get("capability") or [0, 0]
    if tuple(capability) < (7, 0):
        result.update(status="Unsupported GPU", message="The detected GPU is below the supported Triton architecture range.")
        return result
    if target["minor"] >= 3 and tuple(capability) < (8, 0):
        result.update(
            status="Unsupported GPU",
            message="Triton 3.{} is not supported on this GPU architecture; its compatible PyTorch mapping is retained."
                    .format(target["minor"]),
        )
        return result
    python_pair = _parse_version_pair(env.get("python") or platform.python_version())
    python_bounds = TRITON_PYTHON_BOUNDS.get(target["minor"])
    if not python_pair or not python_bounds:
        result.update(
            status="Compatibility unknown",
            message="The Python compatibility range for Triton 3.{} is not configured.".format(target["minor"]),
        )
        return result

    minimum_python, maximum_python = python_bounds
    if windows and target["minor"] == 9:
        # triton-windows 3.9 does not publish Python 3.10 wheels.
        minimum_python = (3, 11)
    if python_pair < minimum_python or python_pair > maximum_python:
        result.update(
            status="Unsupported Python",
            message=(
                "Triton 3.{} supports Python {}.{} through {}.{} on {}. "
                "This environment is Python {}.{}."
            ).format(
                target["minor"],
                minimum_python[0], minimum_python[1],
                maximum_python[0], maximum_python[1],
                "Windows" if windows else "Linux",
                python_pair[0], python_pair[1],
            ),
        )
        return result

    result["supported"] = True
    try:
        latest = _latest_pypi_version(target["package"], target["minor"])
        result["latest"] = latest
    except Exception as exc:
        result["latest_error"] = str(exc)[:250]

    install_status = "Not installed"
    install_message = "Compatible Triton 3.{} is available for this PyTorch environment.".format(target["minor"])
    if installed:
        installed_pair = _parse_version_pair(installed)
        if installed_pair != (3, target["minor"]):
            install_status = "Update required"
            install_message = "Installed Triton {} does not match PyTorch's compatible 3.{} line.".format(installed, target["minor"])
        elif result["latest"] and _version_sort_key(installed) < _version_sort_key(result["latest"]):
            install_status = "Update available"
            install_message = "Triton {} is installed; {} is the latest published build in the compatible 3.{} line.".format(installed, result["latest"], target["minor"])
        elif not result["latest"]:
            install_status = "Compatible"
            install_message = "Installed Triton matches PyTorch's compatible 3.{} line; latest patch could not be confirmed online.".format(target["minor"])
        else:
            install_status = "Up to date"
            install_message = "Installed Triton matches the latest published build in the compatible 3.{} line.".format(target["minor"])

    if windows and legacy_version:
        coexist = " alongside triton-windows" if installed else ""
        result.update(
            status="Package conflict",
            message=(
                "Legacy 'triton' {} is installed{}. The Windows build uses "
                "'triton-windows'; the installer will remove the conflicting "
                "legacy distribution. Current triton-windows state: {} — {}"
            ).format(legacy_version, coexist, install_status, install_message),
        )
    else:
        result.update(status=install_status, message=install_message)

    result["import_ok"], result["import_detail"] = _safe_import_status("triton") if installed else (False, None)
    if installed and not result["import_ok"]:
        if result["status"] == "Package conflict":
            result["message"] += " The installed Triton module also fails to import: {}.".format(result["import_detail"])
        else:
            result["status"] = "Import failed"
            result["message"] = "Triton is installed but cannot be imported: {}".format(result["import_detail"])
    return result


    try:
        latest = _latest_pypi_version(target["package"], target["minor"])
        result["latest"] = latest
    except Exception as exc:
        result["latest_error"] = str(exc)[:250]
    if installed:
        installed_pair = _parse_version_pair(installed)
        if installed_pair != (3, target["minor"]):
            result.update(status="Update required", message="Installed Triton {} does not match PyTorch's compatible 3.{} line."
                          .format(installed, target["minor"]))
        elif result["latest"] and _version_sort_key(installed) < _version_sort_key(result["latest"]):
            result.update(status="Update available", message="Triton {} is installed; {} is the latest published build in the compatible 3.{} line."
                          .format(installed, result["latest"], target["minor"]))
        elif not result["latest"]:
            result.update(status="Compatible", message="Installed Triton matches PyTorch's compatible 3.{} line; latest patch could not be confirmed online."
                          .format(target["minor"]))
        else:
            result.update(status="Up to date", message="Installed Triton matches the latest published build in the compatible 3.{} line."
                          .format(target["minor"]))
    else:
        result.update(status="Not installed", message="Compatible Triton 3.{} is available for this PyTorch environment."
                      .format(target["minor"]))
    result["import_ok"], result["import_detail"] = _safe_import_status("triton") if installed else (False, None)
    if installed and not result["import_ok"]:
        result["status"] = "Import failed"
        result["message"] = "Triton is installed but cannot be imported: {}".format(result["import_detail"])
    return result


def _sage_report(env):
    installed = _distribution_version("sageattention")
    result = {
        "supported": False,
        "installed": installed,
        "target_version": None,
        "wheel_url": None,
        "status": "Not checked",
        "message": "",
        "import_ok": False,
        "import_detail": None,
        "triton_ready": False,
        "triton_version": None,
    }
    if not env.get("torch"):
        result.update(status="Blocked", message="PyTorch could not be imported in this ComfyUI environment.")
        return result
    if not env.get("cuda_available") or not env.get("cuda"):
        result.update(status="Blocked", message="A working CUDA-enabled NVIDIA PyTorch environment is required.")
        return result

    wheels, index_error = _load_sage_wheels()
    if wheels is None:
        result.update(
            status="Index unavailable",
            message="Could not check the official Comfy-Org wheel index: {}".format(index_error or "network unavailable"),
        )
        return result
    wheel, reason = _select_sage_wheel(
        wheels, sys.version_info[:2], env["torch"], env["cuda"],
        env["system"], env["machine"], env.get("glibc"), env.get("capability"),
    )
    if wheel is None:
        result.update(status="Unsupported combination", message=reason)
        return result

    result["target_version"] = wheel["version"]
    result["wheel_url"] = wheel["url"]

    # SageAttention requires Triton, and Triton must match this exact PyTorch
    # minor. Merely finding any Triton >= 3.0 can still leave torch.compile
    # with an incompatible backend.
    triton_target = _triton_target(env["torch"], env["system"])
    triton_distribution = triton_target["distribution"] if triton_target else None
    triton_version = _distribution_version(triton_distribution) if triton_distribution else None
    legacy_windows_triton = (
        _distribution_version("triton") if env.get("system") == "Windows" else None
    )
    triton_import_ok, triton_import_detail = (
        _safe_import_status("triton") if triton_version else (False, "The PyTorch-compatible Triton package is not installed.")
    )
    triton_ready = bool(
        triton_target
        and triton_version
        and _parse_version_pair(triton_version) == (3, triton_target["minor"])
        and triton_import_ok
        and not legacy_windows_triton
    )
    result["triton_version"] = triton_version
    result["triton_target"] = ("3.{}".format(triton_target["minor"]) if triton_target else None)
    result["triton_ready"] = triton_ready

    if installed:
        result["import_ok"], result["import_detail"] = _safe_import_status("sageattention")

    if not triton_ready:
        detail = (
            "Conflicting legacy 'triton' {} distribution is installed on Windows.".format(legacy_windows_triton)
            if legacy_windows_triton
            else triton_import_detail or "The installed Triton version does not match the active PyTorch compatibility line."
        )
        result.update(
            supported=False,
            status="Prerequisite missing",
            message="A working, PyTorch-matched Triton build is required before SageAttention can be installed or used.",
            triton_note=detail,
        )
        return result

    result["supported"] = True
    if installed == wheel["version"] and result["import_ok"]:
        result.update(status="Up to date", message="Installed SageAttention wheel matches this Python/PyTorch/CUDA environment and imports successfully.")
    elif installed == wheel["version"]:
        result.update(status="Import failed", message="The matching SageAttention package is installed but cannot be imported: {}".format(result["import_detail"]))
    elif installed:
        result.update(
            status="Update or repair available",
            message="Installed SageAttention {} differs from the matching wheel {}.".format(installed, wheel["version"]),
        )
    else:
        result.update(status="Not installed", message=reason)
    return result

def build_environment_report():
    """Collect Python, PyTorch, CUDA, GPU and package compatibility information."""
    env = _environment_details()
    triton = _triton_report(env)
    sage = _sage_report(env)
    return {
        "environment": env,
        "triton": triton,
        "sageattention": sage,
        "restart_required_after_install": True,
    }


def _set_job(job_id, **changes):
    with _JOB_LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(changes)


def _run_pip(command):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=INSTALL_TIMEOUT_SECONDS,
        check=False,
    )


def _install_worker(job_id, package):
    global _ACTIVE_JOB
    try:
        with _INSTALL_LOCK:
            _set_job(job_id, state="running", message="Checking compatibility and preparing the installation.")
            report = build_environment_report()
            if not report["environment"].get("pip_available"):
                raise RuntimeError(
                    "pip is not available in the active ComfyUI Python. "
                    "Install pip into this interpreter (for example, python -m ensurepip) and run Check again."
                )
            info = report.get(package) or {}
            if not info.get("supported"):
                raise RuntimeError(info.get("message") or "This package is not supported in the current environment.")
            if package == "triton":
                target = _triton_target(report["environment"]["torch"], report["environment"]["system"])
                if not target:
                    raise RuntimeError("No compatible Triton version was found.")
                if report["environment"]["system"] == "Windows" and _distribution_version("triton"):
                    old_version = _distribution_version("triton")
                    _set_job(job_id, message="Removing the conflicting legacy Triton package before installing triton-windows.")
                    remove = _run_pip([sys.executable, "-m", "pip", "uninstall", "-y", "triton"])
                    if remove.returncode != 0:
                        raise RuntimeError("Could not remove the conflicting triton package: " + (remove.stderr or remove.stdout)[-3000:])
                    spec = target["spec"]
                    command = [
                        sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                        "--no-deps", "--only-binary=:all:", "--upgrade",
                        target["package"] + spec,
                    ]
                    _set_job(job_id, message="Installing the PyTorch-matched Windows Triton build.")
                    result = _run_pip(command)
                    if result.returncode != 0:
                        rollback = _run_pip([
                            sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                            "--no-deps", "--only-binary=:all:", "triton==" + old_version,
                        ])
                        if rollback.returncode == 0:
                            raise RuntimeError("Triton Windows installation failed. The previous Triton {} package was restored. {}".format(old_version, (result.stderr or result.stdout)[-3000:]))
                        raise RuntimeError("Triton Windows installation failed and automatic rollback failed. Previous version: {}. Install error: {}. Rollback error: {}".format(old_version, (result.stderr or result.stdout)[-1500:], (rollback.stderr or rollback.stdout)[-1500:]))
                else:
                    command = [
                        sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                        "--no-deps", "--only-binary=:all:", "--upgrade",
                        target["package"] + target["spec"],
                    ]
                    _set_job(job_id, message="Installing the PyTorch-matched Triton build.")
                    result = _run_pip(command)
                    if result.returncode != 0:
                        raise RuntimeError((result.stderr or result.stdout or "pip installation failed")[-5000:])
            elif package == "sageattention":
                wheel_url = info.get("wheel_url")
                if not wheel_url:
                    raise RuntimeError("No exact matching SageAttention wheel is available.")
                command = [
                    sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "--no-deps", "--only-binary=:all:", "--upgrade", "--force-reinstall",
                    wheel_url,
                ]
                _set_job(job_id, message="Installing the SageAttention wheel built for this Python/PyTorch/CUDA combination.")
                result = _run_pip(command)
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or result.stdout or "pip installation failed")[-5000:])
            else:
                raise RuntimeError("Unknown package selection.")
            output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            _set_job(
                job_id,
                state="completed",
                message="Installation completed. Restart ComfyUI before testing the package.",
                output=output[-12000:],
                finished=time.time(),
                restart_required=True,
            )
    except subprocess.TimeoutExpired as exc:
        _set_job(job_id, state="failed", message="pip installation timed out after 30 minutes.", output=str(exc)[-2000:], finished=time.time())
    except Exception as exc:
        _set_job(job_id, state="failed", message=str(exc)[:5000], finished=time.time())
    finally:
        with _JOB_LOCK:
            if _ACTIVE_JOB == job_id:
                _ACTIVE_JOB = None


async def _check_route(request):
    from aiohttp import web
    try:
        report = await asyncio.to_thread(build_environment_report)
        return web.json_response(report)
    except Exception as exc:
        return web.json_response({"error": str(exc)[:1000]}, status=500)


async def _install_route(request):
    from aiohttp import web
    global _ACTIVE_JOB
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Expected JSON request body."}, status=400)
    package = data.get("package") if isinstance(data, dict) else None
    if package not in ("triton", "sageattention"):
        return web.json_response({"error": "Package must be 'triton' or 'sageattention'."}, status=400)
    with _JOB_LOCK:
        if _ACTIVE_JOB and _JOBS.get(_ACTIVE_JOB, {}).get("state") in ("queued", "running"):
            return web.json_response({"error": "Another Phantom God package installation is already running."}, status=409)
        job_id = uuid.uuid4().hex
        _ACTIVE_JOB = job_id
        _JOBS[job_id] = {
            "job_id": job_id,
            "package": package,
            "state": "queued",
            "message": "Installation queued.",
            "output": "",
            "started": time.time(),
            "finished": None,
            "restart_required": False,
        }
    threading.Thread(target=_install_worker, args=(job_id, package), daemon=True).start()
    return web.json_response({"job_id": job_id, "state": "queued"})


async def _job_route(request):
    from aiohttp import web
    job_id = request.match_info.get("job_id", "")
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        if job:
            job = dict(job)
    if not job:
        return web.json_response({"error": "Installation job not found."}, status=404)
    return web.json_response(job)


def register_routes():
    """Register local ComfyUI routes once when the server is available."""
    try:
        from server import PromptServer
        server = PromptServer.instance
        if server is None or getattr(server, "_phantom_god_environment_routes", False):
            return
        server.routes.post("/phantom_god/environment/check")(_check_route)
        server.routes.post("/phantom_god/environment/install")(_install_route)
        server.routes.get("/phantom_god/environment/job/{job_id}")(_job_route)
        server._phantom_god_environment_routes = True
    except Exception as exc:
        print("[Phantom God] Environment Manager routes could not be registered: {}".format(exc))


class PhantomGodEnvironmentManager:
    """Inspect the active ComfyUI environment and manage Triton/SageAttention."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("environment_report",)
    FUNCTION = "check_environment"
    CATEGORY = "Phantom God/System"
    # This is a utility node, not a workflow sink. Its UI has explicit Check
    # actions; do not run the environment/network checks on every queued prompt.
    OUTPUT_NODE = False
    DESCRIPTION = (
        "Check the Python, PyTorch, CUDA and GPU environment. Install or update "
        "Triton and SageAttention independently using environment-matched wheels. "
        "The installer never upgrades PyTorch or its dependencies."
    )

    def check_environment(self):
        report = build_environment_report()
        return (json.dumps(report, indent=2, sort_keys=True),)


NODE_CLASS_MAPPINGS = {
    "PhantomGodEnvironmentManager": PhantomGodEnvironmentManager,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PhantomGodEnvironmentManager": "Environment Manager (Phantom God)",
}

register_routes()
