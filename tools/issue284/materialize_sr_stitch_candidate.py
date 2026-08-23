"""Materialize one profiling-only Real-ESRGAN stitch candidate for Issue #284.

Runs in its own CUDA process so the SR model exits before downstream HOMR/OMR
workers start. The implementation reuses the full-page stitch profiler's model
and tile path, then persists the resulting uint8 x4 image for propagation gates.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import torch

from tools.issue284.profile_realesrgan_hotpath import sha256
from tools.issue284.profile_sr_stitch_variant_worker import (
    _create_model,
    _profile,
    _require_runtime,
)

IMAGE = ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=IMAGE)
    parser.add_argument("--output-image", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--tile", type=int, default=400)
    parser.add_argument("--tile-pad", type=int, default=10)
    parser.add_argument("--channels-last", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()

    _require_runtime()
    image = args.image.resolve()
    output_image = args.output_image.resolve()
    result_path = args.result.resolve()
    output_image.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": "issue284.materialized_sr_stitch_candidate.v1",
        "status": "started",
        "image": str(image),
        "output_image": str(output_image),
        "tile": args.tile,
        "tile_pad": args.tile_pad,
        "channels_last": args.channels_last,
        "benchmark": args.benchmark,
        "inference_mode": True,
        "output_mode": "gpu_uint8_cpu_stitch",
    }

    try:
        image_bgr = cv2.imread(str(image), cv2.IMREAD_COLOR)
        if image_bgr is None:
            raise FileNotFoundError(image)

        torch.backends.cudnn.benchmark = args.benchmark
        torch.backends.cudnn.deterministic = False
        torch.cuda.empty_cache()
        model = _create_model(channels_last=args.channels_last)
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()

        started = time.perf_counter()
        output, profile = _profile(
            image_bgr,
            model,
            tile=args.tile,
            tile_pad=args.tile_pad,
            channels_last=args.channels_last,
        )
        torch.cuda.synchronize()
        inference_wall = time.perf_counter() - started

        write_started = time.perf_counter()
        if not cv2.imwrite(str(output_image), output):
            raise RuntimeError(f"Failed to write {output_image}")
        write_sec = time.perf_counter() - write_started

        payload.update(profile)
        payload.update(
            {
                "status": "completed",
                "profiled_total_wall_sec": inference_wall,
                "write_sec": write_sec,
                "output_sha256": sha256(output_image),
                "output_shape": list(output.shape),
                "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
            }
        )
    except Exception as error:  # noqa: BLE001
        payload.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
