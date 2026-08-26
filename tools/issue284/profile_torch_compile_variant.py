"""Profile one PyTorch 2.13 torch.compile mode on the accepted current x4 SR runtime."""

from __future__ import annotations

import argparse
import json
import os
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
VALID_MODES = {
    "eager",
    "default",
    "reduce-overhead",
    "max-autotune-no-cudagraphs",
    "max-autotune",
}


def _require_runtime() -> None:
    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 compile profiler requires canonical /workspace container")
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(f"Expected canonical pipeline Python, got {sys.executable}")


def _compare(candidate: np.ndarray, reference: np.ndarray) -> dict[str, Any]:
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


def _counter_snapshot() -> dict[str, Any]:
    try:
        dynamo_utils = __import__("torch._dynamo.utils", fromlist=["counters"])
        counters = dynamo_utils.counters
        result: dict[str, Any] = {}
        for category, values in counters.items():
            result[str(category)] = {str(key): int(value) for key, value in values.items()}
        return result
    except Exception as error:  # noqa: BLE001
        return {"error": f"{type(error).__name__}: {error}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(VALID_MODES), required=True)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--reference-image", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()

    _require_runtime()
    if args.iterations < 2:
        raise ValueError("At least two full-page iterations are required to separate compile and steady-state")

    image_path = args.image.resolve()
    reference_path = args.reference_image.resolve()
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    reference = cv2.imread(str(reference_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(image_path)
    if reference is None:
        raise FileNotFoundError(reference_path)

    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = False

    payload: dict[str, Any] = {
        "schema_version": "issue284.torch_compile_variant.v1",
        "mode": args.mode,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version(),
        "inductor_cache_dir": os.environ.get("TORCHINDUCTOR_CACHE_DIR"),
        "image": str(image_path),
        "reference_image": str(reference_path),
        "iterations_requested": args.iterations,
        "status": "starting",
        "runtime": None,
        "compile_wrap_sec": None,
        "iterations": [],
        "dynamo_counters": None,
        "memory": None,
    }

    result_path = args.result.resolve()
    result_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        runtime = CurrentX4SRRuntime(tile=400, tile_pad=10, fp32=False, channels_last=True)
        payload["runtime"] = runtime.metadata()

        if args.mode != "eager":
            started = time.perf_counter()
            runtime.model = torch.compile(runtime.model, mode=args.mode)
            payload["compile_wrap_sec"] = time.perf_counter() - started
        else:
            payload["compile_wrap_sec"] = 0.0

        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

        for iteration in range(1, args.iterations + 1):
            torch.cuda.synchronize()
            started = time.perf_counter()
            output = runtime.enhance(image)
            torch.cuda.synchronize()
            wall = time.perf_counter() - started
            comparison = _compare(output, reference)
            payload["iterations"].append(
                {
                    "iteration": iteration,
                    "wall_sec": wall,
                    "comparison": comparison,
                }
            )
            del output

        payload["dynamo_counters"] = _counter_snapshot()
        payload["memory"] = {
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
            "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
            "device_total_bytes": int(torch.cuda.get_device_properties(0).total_memory),
        }
        payload["status"] = "completed"
    except Exception as error:  # noqa: BLE001
        payload["status"] = "failed"
        payload["error_type"] = type(error).__name__
        payload["error"] = str(error)
        payload["dynamo_counters"] = _counter_snapshot()
        if torch.cuda.is_available():
            payload["memory"] = {
                "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
                "device_total_bytes": int(torch.cuda.get_device_properties(0).total_memory),
            }
    finally:
        result_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
