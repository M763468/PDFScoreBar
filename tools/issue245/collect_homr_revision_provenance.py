#!/usr/bin/env python3
"""Collect machine-readable provenance for a pinned HOMR revision image."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def git_head(path: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def collect_model(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-name", required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()

    import homr
    import onnxruntime as ort
    from homr.main import ProcessingConfig, download_weights
    from homr.segmentation.config import segnet_path_onnx, segnet_path_onnx_fp16

    source_root = Path("/opt/issue245_homr")
    actual_commit = git_head(source_root)
    if actual_commit != args.expected_commit:
        raise RuntimeError(
            f"HOMR commit mismatch: expected={args.expected_commit} actual={actual_commit}"
        )

    package_root = Path(homr.__file__).resolve().parent
    model_paths = {
        Path(segnet_path_onnx).resolve(),
        Path(segnet_path_onnx_fp16).resolve(),
    }
    for path in package_root.rglob("*.onnx"):
        model_paths.add(path.resolve())
    for path in package_root.rglob("*.onnx.data"):
        model_paths.add(path.resolve())

    payload = {
        "schema_version": "issue245.homr_revision_provenance.v1",
        "candidate": {
            "name": args.candidate_name,
            "expected_commit": args.expected_commit,
            "actual_commit": actual_commit,
            "source_root": str(source_root),
        },
        "runtime": {
            "python_executable": sys.executable,
            "python_version": sys.version,
        },
        "packages": {
            name: package_version(name)
            for name in (
                "homr",
                "numpy",
                "opencv-python-headless",
                "onnxruntime",
                "onnxruntime-gpu",
                "torch",
                "torchvision",
                "Pillow",
                "scipy",
            )
        },
        "onnxruntime": {
            "version": ort.__version__,
            "available_providers": ort.get_available_providers(),
            "device": ort.get_device(),
        },
        "homr": {
            "module_file": str(Path(homr.__file__).resolve()),
            "download_weights_signature": str(inspect.signature(download_weights)),
            "processing_config_signature": str(inspect.signature(ProcessingConfig)),
        },
        "models": [collect_model(path) for path in sorted(model_paths)],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
