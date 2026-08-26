"""Profile persistent multi-page current x4 SR with cuDNN benchmark on/off."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch

from src.pipeline.detection.current_sr_runtime import CurrentX4SRRuntime

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAGES = (
    ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_002.png",
    ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png",
    ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_025.png",
)


def _require_runtime() -> None:
    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError(
            "Issue #284 persistent cuDNN profiling requires canonical /workspace container"
        )
    if not Path(__import__("sys").executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(
            "Issue #284 persistent cuDNN profiling requires canonical pipeline Python"
        )
    if not torch.cuda.is_available():
        raise RuntimeError("Issue #284 persistent cuDNN profiling requires CUDA")


def _compare(candidate: np.ndarray, reference_path: Path) -> dict[str, Any]:
    reference = cv2.imread(str(reference_path), cv2.IMREAD_UNCHANGED)
    if reference is None:
        raise FileNotFoundError(reference_path)
    same_shape = candidate.shape == reference.shape
    result: dict[str, Any] = {"same_shape": same_shape, "array_equal": False}
    if not same_shape:
        return result
    delta = np.abs(candidate.astype(np.int16) - reference.astype(np.int16))
    result.update(
        {
            "array_equal": bool(np.array_equal(candidate, reference)),
            "different_values": int(np.count_nonzero(delta)),
            "max_abs_diff": int(delta.max(initial=0)),
            "mean_abs_diff": float(delta.mean()),
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path)
    args = parser.parse_args()

    _require_runtime()
    pages = [path.resolve() for path in DEFAULT_PAGES]
    missing = [str(path) for path in pages if not path.is_file()]
    if missing:
        raise FileNotFoundError(", ".join(missing))

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    reference_dir = args.reference_dir.resolve() if args.reference_dir else None

    torch.backends.cudnn.benchmark = bool(args.benchmark)
    torch.backends.cudnn.deterministic = False
    torch.cuda.empty_cache()
    torch.cuda.synchronize()
    init_started = time.perf_counter()
    runtime = CurrentX4SRRuntime(tile=400, tile_pad=10, fp32=False, channels_last=True)
    torch.cuda.synchronize()
    model_init_sec = time.perf_counter() - init_started

    torch.cuda.reset_peak_memory_stats()
    page_records: list[dict[str, Any]] = []
    enhance_total = 0.0

    for page in pages:
        image = cv2.imread(str(page), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(page)
        torch.cuda.synchronize()
        started = time.perf_counter()
        upscaled = runtime.enhance(image)
        torch.cuda.synchronize()
        wall = time.perf_counter() - started
        enhance_total += wall

        output_path = output_dir / page.name
        if not cv2.imwrite(str(output_path), upscaled):
            raise RuntimeError(f"Failed to write {output_path}")

        comparison = None
        if reference_dir is not None:
            comparison = _compare(upscaled, reference_dir / page.name)
        page_records.append(
            {
                "page": page.name,
                "enhance_wall_sec": wall,
                "comparison": comparison,
            }
        )
        del upscaled, image

    torch.cuda.synchronize()
    payload = {
        "schema_version": "issue284.persistent_cudnn_variant.v1",
        "status": "completed",
        "benchmark": bool(args.benchmark),
        "model_init_sec": model_init_sec,
        "enhance_total_wall_sec": enhance_total,
        "page_count": len(page_records),
        "pages": page_records,
        "peak_cuda_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "peak_cuda_reserved_bytes": int(torch.cuda.max_memory_reserved()),
        "device_total_bytes": int(torch.cuda.get_device_properties(0).total_memory),
        "all_array_equal": all(
            item["comparison"] is None or item["comparison"].get("array_equal") is True
            for item in page_records
        ),
        "backend": {
            "cudnn_benchmark": torch.backends.cudnn.benchmark,
            "cudnn_deterministic": torch.backends.cudnn.deterministic,
        },
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
