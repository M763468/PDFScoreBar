"""Build/runtime contract fingerprinting and fail-fast Docker validation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable

SOURCE_CONTRACT_ROOTS = (
    Path("src"),
    Path("docker"),
    Path("configs"),
    Path("models"),
)
SOURCE_CONTRACT_FILES = (
    Path("Dockerfile"),
    Path("pyproject.toml"),
    Path("tools/review_correction/server.py"),
    Path("tools/review_correction/application.py"),
    Path("tools/review_correction/state.py"),
    Path("tools/review_correction/history.py"),
    Path("tools/review_correction/resume.py"),
    Path("tools/review_correction/history.js"),
    Path("src/pipeline/review/number_layer.py"),
    Path("tools/review_correction/index.html"),
    Path("tools/review_correction/app.js"),
    Path("tools/review_correction/strings.js"),
    Path("tools/review_correction/correction_state.js"),
)
SOURCE_SUFFIXES = frozenset({".py", ".toml", ".yaml", ".yml", ".json", ".pth"})
RUNTIME_MODULES = ("homr", "realesrgan", "basicsr", "ultralytics")
PROVENANCE_NAME = "DISTRIBUTION_PROVENANCE.json"
MANIFEST_NAME = "docs/MINIMAL_MAINLINE_SURFACE.json"
MANIFEST_SECTIONS = (
    "runtime_bundle_patterns",
    "distribution_support_patterns",
    "distribution_metadata_patterns",
)

# Image/runtime compatibility is intentionally narrower than source provenance.
# The active checkout is bind-mounted at /workspace, so application Python does
# not require an image rebuild. These inputs define the image-owned environment
# and assets that must remain compatible with the selected image.
RUNTIME_CONTRACT_FILES = (
    Path("Dockerfile"),
    Path("pyproject.toml"),
    Path("docker/patch_homr_onnx_provider.py"),
    Path("models/barline_cnn/manifest.json"),
    Path("src/common/model_artifacts.py"),
    Path("src/common/__init__.py"),
    Path("src/common/barline_geometry.py"),
)

LEGACY_SOURCE_PROVENANCE_LINES = (
    "/opt/venv_pipeline/bin/python /opt/pdfscore-runtime/runtime_contract.py "
    "fingerprint /workspace \\",
    "> /opt/pdfscore-runtime/source_fingerprint.txt && \\",
)
CURRENT_SOURCE_PROVENANCE_LINES = (
    "ACTUAL_SOURCE_FINGERPRINT=$(/opt/venv_pipeline/bin/python \\",
    "/opt/pdfscore-runtime/runtime_contract.py fingerprint /workspace) && \\",
    "printf '%s\\n' \"${ACTUAL_SOURCE_FINGERPRINT}\" \\",
    "> /opt/pdfscore-runtime/source_fingerprint.txt && \\",
    'if [ -n "${PDFSCORE_SOURCE_FINGERPRINT}" ] && \\',
    '[ "${ACTUAL_SOURCE_FINGERPRINT}" != "${PDFSCORE_SOURCE_FINGERPRINT}" ]; then \\',
    'echo "Docker build source fingerprint changed during build context transfer" >&2; \\',
    'echo "expected=${PDFSCORE_SOURCE_FINGERPRINT} actual=${ACTUAL_SOURCE_FINGERPRINT}" >&2; \\',
    "exit 1; \\",
    "fi && \\",
)

PROVENANCE_ARG_LINES = frozenset(
    {
        "ARG PDFSCORE_SOURCE_FINGERPRINT",
        "ARG PDFSCORE_SOURCE_COMMIT",
        "ARG PDFSCORE_SOURCE_BRANCH",
    }
)
PROVENANCE_LABEL_LINES = frozenset(
    {
        'LABEL pdfscore.runtime.source_fingerprint="${PDFSCORE_SOURCE_FINGERPRINT}"',
        'LABEL pdfscore.runtime.source_commit="${PDFSCORE_SOURCE_COMMIT}"',
        'LABEL pdfscore.runtime.source_branch="${PDFSCORE_SOURCE_BRANCH}"',
    }
)


def _source_contract_files(root: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for relative in SOURCE_CONTRACT_FILES:
        path = root / relative
        if path.is_file():
            seen.add(path)
            yield path
    for relative_root in SOURCE_CONTRACT_ROOTS:
        base = root / relative_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            if "__pycache__" in path.parts or path in seen:
                continue
            seen.add(path)
            yield path


def source_fingerprint(root: Path) -> str:
    """Hash runtime-sensitive source independently of git/worktree metadata."""
    digest = hashlib.sha256()
    paths = sorted(
        _source_contract_files(root),
        key=lambda item: item.relative_to(root).as_posix(),
    )
    for path in paths:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def validate_distribution_provenance(workspace: Path) -> dict | None:
    """Verify all manifest-selected bytes before trusting a frozen identity."""
    provenance_path = workspace / PROVENANCE_NAME
    if not provenance_path.is_file():
        return None
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        manifest = json.loads((workspace / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read distribution identity metadata: {exc}") from exc
    if not isinstance(provenance, dict) or not isinstance(manifest, dict):
        raise ValueError("distribution identity metadata must be JSON objects")
    if provenance.get("schema_version") != 1:
        raise ValueError("unsupported distribution provenance schema")
    if not isinstance(provenance.get("source_commit"), str) or not re.fullmatch(
        r"[0-9a-f]{40}", provenance["source_commit"]
    ):
        raise ValueError("distribution provenance has an invalid source commit")
    if manifest.get("schema_version") != 3:
        raise ValueError("unsupported distribution manifest schema")

    selected: set[str] = set()
    for section in MANIFEST_SECTIONS:
        entries = manifest.get(section)
        if not isinstance(entries, list):
            raise ValueError(f"invalid distribution manifest section: {section}")
        for entry in entries:
            relative = entry.get("pattern") if isinstance(entry, dict) else None
            path = PurePosixPath(relative) if isinstance(relative, str) else None
            if (
                path is None
                or path.is_absolute()
                or ".." in path.parts
                or str(path) != relative
                or any(char in relative for char in "*?[")
                or relative == PROVENANCE_NAME
                or not entry.get("role")
            ):
                raise ValueError(f"invalid exact distribution entry: {entry}")
            if relative in selected:
                raise ValueError(f"duplicate distribution entry: {relative}")
            selected.add(relative)
    if MANIFEST_NAME not in selected:
        raise ValueError("distribution manifest must include itself")

    hashes = provenance.get("files")
    if not isinstance(hashes, dict) or set(hashes) != selected:
        raise ValueError("distribution provenance file selection differs from manifest")
    for relative, expected in hashes.items():
        path = PurePosixPath(relative)
        if (
            path.is_absolute()
            or ".." in path.parts
            or str(path) != relative
            or not isinstance(expected, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected)
        ):
            raise ValueError(f"invalid distribution provenance entry: {relative!r}")
        target = workspace / relative
        if (
            target.is_symlink()
            or not target.is_file()
            or not target.resolve().is_relative_to(workspace.resolve())
        ):
            raise ValueError(f"missing or unsafe distributed file: {relative}")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"distribution content hash mismatch: {relative}")

    release = provenance.get("release")
    if isinstance(release, dict):
        manifest_hash = hashlib.sha256((workspace / MANIFEST_NAME).read_bytes()).hexdigest()
        if release.get("manifest_sha256") != manifest_hash:
            raise ValueError("distribution manifest hash differs from release provenance")
        modes = release.get("file_modes")
        if not isinstance(modes, dict) or set(modes) != selected:
            raise ValueError("distribution file modes differ from release provenance")
        for relative, mode in modes.items():
            if mode not in {"100644", "100755"}:
                raise ValueError(f"invalid distributed file mode: {relative}")
            executable = bool((workspace / relative).stat().st_mode & 0o111)
            if executable != (mode == "100755"):
                raise ValueError(f"distribution file mode mismatch: {relative}")
    return provenance


def _remove_exact_sequence(lines: list[str], sequence: tuple[str, ...]) -> list[str]:
    """Remove only a known provenance command sequence; unknown syntax remains hashed."""
    output: list[str] = []
    index = 0
    width = len(sequence)
    while index < len(lines):
        stripped_window = tuple(line.strip() for line in lines[index : index + width])
        if stripped_window == sequence:
            index += width
            continue
        output.append(lines[index])
        index += 1
    return output


def _dockerfile_runtime_contract(payload: bytes) -> bytes:
    """Strip only known source-provenance commands from compatibility hashing."""
    lines = payload.decode("utf-8").splitlines()
    lines = _remove_exact_sequence(lines, LEGACY_SOURCE_PROVENANCE_LINES)
    lines = _remove_exact_sequence(lines, CURRENT_SOURCE_PROVENANCE_LINES)

    normalized: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped in PROVENANCE_ARG_LINES:
            continue
        if stripped in PROVENANCE_LABEL_LINES:
            continue
        if not stripped or stripped.startswith("#"):
            continue
        normalized.append(line.rstrip())

    return ("\n".join(normalized) + "\n").encode("utf-8")


def _runtime_contract_bytes(relative: Path, payload: bytes | None) -> bytes:
    if payload is None:
        return b"<missing>"
    if relative == Path("Dockerfile"):
        return _dockerfile_runtime_contract(payload)
    return payload


def runtime_fingerprint_entries(entries: dict[str, bytes | None]) -> str:
    """Hash only image/environment-defining inputs, not bind-mounted app source."""
    digest = hashlib.sha256()
    for relative in RUNTIME_CONTRACT_FILES:
        key = relative.as_posix()
        digest.update(key.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_runtime_contract_bytes(relative, entries.get(key)))
        digest.update(b"\0")
    return digest.hexdigest()


def runtime_fingerprint(root: Path) -> str:
    entries: dict[str, bytes | None] = {}
    for relative in RUNTIME_CONTRACT_FILES:
        path = root / relative
        entries[relative.as_posix()] = path.read_bytes() if path.is_file() else None
    return runtime_fingerprint_entries(entries)


def _symlink_ancestor(path: Path) -> tuple[Path, Path] | None:
    """Return the nearest symlink in a missing path chain, including dangling links."""
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            try:
                target = candidate.readlink()
            except OSError:
                target = Path("<unreadable>")
            return candidate, target
    return None


def _require_file(path: Path, *, role: str, errors: list[str]) -> None:
    if path.is_file():
        return

    message = f"{role} is missing: {path}"
    symlink = _symlink_ancestor(path)
    if symlink is not None:
        link, target = symlink
        message += (
            f"; path crosses symlink {link} -> {target}. A bind mount of /workspace does not "
            "automatically expose targets outside that mounted checkout. Explicitly bind the "
            "required external target or materialize it under the documented ownership contract."
        )
    errors.append(message)


def _resolve_input_path(workspace: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else workspace / path


def _host_provenance() -> dict[str, str | None]:
    return {
        "source_root": os.environ.get("PDFSCORE_HOST_SOURCE_ROOT"),
        "branch": os.environ.get("PDFSCORE_HOST_SOURCE_BRANCH"),
        "commit": os.environ.get("PDFSCORE_HOST_SOURCE_COMMIT"),
        "image_ref": os.environ.get("PDFSCORE_DOCKER_IMAGE_REF"),
        "image_id": os.environ.get("PDFSCORE_DOCKER_IMAGE_ID"),
    }


def _validate_production_provenance(workspace: Path, errors: list[str]) -> None:
    from src.pipeline.detection.profile_contract import (
        load_profile_manifest,
        validate_profile_runtime,
    )

    try:
        profile = load_profile_manifest(
            "maintained_original",
            workspace / "configs/detector_profiles/maintained_original_homr.json",
        )
        validate_profile_runtime(profile)
    except (OSError, RuntimeError, ValueError) as exc:
        errors.append(f"maintained production provenance is invalid: {exc}")


def run_preflight(
    workspace: Path,
    config_path: Path,
    expected_fingerprint_path: Path,
    *,
    expected_fingerprint_value: str | None = None,
    expected_source_fingerprint_path: Path = Path("/opt/pdfscore-runtime/source_fingerprint.txt"),
) -> int:
    errors: list[str] = []
    host_provenance = _host_provenance()
    expected_runtime_fingerprint = (
        expected_fingerprint_value.strip()
        if expected_fingerprint_value
        else (
            expected_fingerprint_path.read_text(encoding="utf-8").strip()
            if expected_fingerprint_path.is_file()
            else ""
        )
    )
    actual_runtime_fingerprint = runtime_fingerprint(workspace)
    actual_source_fingerprint = source_fingerprint(workspace)
    image_source_fingerprint = (
        expected_source_fingerprint_path.read_text(encoding="utf-8").strip()
        if expected_source_fingerprint_path.is_file()
        else None
    )

    try:
        validate_distribution_provenance(workspace)
    except (OSError, ValueError) as exc:
        errors.append(f"distribution provenance is invalid: {exc}")

    if not expected_runtime_fingerprint:
        errors.append("selected image runtime compatibility fingerprint is missing")
    elif actual_runtime_fingerprint != expected_runtime_fingerprint:
        errors.append(
            "bind-mounted checkout changed image/environment-defining inputs after host "
            "image resolution; "
            f"expected={expected_runtime_fingerprint} actual={actual_runtime_fingerprint}"
        )

    if errors:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "runtime_fingerprint": actual_runtime_fingerprint,
                    "source_fingerprint": actual_source_fingerprint,
                    "image_source_fingerprint": image_source_fingerprint,
                    "source_fingerprint_match": (
                        image_source_fingerprint == actual_source_fingerprint
                        if image_source_fingerprint
                        else None
                    ),
                    "host_provenance": host_provenance,
                    "errors": errors,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    sys.path.insert(0, str(workspace))

    import onnxruntime as ort
    import torch
    import yaml

    from src.common.model_artifacts import (
        resolve_model_artifact,
        resolve_omr_dln_model_path,
        resolve_realesrgan_weight,
    )

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    inputs = config.get("inputs") or {}
    detection = config.get("detection") or {}
    mmr = config.get("mmr") or {}

    input_path = _resolve_input_path(workspace, inputs.get("pdf_path"))
    if input_path is not None:
        _require_file(input_path, role="configured smoke input", errors=errors)

    sr_weights = {}
    for model_name in ("RealESRGAN_x2plus", "RealESRGAN_x4plus"):
        path = resolve_realesrgan_weight(model_name, project_root=workspace)
        _require_file(path, role=f"image-owned {model_name} weight", errors=errors)
        sr_weights[model_name] = str(path)

    omr_model = resolve_omr_dln_model_path(repository_root=workspace)
    _require_file(omr_model, role="OMR-DLN external model", errors=errors)

    cnn_model = detection.get("cnn_model_path")
    cnn_model_path = _resolve_input_path(workspace, cnn_model)
    if cnn_model_path is not None:
        _require_file(cnn_model_path, role="configured CNN model", errors=errors)

    cnn_manifest = detection.get("cnn_model_manifest")
    resolved_manifest_model = None
    if cnn_manifest:
        manifest_path = _resolve_input_path(workspace, cnn_manifest)
        if manifest_path is None:
            errors.append("detection.cnn_model_manifest is invalid")
        else:
            try:
                resolved_manifest_model = str(
                    resolve_model_artifact(manifest_path, project_root=workspace)
                )
            except Exception as exc:
                errors.append(f"CNN manifest artifact is unavailable: {exc}")

    mmr_model_path = _resolve_input_path(workspace, mmr.get("model_path"))
    if mmr_model_path is not None:
        _require_file(mmr_model_path, role="configured MMR model", errors=errors)

    module_origins: dict[str, str | None] = {}
    for module_name in RUNTIME_MODULES:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            errors.append(f"required runtime module is unavailable: {module_name}")
            module_origins[module_name] = None
        else:
            module_origins[module_name] = spec.origin

    # Canonical preflight shares the maintained profile's pinned marker contract.
    # Historical profile validation belongs to its explicit reproduction runner.
    _validate_production_provenance(workspace, errors)

    cuda_available = torch.cuda.is_available()
    if not cuda_available:
        errors.append("CUDA is not available inside the canonical Docker runtime")
    device = torch.cuda.get_device_name(torch.cuda.current_device()) if cuda_available else None

    onnx_providers = ort.get_available_providers()
    if "CUDAExecutionProvider" not in onnx_providers:
        errors.append(
            "onnxruntime CUDAExecutionProvider is unavailable inside the canonical Docker runtime"
        )

    payload = {
        "status": "pass" if not errors else "fail",
        "runtime_fingerprint": actual_runtime_fingerprint,
        "source_fingerprint": actual_source_fingerprint,
        "image_source_fingerprint": image_source_fingerprint,
        "source_fingerprint_match": (
            image_source_fingerprint == actual_source_fingerprint
            if image_source_fingerprint
            else None
        ),
        "host_provenance": host_provenance,
        "config": str(config_path),
        "input": str(input_path) if input_path is not None else None,
        "realesrgan_weights": sr_weights,
        "omr_dln_model": str(omr_model),
        "cnn_model": (
            str(cnn_model_path) if cnn_model_path is not None else resolved_manifest_model
        ),
        "mmr_model": str(mmr_model_path) if mmr_model_path is not None else None,
        "runtime_modules": module_origins,
        "cuda_available": cuda_available,
        "cuda_device": device,
        "onnxruntime_providers": onnx_providers,
        "errors": errors,
    }
    stream = sys.stdout if not errors else sys.stderr
    print(json.dumps(payload, indent=2), file=stream)
    return 0 if not errors else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fingerprint = subparsers.add_parser("fingerprint")
    fingerprint.add_argument("root", type=Path)

    runtime = subparsers.add_parser("runtime-fingerprint")
    runtime.add_argument("root", type=Path)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--workspace", type=Path, default=Path("/workspace"))
    preflight.add_argument("--config", type=Path, required=True)
    preflight.add_argument(
        "--expected-fingerprint",
        type=Path,
        default=Path("/opt/pdfscore-runtime/runtime_fingerprint.txt"),
        help="Compatibility fingerprint file; retained for script/test compatibility.",
    )
    preflight.add_argument(
        "--expected-fingerprint-value",
        help="Host-resolved image/runtime compatibility fingerprint.",
    )
    preflight.add_argument(
        "--expected-source-fingerprint",
        type=Path,
        default=Path("/opt/pdfscore-runtime/source_fingerprint.txt"),
        help="Image build-source fingerprint used only for provenance reporting.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "fingerprint":
        print(source_fingerprint(args.root))
        return 0
    if args.command == "runtime-fingerprint":
        print(runtime_fingerprint(args.root))
        return 0
    return run_preflight(
        args.workspace,
        args.config,
        args.expected_fingerprint,
        expected_fingerprint_value=args.expected_fingerprint_value,
        expected_source_fingerprint_path=args.expected_source_fingerprint,
    )


if __name__ == "__main__":
    raise SystemExit(main())
