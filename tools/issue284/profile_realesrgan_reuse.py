"""Measure page-to-page Real-ESRGAN upsampler reuse for Issue #284.

Profiling-only experiment. Production currently launches one current_sr_worker per
page and always passes upsampler=None. This script stays in one canonical CUDA
process, reuses the existing apply_advanced_sr(..., upsampler=...) contract, and
checks every candidate image against retained production SR output.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import torch

from src.common.preprocessing import apply_advanced_sr
from tools.issue284.profile_realesrgan_hotpath import (
    compare_images,
    require_canonical_container,
    resolve_compare_image,
    sha256,
)

DEFAULT_IMAGES = (
    ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_012.png",
    ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png",
    ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_014.png",
)


def _cleanup_reused_upsampler(upsampler: Any) -> dict[str, Any]:
    """Release page-sized tensors while retaining only model/runtime state."""
    torch.cuda.synchronize()
    started = time.perf_counter()
    if hasattr(upsampler, "img"):
        upsampler.img = None
    if hasattr(upsampler, "output"):
        upsampler.output = None
    torch.cuda.empty_cache()
    torch.cuda.synchronize()
    return {
        "wall_sec": time.perf_counter() - started,
        "allocated_bytes": int(torch.cuda.memory_allocated()),
        "reserved_bytes": int(torch.cuda.memory_reserved()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", nargs="+", type=Path, default=list(DEFAULT_IMAGES))
    parser.add_argument("--tile", type=int, default=400)
    parser.add_argument("--tile-pad", type=int, default=10)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    require_canonical_container()
    baseline = args.baseline_summary.resolve()
    if not baseline.is_file():
        raise FileNotFoundError(baseline)
    args.result.parent.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "schema_version": "issue284.realesrgan_reuse.v1",
        "status": "started",
        "device": torch.cuda.get_device_name(torch.cuda.current_device()),
        "tile": args.tile,
        "tile_pad": args.tile_pad,
        "baseline_summary": str(baseline),
        "pages": [],
    }

    upsampler = None
    try:
        for index, raw_image in enumerate(args.images):
            image_path = raw_image.resolve()
            image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image_bgr is None:
                raise FileNotFoundError(image_path)
            reference = resolve_compare_image(baseline, image_path)
            if reference is None:
                raise FileNotFoundError(f"No retained baseline SR image for {image_path.name}")

            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            started = time.perf_counter()
            output, upsampler = apply_advanced_sr(
                image_bgr,
                model_name="RealESRGAN_x4plus",
                scale=4,
                tile=args.tile,
                tile_pad=args.tile_pad,
                fp32=False,
                upsampler=upsampler,
            )
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - started
            page_record = {
                "index": index,
                "image": str(image_path),
                "image_sha256": sha256(image_path),
                "reused_existing_upsampler": index > 0,
                "apply_advanced_sr_wall_sec": elapsed,
                "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
                "comparison": compare_images(output, reference),
            }
            del output
            page_record["cleanup"] = _cleanup_reused_upsampler(upsampler)
            result["pages"].append(page_record)

        walls = [float(page["apply_advanced_sr_wall_sec"]) for page in result["pages"]]
        reused_walls = walls[1:]
        result.update(
            {
                "status": "completed",
                "first_page_wall_sec": walls[0] if walls else None,
                "reused_page_mean_wall_sec": (
                    statistics.fmean(reused_walls) if reused_walls else None
                ),
                "all_outputs_array_equal": all(
                    bool(page["comparison"].get("array_equal")) for page in result["pages"]
                ),
                "retained_after_final_cleanup_allocated_bytes": int(torch.cuda.memory_allocated()),
                "retained_after_final_cleanup_reserved_bytes": int(torch.cuda.memory_reserved()),
            }
        )
    except Exception as error:  # noqa: BLE001
        result.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "allocated_bytes_at_failure": int(torch.cuda.memory_allocated()),
                "reserved_bytes_at_failure": int(torch.cuda.memory_reserved()),
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
