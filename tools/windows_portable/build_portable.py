"""Build a Docker-free Windows portable folder from one source commit (#535).

Run on Windows from a clean PDFScoreBar checkout of the commit, with Python >= 3.11, Git
and uv on PATH:

    python tools\\windows_portable\\build_portable.py --output C:\\pb\\PDFScoreBar ^
        --asset-source C:\\staged-assets --commit <40-hex sha> [--cache C:\\pb-cache]

The folder is assembled only from pinned inputs: the main minimal-distribution
application selected by ``docs/MINIMAL_MAINLINE_SURFACE.json`` and read as Git blobs of
the commit (``app/``, #551; see ``payload.py``), the Windows-only allowlist of
``overlay.json`` (``launcher/`` and ``PDFScoreBar.cmd``), a uv-managed CPython,
``requirements-cu126.txt``, the HOMR commit of the Dockerfile, the first-party SR weights
of the application (``models/sr_x4``, #533) and the hash-pinned assets of ``assets.json``.
The running builder must equal the commit's builder files. As in the Dockerfile, HOMR is
initialized SegNet-only and the build fails if basicsr/realesrgan/gfpgan/facexlib or a
HOMR transformer checkpoint is present (#533/#536). Every input is checked, the
installed distribution set must equal the lock, and ``runtime/build_manifest.json``
records the provenance plus size/SHA-256 of every runtime file (including native
DLLs) so ``PDFScoreBar.cmd verify --full`` can re-check the folder anywhere.

Building is not permission to distribute: see tools/windows_portable/README.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import payload  # noqa: E402
from manifest import (  # noqa: E402
    APP_ROOT,
    MANIFEST_PATH,
    MANIFEST_SCHEMA,
    MARKERS_ROOT,
    build_inventory,
    check_contract,
    sha256_file,
    tree_digest,
    verify,
)
from materialize_distribution import check_tree  # noqa: E402

CPYTHON_VERSION = "3.12.12"
TORCH_INDEX = "https://download.pytorch.org/whl/cu126"
HOMR_COMMIT = "457e7c6518a10ba755db2e60883419e56c4d7369"
ORT_GPU = "onnxruntime-gpu==1.24.4"
OPENCV = "opencv-python==4.11.0.86"
# Replaced by the pinned commit's copies (written to the build cache) in build().
LOCK = HERE / "requirements-cu126.txt"
ASSETS = HERE / "assets.json"
# Build tooling that is not part of the runtime lock.
UNLOCKED = {"pip", "setuptools", "wheel", "homr"}
# Same exclusion as the Dockerfile and docker/runtime_contract.py (#533/#536).
EXCLUDED_DISTRIBUTIONS = ("basicsr", "realesrgan", "gfpgan", "facexlib")


def log(message: str) -> None:
    print(f"[build] {message}", flush=True)


def run(command: list[str], *, env: dict[str, str], cwd: Path | None = None) -> str:
    log(" ".join(command))
    completed = subprocess.run(
        command, env=env, cwd=cwd, check=True, text=True, capture_output=True
    )
    return completed.stdout


def git(*args: str, repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, text=True, capture_output=True
    ).stdout.strip()


def read_lock() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, version = line.split("==", 1)
            pins[canonical(name)] = version
    return pins


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def installed_distributions(site_packages: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for meta in site_packages.glob("*.dist-info/METADATA"):
        text = meta.read_text(encoding="utf-8", errors="replace")
        name = re.search(r"^Name: (.+)$", text, re.M)
        version = re.search(r"^Version: (.+)$", text, re.M)
        if name and version:
            found[canonical(name.group(1).strip())] = version.group(1).strip()
    return found


def pin_build_inputs(snap: payload.Snapshot, cache: Path) -> None:
    """Use the lock and asset list of the pinned commit, never the working tree."""

    global LOCK, ASSETS
    inputs = cache / "inputs" / snap.commit
    for relative, data in snap.inputs.items():
        target = inputs / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    LOCK, ASSETS = inputs / payload.LOCK, inputs / payload.ASSETS


def install_cpython(target: Path, *, env: dict[str, str], cache: Path) -> Path:
    install_dir = cache / "python"
    run(
        ["uv", "python", "install", CPYTHON_VERSION, "--install-dir", str(install_dir)],
        env=env,
    )
    candidates = sorted(install_dir.glob(f"cpython-{CPYTHON_VERSION}-windows-x86_64-*"))
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one CPython {CPYTHON_VERSION} install, found {candidates}")
    shutil.copytree(candidates[0], target)
    # The private copy is owned by this folder; uv's marker would refuse installs.
    for marker in target.rglob("EXTERNALLY-MANAGED"):
        marker.unlink()
    python = target / "python.exe"
    version = run([str(python), "-c", "import platform;print(platform.python_version())"], env=env)
    if version.strip() != CPYTHON_VERSION:
        raise RuntimeError(f"Bundled CPython version mismatch: {version.strip()}")
    return python


def install_packages(python: Path, *, env: dict[str, str]) -> None:
    pip = ["uv", "pip", "install", "--python", str(python), "--link-mode", "copy"]
    torch_index = ["--extra-index-url", TORCH_INDEX, "--index-strategy", "unsafe-best-match"]
    lock = ["-c", str(LOCK)]
    lock_pins = read_lock()
    torch = f"torch=={lock_pins['torch']}"
    torchvision = f"torchvision=={lock_pins['torchvision']}"
    # Same order and pins as the Dockerfile; only the CUDA wheel flavour differs.
    run([*pip, *torch_index, *lock, torch, torchvision], env=env)
    run(
        [*pip, *torch_index, *lock, f"git+https://github.com/liebharc/homr.git@{HOMR_COMMIT}"],
        env=env,
    )
    commit = run(
        [
            str(python),
            "-c",
            "import importlib.metadata as m, json;"
            "print(json.loads(m.distribution('homr').read_text('direct_url.json'))"
            "['vcs_info']['commit_id'])",
        ],
        env=env,
    ).strip()
    if commit != HOMR_COMMIT:
        raise RuntimeError(f"homr commit mismatch: {commit}")
    run([*pip, *torch_index, *lock, ORT_GPU], env=env)
    run([*pip, *torch_index, "-r", str(LOCK)], env=env)
    run([*pip, "--force-reinstall", "--no-deps", OPENCV], env=env)
    run(["uv", "pip", "uninstall", "--python", str(python), "onnxruntime"], env=env)
    run([*pip, "--force-reinstall", "--no-deps", ORT_GPU], env=env)


def patch_and_init(python: Path, app: Path, *, env: dict[str, str]) -> None:
    run([str(python), str(app / "docker" / "patch_homr_onnx_provider.py")], env=env)
    # SegNet fp16 + OCR only, hash-checked; fails if a transformer checkpoint exists.
    run([str(python), str(app / "docker" / "init_homr_segnet.py")], env=env)


def strip_console_scripts(python_root: Path) -> list[str]:
    """Remove pip console-script launchers and their RECORD lines.

    The ``Scripts\\*.exe`` launchers embed the absolute interpreter path of the build
    location, so they break after relocation and make otherwise identical builds
    differ. The runtime only uses ``python -m``; nothing needs them.
    """

    scripts = python_root / "Scripts"
    removed = sorted(path.name for path in scripts.iterdir()) if scripts.is_dir() else []
    if scripts.is_dir():
        shutil.rmtree(scripts)
    site_packages = python_root / "Lib" / "site-packages"
    for record in site_packages.glob("*.dist-info/RECORD"):
        lines = record.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = [
            line for line in lines if not line.startswith(("../../Scripts/", "..\\..\\Scripts\\"))
        ]
        if kept != lines:
            record.write_text("".join(kept), encoding="utf-8")
    return removed


def check_distributions(site_packages: Path) -> dict[str, str]:
    expected = read_lock()
    installed = installed_distributions(site_packages)
    excluded = sorted(set(installed) & set(EXCLUDED_DISTRIBUTIONS))
    if excluded or set(expected) & set(EXCLUDED_DISTRIBUTIONS):
        raise RuntimeError(f"Excluded SR distributions must not be installed: {excluded}")
    leftovers = sorted(
        path.name for path in (site_packages / "homr" / "transformer").glob("*.onnx")
    )
    if leftovers:
        raise RuntimeError(f"HOMR transformer checkpoints must not be shipped: {leftovers}")
    runtime = {name: version for name, version in installed.items() if name not in UNLOCKED}
    if runtime != expected:
        missing = sorted(set(expected) - set(runtime))
        extra = sorted(set(runtime) - set(expected))
        changed = sorted(
            f"{name}: lock={expected[name]} installed={runtime[name]}"
            for name in set(expected) & set(runtime)
            if expected[name] != runtime[name]
        )
        raise RuntimeError(
            f"Installed distributions differ from the lock: missing={missing} "
            f"extra={extra} changed={changed}"
        )
    return installed


def stage_assets(root: Path, source: Path | None, cache: Path) -> list[dict]:
    records = []
    for asset in json.loads(ASSETS.read_text(encoding="utf-8"))["assets"]:
        target = root / asset["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        relative = Path(asset["path"]).relative_to("assets")
        staged = source / relative if source else None
        if staged is not None and staged.is_file():
            shutil.copyfile(staged, target)
            via = "asset-source"
        elif asset.get("url"):
            download = cache / "downloads" / relative
            if not download.is_file():
                download.parent.mkdir(parents=True, exist_ok=True)
                log(f"download {asset['url']}")
                with urllib.request.urlopen(asset["url"], timeout=120) as response:
                    download.write_bytes(response.read())
            shutil.copyfile(download, target)
            via = "url"
        else:
            raise FileNotFoundError(
                f"Asset {asset['path']} needs --asset-source ({asset['origin']})"
            )
        digest = sha256_file(target)
        if asset.get("sha256") and digest != asset["sha256"]:
            raise RuntimeError(f"Asset hash mismatch for {asset['path']}: {digest}")
        records.append({"path": asset["path"], "sha256": digest, "via": via})
    return records


def runtime_identity(python: Path, *, env: dict[str, str]) -> dict:
    probe = (
        "import json, platform, torch, torchvision, onnxruntime, cv2, numpy;"
        "import importlib.metadata as m;"
        "print(json.dumps({'cpython': platform.python_version(),"
        "'torch': torch.__version__, 'torch_cuda': torch.version.cuda,"
        "'cudnn': torch.backends.cudnn.version(), 'torchvision': torchvision.__version__,"
        "'onnxruntime': onnxruntime.__version__, 'opencv': cv2.__version__,"
        "'numpy': numpy.__version__, 'triton_windows': m.version('triton-windows')}))"
    )
    return json.loads(run([str(python), "-c", probe], env=env))


def write_manifest(
    root: Path,
    snap: payload.Snapshot,
    *,
    started: dt.datetime,
    builder: dict,
    runtime: dict,
    distributions: dict[str, str],
    assets: list[dict],
    removed_scripts: list[str],
) -> Path:
    """Inventory the folder, check the payload contract and write the build manifest."""

    files = build_inventory(root)
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        # Legacy meaning kept: the application source the jobs record (#535).
        "source_commit": snap.commit,
        "application_source_commit": snap.commit,
        # check_running_builder() requires the builder files of the same commit.
        "builder_source_commit": snap.commit,
        "source_tree": snap.tree,
        "built_at": started.isoformat(),
        "builder": builder,
        "application": snap.application_record(),
        "windows_overlay": snap.overlay_record(),
        "pins": {
            "cpython": CPYTHON_VERSION,
            "torch_index": TORCH_INDEX,
            "homr_commit": HOMR_COMMIT,
            "lock_sha256": payload.sha256(snap.inputs[payload.LOCK]),
            "assets_sha256": payload.sha256(snap.inputs[payload.ASSETS]),
        },
        "runtime": runtime,
        "distributions": dict(sorted(distributions.items())),
        "assets": assets,
        "removed_console_scripts": removed_scripts,
        "file_count": len(files),
        "total_bytes": sum(size for size, _ in files.values()),
        "tree_digest": tree_digest(files),
        "files": files,
    }
    problems = check_contract(root, manifest, files=files)
    if problems:
        raise RuntimeError("Portable payload contract failed:\n" + "\n".join(problems))
    manifest_path = root / MANIFEST_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    problems = verify(root, full=False)
    if problems:
        raise RuntimeError("Built folder does not verify:\n" + "\n".join(problems))
    return manifest_path


def build(args: argparse.Namespace) -> Path:
    repo = Path(git("rev-parse", "--show-toplevel", repo=Path.cwd()))
    # Read and check everything pinned before creating the output folder.
    snap = payload.snapshot(repo, args.commit)
    commit = snap.commit
    builder_files = payload.check_running_builder(snap)
    root = args.output.resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"Output folder must be new or empty: {root}")
    if not str(root).isascii():
        raise ValueError("Build the folder at an ASCII path; the launcher refuses others")
    cache = (args.cache or root.parent / f"{root.name}-build-cache").resolve()
    cache.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "UV_CACHE_DIR": str(cache / "uv"),
            "UV_LINK_MODE": "copy",
            "UV_PYTHON_INSTALL_BIN": "0",
            "UV_PYTHON_INSTALL_REGISTRY": "0",
            "UV_NO_CONFIG": "1",
            "POETRY_DYNAMIC_VERSIONING_BYPASS": "0.1.0",
            "PYTHONUTF8": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    env.pop("PYTHONPATH", None)
    started = dt.datetime.now(dt.timezone.utc)
    root.mkdir(parents=True, exist_ok=True)

    log(f"source {commit}: {len(snap.selected)} application files + Windows overlay")
    payload.stage(snap, root)
    pin_build_inputs(snap, cache)
    python = install_cpython(root / "python", env=env, cache=cache)
    install_packages(python, env=env)
    patch_and_init(python, root / APP_ROOT, env=env)
    removed_scripts = strip_console_scripts(root / "python")
    site_packages = root / "python" / "Lib" / "site-packages"
    distributions = check_distributions(site_packages)
    assets = stage_assets(root, args.asset_source, cache)

    markers = root / MARKERS_ROOT
    markers.mkdir(parents=True, exist_ok=True)
    (markers / "homr_maintained_profile_commit.txt").write_text(HOMR_COMMIT + "\n")
    (markers / "pdfscore_maintained_profile_commit.txt").write_text("workspace-runtime\n")
    for cache_dir in root.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
    # The HOMR patch/initialization must not have changed or added application files.
    errors = check_tree(root / APP_ROOT)
    if errors:
        raise RuntimeError("Application changed during the build:\n" + "\n".join(errors))

    manifest_path = write_manifest(
        root,
        snap,
        started=started,
        builder={
            "host_python": platform.python_version(),
            "uv": run(["uv", "--version"], env=env).strip(),
            "windows": platform.platform(),
            "files": builder_files,
        },
        runtime=runtime_identity(python, env=env),
        distributions=distributions,
        assets=assets,
        removed_scripts=removed_scripts,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = sha256_file(manifest_path)
    # Keep an out-of-folder copy of the manifest digest beside the candidate.
    (root.parent / f"{root.name}.build_manifest.sha256").write_text(
        f"{digest}  {root.name}/{MANIFEST_PATH.as_posix()}\n", encoding="utf-8"
    )
    log(
        f"done: {manifest['file_count']} files, {manifest['total_bytes'] / 2**30:.2f} GiB, "
        f"tree {manifest['tree_digest']}, manifest {digest}"
    )
    return root


def main() -> int:
    if os.name != "nt":
        print("The Windows portable folder must be built on Windows", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", required=True, help="frozen 40-hex source commit")
    parser.add_argument("--asset-source", type=Path)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    try:
        build(args)
    except subprocess.CalledProcessError as error:
        print(error.stdout or "", file=sys.stderr)
        print(error.stderr or "", file=sys.stderr)
        print(f"build failed: {error}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError) as error:
        print(f"build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
