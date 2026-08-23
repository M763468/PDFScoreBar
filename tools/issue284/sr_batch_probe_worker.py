"""Profiling-only reusable Real-ESRGAN SR batch worker for Issue #284.

This worker mirrors the production current_sr_worker page contract closely, but
keeps one RealESRGANer alive across multiple pages. It persists one x4 PNG and
SHA256 per page, then releases page-sized CUDA tensors while retaining only the
model/runtime state. The process exits before any HOMR/OMR phase in the intended
production design.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cleanup(upsampler: Any) -> dict[str, Any]:
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
    parser.add_argument("--images", nargs="+", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--tile", type=int, default=400)
    parser.add_argument("--tile-pad", type=int, default=10)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("Issue #284 SR batch probe requires CUDA")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    args.result.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "issue284.sr_batch_probe_worker.v1",
        "status": "started",
        "tile": args.tile,
        "tile_pad": args.tile_pad,
        "device": torch.cuda.get_device_name(torch.cuda.current_device()),
        "pages": [],
    }

    upsampler = None
    batch_started = time.perf_counter()
    try:
        for index, raw_image in enumerate(args.images):
            image = raw_image.resolve()
            if not image.is_file():
                raise FileNotFoundError(image)
            page_started = time.perf_counter()

            started = time.perf_counter()
            image_bgr = cv2.imread(str(image), cv2.IMREAD_COLOR)
            read_sec = time.perf_counter() - started
            if image_bgr is None:
                raise RuntimeError(f"Failed to read {image}")

            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            started = time.perf_counter()
            upscaled, upsampler = apply_advanced_sr(
                image_bgr,
                model_name="RealESRGAN_x4plus",
                scale=4,
                tile=args.tile,
                tile_pad=args.tile_pad,
                fp32=False,
                upsampler=upsampler,
            )
            torch.cuda.synchronize()
            sr_sec = time.perf_counter() - started

            output = output_dir / image.name
            started = time.perf_counter()
            if not cv2.imwrite(str(output), upscaled):
                raise RuntimeError(f"Failed to write {output}")
            write_sec = time.perf_counter() - started

            started = time.perf_counter()
            digest = _sha256(output)
            sha_sec = time.perf_counter() - started

            peak_allocated = int(torch.cuda.max_memory_allocated())
            peak_reserved = int(torch.cuda.max_memory_reserved())
            del upscaled, image_bgr
            cleanup = _cleanup(upsampler)

            payload["pages"].append(
                {
                    "index": index,
                    "image": str(image),
                    "output": str(output),
                    "sr_sha256": digest,
                    "reused_existing_upsampler": index > 0,
                    "read_sec": read_sec,
                    "apply_advanced_sr_sec": sr_sec,
                    "write_sec": write_sec,
                    "sha256_sec": sha_sec,
                    "page_wall_sec": time.perf_counter() - page_started,
                    "peak_allocated_bytes": peak_allocated,
                    "peak_reserved_bytes": peak_reserved,
                    "cleanup": cleanup,
                }
            )

        payload.update(
            {
                "status": "completed",
                "batch_internal_wall_sec": time.perf_counter() - batch_started,
                "retained_after_final_cleanup_allocated_bytes": int(torch.cuda.memory_allocated()),
                "retained_after_final_cleanup_reserved_bytes": int(torch.cuda.memory_reserved()),
            }
        )
    except Exception as error:  # noqa: BLE001
        payload.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "batch_internal_wall_sec": time.perf_counter() - batch_started,
            }
        )
        args.result.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    args.result.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
