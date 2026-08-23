"""Profile a byte-equivalent GPU-side Real-ESRGAN output conversion candidate.

Profiling-only Issue #284 experiment. The model/tile path is kept at the current
production tile=400 setting. After producing the same fp16 x4 tensor, compare the
pinned Real-ESRGAN CPU conversion with a candidate that performs clamp/scale/
round/uint8/channel reorder on CUDA and transfers only uint8 BGR/HWC data.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch

from tools.issue284.profile_realesrgan_hotpath import (
    CANONICAL_IMAGE,
    compare_images,
    create_upsampler,
    require_canonical_container,
    resolve_compare_image,
    sha256,
)


def _prepare_output_tensor(image_bgr: np.ndarray, *, tile: int, tile_pad: int) -> tuple[torch.Tensor, float]:
    upsampler, _ = create_upsampler(tile, tile_pad, 0, False)
    image = image_bgr.astype(np.float32)
    if float(np.max(image)) > 256:
        raise ValueError("Representative Issue #284 path expects an 8-bit input")
    image = image / 255.0
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    upsampler.pre_process(image)
    torch.cuda.synchronize()
    started = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        upsampler.tile_process()
    output = upsampler.post_process()
    torch.cuda.synchronize()
    return output, time.perf_counter() - started


def _legacy_cpu_conversion(output: torch.Tensor) -> tuple[np.ndarray, dict[str, Any]]:
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    started = time.perf_counter()
    converted = output.data.squeeze().float().cpu().clamp_(0, 1).numpy()
    converted = np.transpose(converted[[2, 1, 0], :, :], (1, 2, 0))
    converted = (converted * 255.0).round().astype(np.uint8)
    torch.cuda.synchronize()
    return converted, {
        "wall_sec": time.perf_counter() - started,
        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
        "numpy_c_contiguous": bool(converted.flags.c_contiguous),
    }


def _gpu_uint8_conversion(output: torch.Tensor) -> tuple[np.ndarray, dict[str, Any]]:
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    started = time.perf_counter()
    converted = output.data.squeeze().float()
    converted.clamp_(0, 1).mul_(255.0).round_()
    converted_u8 = converted.to(torch.uint8)
    # RealESRGAN output is RGB/CHW. Production returns BGR/HWC to OpenCV.
    converted_bgr_hwc = converted_u8[[2, 1, 0], :, :].permute(1, 2, 0).contiguous()
    candidate = converted_bgr_hwc.cpu().numpy()
    torch.cuda.synchronize()
    result = {
        "wall_sec": time.perf_counter() - started,
        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
        "numpy_c_contiguous": bool(candidate.flags.c_contiguous),
    }
    del converted, converted_u8, converted_bgr_hwc
    return candidate, result


def _array_comparison(candidate: np.ndarray, reference: np.ndarray) -> dict[str, Any]:
    same_shape = candidate.shape == reference.shape
    result: dict[str, Any] = {
        "same_shape": same_shape,
        "candidate_shape": list(candidate.shape),
        "reference_shape": list(reference.shape),
        "array_equal": False,
    }
    if not same_shape:
        return result
    result["array_equal"] = bool(np.array_equal(candidate, reference))
    delta = np.abs(candidate.astype(np.int16) - reference.astype(np.int16))
    result.update(
        {
            "different_values": int(np.count_nonzero(delta)),
            "max_abs_diff": int(delta.max(initial=0)),
            "mean_abs_diff": float(delta.mean()),
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=CANONICAL_IMAGE)
    parser.add_argument("--tile", type=int, default=400)
    parser.add_argument("--tile-pad", type=int, default=10)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--compare-image", type=Path)
    parser.add_argument("--compare-baseline-summary", type=Path)
    args = parser.parse_args()

    require_canonical_container()
    image_path = args.image.resolve()
    image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise FileNotFoundError(image_path)

    args.result.parent.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "schema_version": "issue284.output_conversion_profile.v1",
        "status": "started",
        "image": str(image_path),
        "image_sha256": sha256(image_path),
        "tile": args.tile,
        "tile_pad": args.tile_pad,
        "device": torch.cuda.get_device_name(torch.cuda.current_device()),
    }

    try:
        output, tile_wall = _prepare_output_tensor(image_bgr, tile=args.tile, tile_pad=args.tile_pad)
        legacy, legacy_stats = _legacy_cpu_conversion(output)
        candidate, candidate_stats = _gpu_uint8_conversion(output)
        comparison = _array_comparison(candidate, legacy)
        result.update(
            {
                "status": "completed",
                "tile_process_synchronized_wall_sec": tile_wall,
                "legacy_cpu_conversion": legacy_stats,
                "gpu_uint8_conversion": candidate_stats,
                "candidate_vs_legacy": comparison,
                "conversion_saved_sec": legacy_stats["wall_sec"] - candidate_stats["wall_sec"],
                "conversion_reduction_fraction": (
                    (legacy_stats["wall_sec"] - candidate_stats["wall_sec"]) / legacy_stats["wall_sec"]
                ),
            }
        )

        reference_path = args.compare_image.resolve() if args.compare_image else None
        if reference_path is None and args.compare_baseline_summary:
            reference_path = resolve_compare_image(args.compare_baseline_summary.resolve(), image_path)
        if reference_path is not None:
            result["candidate_vs_production_reference"] = compare_images(candidate, reference_path)
    except Exception as error:  # noqa: BLE001
        result.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "memory_at_failure": {
                    "allocated_bytes": int(torch.cuda.memory_allocated()),
                    "reserved_bytes": int(torch.cuda.memory_reserved()),
                    "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                    "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
                },
            }
        )
        args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1

    args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
