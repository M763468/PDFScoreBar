"""Probe PyTorch/compiler capabilities and current SR compatibility for Issue #284.

This profiling-only tool does not mutate the environment. It records the active
Torch stack, available torch.compile modes, import compatibility for the packages
used by the current SR path, and optionally runs the accepted page_013 current-SR
runtime against a retained reference image.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
import torch

from src.pipeline.detection.current_sr_runtime import CurrentX4SRRuntime

DEFAULT_IMAGE = ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png"


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _compile_modes() -> dict[str, Any]:
    result: dict[str, Any] = {"available": hasattr(torch, "compile"), "modes": None, "error": None}
    if not result["available"]:
        return result
    try:
        inductor = importlib.import_module("torch._inductor")
        result["modes"] = inductor.list_mode_options()
    except Exception as error:  # noqa: BLE001
        result["error"] = f"{type(error).__name__}: {error}"
    return result


def _import_smoke() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for module_name in ("torchvision", "basicsr", "realesrgan", "ultralytics"):
        try:
            module = importlib.import_module(module_name)
            result[module_name] = {
                "ok": True,
                "version": getattr(module, "__version__", None),
            }
        except Exception as error:  # noqa: BLE001
            result[module_name] = {
                "ok": False,
                "error": f"{type(error).__name__}: {error}",
            }
    return result


def _compare(candidate: np.ndarray, reference_path: Path) -> dict[str, Any]:
    reference = cv2.imread(str(reference_path), cv2.IMREAD_UNCHANGED)
    if reference is None:
        raise FileNotFoundError(reference_path)
    same_shape = candidate.shape == reference.shape
    payload: dict[str, Any] = {
        "same_shape": same_shape,
        "array_equal": False,
        "candidate_shape": list(candidate.shape),
        "reference_shape": list(reference.shape),
    }
    if not same_shape:
        return payload
    delta = np.abs(candidate.astype(np.int16) - reference.astype(np.int16))
    payload.update(
        {
            "array_equal": bool(np.array_equal(candidate, reference)),
            "different_values": int(np.count_nonzero(delta)),
            "max_abs_diff": int(delta.max(initial=0)),
            "mean_abs_diff": float(delta.mean()),
        }
    )
    return payload


def _sr_probe(image_path: Path, reference_path: Path) -> dict[str, Any]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    runtime = CurrentX4SRRuntime(tile=400, tile_pad=10, fp32=False, channels_last=True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = False
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    started = time.perf_counter()
    output = runtime.enhance(image)
    torch.cuda.synchronize()
    wall = time.perf_counter() - started
    return {
        "status": "completed",
        "wall_sec": wall,
        "runtime": runtime.metadata(),
        "memory": {
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
            "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
            "device_total_bytes": int(torch.cuda.get_device_properties(0).total_memory),
        },
        "comparison": _compare(output, reference_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--reference-image", type=Path)
    args = parser.parse_args()

    payload: dict[str, Any] = {
        "schema_version": "issue284.torch_runtime_capabilities.v1",
        "python": sys.version,
        "torch": {
            "version": torch.__version__,
            "cuda_version": torch.version.cuda,
            "cudnn_version": torch.backends.cudnn.version(),
            "cuda_available": torch.cuda.is_available(),
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        },
        "packages": {
            name: _package_version(name)
            for name in (
                "torch",
                "torchvision",
                "triton",
                "basicsr",
                "realesrgan",
                "ultralytics",
            )
        },
        "compile": _compile_modes(),
        "imports": _import_smoke(),
        "sr_probe": None,
    }

    if args.reference_image is not None:
        try:
            payload["sr_probe"] = _sr_probe(args.image.resolve(), args.reference_image.resolve())
        except Exception as error:  # noqa: BLE001
            payload["sr_probe"] = {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }

    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
