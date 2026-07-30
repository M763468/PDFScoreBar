#!/usr/bin/env python3
"""Download and verify HOMR runtime models before focused detector inference."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any


def invoke_download_weights(download_weights: Callable[..., None]) -> dict[str, Any]:
    """Call supported HOMR download APIs with GPU inference enabled."""
    signature = inspect.signature(download_weights)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    count = len(positional)
    if count == 0:
        arguments: tuple[bool, ...] = ()
    elif count == 1:
        arguments = (True,)
    elif count == 2:
        arguments = (True, True)
    elif count == 3:
        arguments = (True, True, False)
    else:
        raise TypeError(f"Unsupported HOMR download_weights signature: {signature}")
    download_weights(*arguments)
    return {"signature": str(signature), "arguments": list(arguments)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_artifact(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"HOMR model was not created: {resolved}")
    return {
        "path": str(resolved),
        "size_bytes": resolved.stat().st_size,
        "sha256": _sha256(resolved),
    }


def run(output_path: Path) -> dict[str, Any]:
    """Bootstrap current HOMR GPU models and write their provenance."""
    report: dict[str, Any] = {
        "schema_version": "issue255.homr_model_bootstrap.v1",
        "status": "running",
        "python": sys.executable,
    }
    try:
        from homr.main import download_weights
        from homr.segmentation.config import segnet_path_onnx_fp16
        from homr.transformer.configs import default_config

        invocation = invoke_download_weights(download_weights)
        paths = {
            "segnet_fp16": Path(segnet_path_onnx_fp16),
            "encoder_fp16": Path(default_config.filepaths.encoder_path_fp16),
            "decoder_fp16": Path(default_config.filepaths.decoder_path_fp16),
        }
        report.update(
            {
                "status": "completed",
                "download_api": invocation,
                "models": {name: model_artifact(path) for name, path in paths.items()},
            }
        )
    except Exception as error:  # noqa: BLE001
        report.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
        )

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.output)
    print(
        json.dumps(
            {"status": report["status"], "report": str(args.output.resolve())},
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
