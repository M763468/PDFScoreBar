"""First-run user setup of the Windows portable folder (#553).

Some runtime components are not shipped in the folder: the recipient downloads them once,
directly from their official distribution channel, with ``PDFScoreBar.cmd setup``.

* ``triton-windows`` (PyPI) is needed by ``torch.compile`` (production SR,
  ``sr_compile_mode: reduce-overhead``). Its wheel carries NVIDIA CUDA components
  (``ptxas.exe``, ``cuda.h``, ``cuda.lib``) whose redistribution by us on Windows is not
  established by the CUDA EULA's Attachment A, and TinyCC (LGPL-2.1). Installing the
  wheel from PyPI keeps those files out of what we hand over while keeping Triton.
* ``torch/lib/nvperf_host.dll`` and ``torch/lib/cusolverMg64_11.dll`` (NVIDIA, also not
  listed for Windows) and OpenCV's FFmpeg video plugins (LGPL-2.1) are removed at build
  time: nothing PDFScoreBar runs loads them (``SETUP_SPEC["build_exclusions"]``).

The packages are installed with the bundled interpreter's own pip into
``<root>/addons/site-packages``, outside ``python/`` and outside the build manifest, and
reach ``sys.path`` through the shipped ``python/Lib/site-packages/pdfscorebar_addons.pth``
(a relative line, so the folder stays relocatable). Nothing is written outside the
folder; no administrator rights or system Python are used.

Installation is staged and swapped in only after the package imports (and, by default,
after a small ``torch.compile`` GPU smoke test), so a failed or interrupted setup leaves a
previous installation untouched and can simply be re-run. Downloaded wheels are kept in
``addons/downloads`` and reused; setup never upgrades on its own. Version pins are
compatibility choices (the combination validated on Windows), not byte pins: the record
keeps package names, versions, wheel names, sources and local file digests for diagnosis,
and ``verify --full`` re-hashes the installed add-on files. Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath

SETUP_SCHEMA = "pdfscore.windows_portable.user_setup.v1"
STATE_SCHEMA = "pdfscore.windows_portable.user_setup_state.v1"
ADDONS = "addons"
ADDONS_SITE = f"{ADDONS}/site-packages"
DOWNLOADS = f"{ADDONS}/downloads"
STATE = f"{ADDONS}/setup_state.json"
STAGING = f"{ADDONS}/.staging"
PREVIOUS = f"{ADDONS}/.previous"
# Shipped in python/ by the builder; relative to python/Lib/site-packages.
PTH_PATH = "python/Lib/site-packages/pdfscorebar_addons.pth"
PTH_LINE = "../../../addons/site-packages"

SETUP_SPEC: dict = {
    "schema_version": SETUP_SCHEMA,
    "index_url": "https://pypi.org/simple",
    "packages": [
        {
            "name": "triton-windows",
            "version": "3.8.0.post29",
            "import": "triton",
            "project_url": "https://pypi.org/project/triton-windows/",
            "purpose": "torch.compile (reduce-overhead) of the production super-resolution step",
            "terms": (
                "triton-windows is MIT-licensed. Its wheel contains NVIDIA CUDA components "
                "(ptxas.exe, cuda.h, cuda.lib; NVIDIA CUDA Toolkit EULA) and TinyCC "
                "(LGPL-2.1), as distributed by the triton-windows project on PyPI."
            ),
            "required_files": [
                "triton/__init__.py",
                "triton/backends/nvidia/bin/ptxas.exe",
                "triton/backends/nvidia/include/cuda.h",
                "triton/backends/nvidia/lib/x64/cuda.lib",
                "triton/runtime/tcc/tcc.exe",
            ],
        }
    ],
    "build_exclusions": [
        {
            "path": "torch/lib/nvperf_host.dll",
            "reason": (
                "Nsight Perf SDK host library; only CUPTI's profiler range API loads it. Not "
                "listed as a Windows redistributable; unused by inference"
            ),
        },
        {
            "path": "torch/lib/cusolverMg64_11.dll",
            "reason": (
                "multi-GPU cuSOLVER; no torch library references it. Not listed as a "
                "Windows redistributable; unused by inference"
            ),
        },
        {
            "path": "cv2/opencv_videoio_ffmpeg4110_64.dll",
            "reason": (
                "FFmpeg (LGPL-2.1) video I/O plugin of opencv-python, loaded only by "
                "cv2.VideoCapture/VideoWriter, which neither PDFScoreBar nor HOMR uses"
            ),
        },
        {
            "path": "cv2/opencv_videoio_ffmpeg4140_64.dll",
            "reason": ("the same FFmpeg plugin left by opencv-python-headless; unused as above"),
        },
    ],
}

GPU_SMOKE = r"""
import torch, triton
assert torch.cuda.is_available(), "No CUDA GPU is visible to PyTorch"
fn = torch.compile(lambda x: torch.relu(x * 2.0 + 1.0))
x = torch.linspace(-4.0, 4.0, 4096, device="cuda")
y = fn(x)
torch.cuda.synchronize()
assert torch.equal(y, torch.relu(x * 2.0 + 1.0)), "compiled result differs"
print(triton.__version__)
"""


class SetupError(RuntimeError):
    pass


def spec_digest(spec: dict = SETUP_SPEC) -> str:
    payload = json.dumps(spec["packages"], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wheel_prefix(name: str, version: str) -> str:
    return f"{re.sub(r'[-_.]+', '_', name).lower()}-{version}-"


def find_wheel(directory: Path, package: dict) -> Path | None:
    if not directory.is_dir():
        return None
    prefix = wheel_prefix(package["name"], package["version"])
    found = sorted(
        p for p in directory.iterdir() if p.is_file() and p.name.lower().startswith(prefix)
    )
    found = [p for p in found if p.suffix == ".whl"]
    return found[0] if found else None


def load_state(root: Path) -> dict | None:
    path = root / STATE
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SetupError(f"Setup record is unreadable: {error}") from error
    if not isinstance(state, dict) or state.get("schema_version") != STATE_SCHEMA:
        raise SetupError("Setup record has an unsupported format; run setup --force")
    return state


def addons_problems(root: Path, *, full: bool = False, required: bool = True) -> list[str]:
    """Problems with the user-installed add-ons. Quick: presence and sizes; full: digests."""

    if not (root / PTH_PATH).is_file():
        return [f"missing add-on path file: {PTH_PATH}"]
    try:
        state = load_state(root)
    except SetupError as error:
        return [str(error)]
    if state is None:
        return (
            [
                "First-run setup is not completed: run 'PDFScoreBar.cmd setup' (downloads "
                "triton-windows from PyPI once)"
            ]
            if required
            else []
        )
    problems = []
    if state.get("spec_sha256") != spec_digest():
        problems.append(
            "Installed add-ons do not match this PDFScoreBar version: run 'PDFScoreBar.cmd "
            "setup --force'"
        )
    site = root / ADDONS_SITE
    files = state.get("files", {})
    for package in SETUP_SPEC["packages"]:
        for name in package["required_files"]:
            if name not in files:
                problems.append(f"add-on record lacks required file: {name}")
    for name, (size, digest) in sorted(files.items()):
        path = site / PurePosixPath(name)
        if not path.is_file():
            problems.append(f"add-on file missing: {name}")
        elif path.stat().st_size != size:
            problems.append(f"add-on size mismatch: {name}")
        elif full and sha256_file(path) != digest:
            problems.append(f"add-on sha256 mismatch: {name}")
    return problems


def status(root: Path) -> dict:
    try:
        state = load_state(root)
    except SetupError as error:
        return {"completed": False, "error": str(error)}
    if state is None:
        return {"completed": False}
    return {
        "completed": True,
        "completed_at": state.get("completed_at"),
        "packages": [
            {k: p.get(k) for k in ("name", "version", "wheel", "source")}
            for p in state.get("packages", [])
        ],
    }


def _record_files(site: Path) -> dict[str, list]:
    return {
        path.relative_to(site).as_posix(): [path.stat().st_size, sha256_file(path)]
        for path in sorted(site.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def _recover(root: Path) -> None:
    """Undo an interrupted swap and drop leftovers of an interrupted setup."""

    site, previous, staging = root / ADDONS_SITE, root / PREVIOUS, root / STAGING
    if previous.is_dir():
        if site.exists():
            shutil.rmtree(previous)
        else:
            previous.rename(site)
    if staging.exists():
        shutil.rmtree(staging)


Runner = Callable[..., subprocess.CompletedProcess]


def _run(runner: Runner, command: list[str], env: dict[str, str], what: str) -> str:
    completed = runner(command, env=env, capture_output=True, text=True)
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip()[-1500:]
        raise SetupError(f"{what} failed (exit {completed.returncode}):\n{tail}")
    return completed.stdout or ""


def notice(spec: dict = SETUP_SPEC) -> str:
    lines = [
        "PDFScoreBar first-run setup",
        "",
        "The following package is downloaded once from its official distribution channel",
        f"({spec['index_url']}) and installed into this folder only (addons\\):",
        "",
    ]
    for package in spec["packages"]:
        lines += [
            f"  {package['name']} {package['version']}  ({package['project_url']})",
            f"    used for: {package['purpose']}",
            f"    terms: {package['terms']}",
        ]
    lines += [
        "",
        "By continuing you obtain these files directly from that source and accept their",
        "license terms. Nothing is installed system-wide; administrator rights are not used.",
    ]
    return "\n".join(lines)


def run_setup(
    root: Path,
    python: Path,
    *,
    env: dict[str, str],
    assume_yes: bool = False,
    force: bool = False,
    wheel_dir: Path | None = None,
    gpu_smoke: bool = True,
    runner: Runner = subprocess.run,
    confirm: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
) -> dict:
    """Install the add-ons. Returns the setup status; raises SetupError on failure."""

    addons = root / ADDONS
    addons.mkdir(parents=True, exist_ok=True)
    _recover(root)
    if not force and not addons_problems(root, full=False):
        out("Setup is already completed; nothing to download (use --force to reinstall).")
        return status(root)
    out(notice())
    if not assume_yes and confirm("Continue? [y/N] ").strip().lower() not in {"y", "yes"}:
        raise SetupError("Setup cancelled; nothing was changed")

    downloads, staging = root / DOWNLOADS, root / STAGING
    downloads.mkdir(parents=True, exist_ok=True)
    target = staging / "site-packages"
    target.mkdir(parents=True)
    pip_env = {k: v for k, v in env.items() if not k.upper().startswith("PIP_")}
    pip_env["PYTHONNOUSERSITE"] = "1"
    pip = [str(python), "-m", "pip", "--isolated", "--disable-pip-version-check"]
    records = []
    try:
        for package in SETUP_SPEC["packages"]:
            requirement = f"{package['name']}=={package['version']}"
            wheel = find_wheel(downloads, package)
            source = "downloads"
            if wheel is None and wheel_dir is not None:
                provided = find_wheel(wheel_dir, package)
                if provided is None:
                    raise SetupError(f"No {requirement} wheel in {wheel_dir}")
                wheel = downloads / provided.name
                shutil.copyfile(provided, wheel)
                source = "wheel-dir"
            if wheel is None:
                out(f"Downloading {requirement} from {SETUP_SPEC['index_url']} ...")
                fetched = staging / "download"
                fetched.mkdir()
                _run(
                    runner,
                    [
                        *pip,
                        "download",
                        "--no-deps",
                        "--only-binary=:all:",
                        "--index-url",
                        SETUP_SPEC["index_url"],
                        "--cache-dir",
                        str(staging / "pip-cache"),
                        "--dest",
                        str(fetched),
                        requirement,
                    ],
                    pip_env,
                    f"Download of {requirement}",
                )
                got = find_wheel(fetched, package)
                if got is None:
                    raise SetupError(f"pip did not download a {requirement} wheel")
                wheel = downloads / got.name
                shutil.move(str(got), wheel)
                source = SETUP_SPEC["index_url"]
            out(f"Installing {wheel.name} ...")
            _run(
                runner,
                [
                    *pip,
                    "install",
                    "--no-deps",
                    "--no-index",
                    "--no-compile",
                    "--target",
                    str(target),
                    str(wheel),
                ],
                pip_env,
                f"Installation of {wheel.name}",
            )
            records.append(
                {
                    "name": package["name"],
                    "version": package["version"],
                    "wheel": wheel.name,
                    "wheel_sha256": sha256_file(wheel),
                    "source": source,
                }
            )
        # pip --target puts console-script launchers (absolute interpreter paths) in bin/.
        shutil.rmtree(target / "bin", ignore_errors=True)
        shutil.rmtree(target / "Scripts", ignore_errors=True)
        for package in SETUP_SPEC["packages"]:
            missing = [n for n in package["required_files"] if not (target / n).is_file()]
            if missing:
                raise SetupError(f"{package['name']} wheel lacks required files: {missing}")
        smoke_env = dict(env)
        smoke_env["PYTHONPATH"] = os.pathsep.join(
            [str(target), *filter(None, [env.get("PYTHONPATH")])]
        )
        modules = [p["import"] for p in SETUP_SPEC["packages"]]
        probe = (
            "import importlib, json, pathlib, sys\n"
            f"mods = {modules!r}\n"
            "print(json.dumps({m: str(pathlib.Path(importlib.import_module(m).__file__))"
            " for m in mods}))\n"
        )
        located = json.loads(
            _run(runner, [str(python), "-c", probe], smoke_env, "Import check").splitlines()[-1]
        )
        for module, location in located.items():
            if not Path(location).resolve().is_relative_to(target.resolve()):
                raise SetupError(f"{module} was imported from {location}, not from the add-ons")
        if gpu_smoke:
            out("Checking torch.compile with Triton on the GPU (first run takes a while) ...")
            _run(runner, [str(python), "-c", GPU_SMOKE], smoke_env, "GPU compile check")
        files = _record_files(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    site, previous = root / ADDONS_SITE, root / PREVIOUS
    if site.exists():
        site.rename(previous)
    target.rename(site)
    state = {
        "schema_version": STATE_SCHEMA,
        "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "spec_sha256": spec_digest(),
        "index_url": SETUP_SPEC["index_url"],
        "python": sys.version.split()[0],
        "gpu_smoke": gpu_smoke,
        "packages": records,
        "files": files,
    }
    temporary = root / (STATE + ".tmp")
    temporary.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    os.replace(temporary, root / STATE)
    _recover(root)
    problems = addons_problems(root, full=False)
    if problems:
        raise SetupError("Setup finished but the add-ons do not check:\n" + "\n".join(problems))
    out("Setup completed.")
    return status(root)
