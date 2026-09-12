"""Build/runtime contract fingerprinting and fail-fast Docker validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable

SOURCE_CONTRACT_ROOTS = (
    Path("src"),
    Path("experiments/models"),
    Path("docker"),
)
SOURCE_CONTRACT_FILES = (
    Path("Dockerfile"),
    Path("pyproject.toml"),
)
SOURCE_SUFFIXES = frozenset({".py", ".toml"})


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
    for path in sorted(_source_contract_files(root), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _require_file(path: Path, *, role: str, errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"{role} is missing: {path}")


def _resolve_input_path(workspace: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else workspace / path


def run_preflight(workspace: Path, config_path: Path, expected_fingerprint_path: Path) -> int:
    errors: list[str] = []
    expected_fingerprint = (
        expected_fingerprint_path.read_text(encoding="utf-8").strip()
        if expected_fingerprint_path.is_file()
        else ""
    )
    actual_fingerprint = source_fingerprint(workspace)
    if not expected_fingerprint:
        errors.append(f"image source fingerprint is missing: {expected_fingerprint_path}")
    elif actual_fingerprint != expected_fingerprint:
        errors.append(
            "bind-mounted source does not match the source used to build the image; "
            f"expected={expected_fingerprint} actual={actual_fingerprint}. Rebuild the image."
        )

    if errors:
        print(json.dumps({"status": "fail", "errors": errors}, indent=2), file=sys.stderr)
        return 2

    sys.path.insert(0, str(workspace))

    import torch
    import yaml

    from src.common.model_artifacts import resolve_model_artifact
    from src.common.realesrgan_assets import resolve_realesrgan_weight
    from src.pipeline.detection.omr_dln_model import resolve_omr_dln_model_path

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    inputs = config.get("inputs") or {}
    detection = config.get("detection") or {}

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
            except Exception as exc:  # fail-fast report should retain the actionable resolver error
                errors.append(f"CNN manifest artifact is unavailable: {exc}")

    for marker in (
        Path("/opt/homr_stage_e_profile_commit.txt"),
        Path("/opt/pdfscore_stage_e_profile_commit.txt"),
    ):
        _require_file(marker, role="Stage-E runtime provenance marker", errors=errors)

    cuda_available = torch.cuda.is_available()
    if not cuda_available:
        errors.append("CUDA is not available inside the canonical Docker runtime")
    device = torch.cuda.get_device_name(torch.cuda.current_device()) if cuda_available else None

    payload = {
        "status": "pass" if not errors else "fail",
        "source_fingerprint": actual_fingerprint,
        "config": str(config_path),
        "input": str(input_path) if input_path is not None else None,
        "realesrgan_weights": sr_weights,
        "omr_dln_model": str(omr_model),
        "cnn_model": str(cnn_model_path) if cnn_model_path is not None else resolved_manifest_model,
        "cuda_available": cuda_available,
        "cuda_device": device,
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

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--workspace", type=Path, default=Path("/workspace"))
    preflight.add_argument("--config", type=Path, required=True)
    preflight.add_argument(
        "--expected-fingerprint",
        type=Path,
        default=Path("/opt/pdfscore-runtime/source_fingerprint.txt"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "fingerprint":
        print(source_fingerprint(args.root))
        return 0
    return run_preflight(args.workspace, args.config, args.expected_fingerprint)


if __name__ == "__main__":
    raise SystemExit(main())
