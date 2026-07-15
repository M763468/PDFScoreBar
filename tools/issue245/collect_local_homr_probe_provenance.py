#!/usr/bin/env python3
"""Collect provenance for the reconstructed local HOMR snapshot image."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import inspect
import json
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


def file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()

    import homr
    import onnxruntime as ort
    from homr.main import ProcessingConfig, download_weights
    from homr.segmentation import config as segmentation_config
    from homr.segmentation.inference_segnet import Segnet

    source_root = Path("/opt/issue245_homr")
    recorded_commit = Path("/opt/issue245_homr_commit.txt").read_text(
        encoding="utf-8"
    ).strip()
    if recorded_commit != args.expected_commit:
        raise RuntimeError(
            "HOMR source commit mismatch: "
            f"expected={args.expected_commit} recorded={recorded_commit}"
        )

    fp32_model = Path(segmentation_config.segnet_path_onnx).resolve()
    session = Segnet(str(fp32_model), True).model
    model_paths = {fp32_model}
    package_root = Path(homr.__file__).resolve().parent
    for pattern in ("*.onnx", "*.onnx.data"):
        model_paths.update(path.resolve() for path in package_root.rglob(pattern))

    payload = {
        "schema_version": "issue245.local_homr_probe_provenance.v1",
        "candidate": {
            "expected_commit": args.expected_commit,
            "recorded_commit": recorded_commit,
            "source_root": str(source_root),
            "module_root": str(package_root),
        },
        "runtime": {
            "python_executable": sys.executable,
            "python_version": sys.version,
        },
        "packages": {
            name: package_version(name)
            for name in (
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
            "device": ort.get_device(),
            "available_providers": ort.get_available_providers(),
            "selected_model_providers": session.get_providers(),
        },
        "homr": {
            "module_file": str(Path(homr.__file__).resolve()),
            "download_weights_signature": str(inspect.signature(download_weights)),
            "processing_config_signature": str(inspect.signature(ProcessingConfig)),
            "source_files": [
                file_record(source_root / relative)
                for relative in (
                    "homr/autocrop.py",
                    "homr/main.py",
                    "homr/segmentation/config.py",
                    "homr/segmentation/inference_segnet.py",
                    "pyproject.toml",
                )
            ],
        },
        "models": [file_record(path) for path in sorted(model_paths)],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
