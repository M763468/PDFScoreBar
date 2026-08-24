"""Attribute the Real-ESRGAN x4 enhance hot path for Issue #284.

This is profiling-only code. It reproduces the pinned RealESRGANer x4 RGB path
without modifying the installed package, adds CUDA-event timing around each tile
forward/merge, and preserves the production operation order closely enough to
compare the generated uint8 output mechanically with a retained production SR
image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_IMAGE = ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png"
DEFAULT_CANDIDATE_TILES = (400, 480, 512, 576, 640, 768, 800, 960, 1024)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_canonical_container() -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Issue #284 profiling must run inside pdfscore_pipeline_gpu")
    if ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError(f"Expected repository at /workspace, got {ROOT}")
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(f"Expected /opt/venv_pipeline interpreter, got {sys.executable}")
    if not torch.cuda.is_available():
        raise RuntimeError("Issue #284 hot-path profiling requires CUDA")


def tile_geometry(height: int, width: int, tile: int, tile_pad: int) -> dict[str, Any]:
    if tile <= 0:
        return {
            "tile": tile,
            "tile_pad": tile_pad,
            "tiles_x": 1,
            "tiles_y": 1,
            "tile_count": 1,
            "core_input_pixels": height * width,
            "padded_input_pixels": height * width,
            "padded_pixel_overhead_fraction": 0.0,
            "padded_shape_counts": {f"{height}x{width}": 1},
        }
    tiles_x = math.ceil(width / tile)
    tiles_y = math.ceil(height / tile)
    padded_pixels = 0
    shape_counts: Counter[str] = Counter()
    for y in range(tiles_y):
        for x in range(tiles_x):
            start_x = x * tile
            end_x = min(start_x + tile, width)
            start_y = y * tile
            end_y = min(start_y + tile, height)
            start_x_pad = max(start_x - tile_pad, 0)
            end_x_pad = min(end_x + tile_pad, width)
            start_y_pad = max(start_y - tile_pad, 0)
            end_y_pad = min(end_y + tile_pad, height)
            padded_h = end_y_pad - start_y_pad
            padded_w = end_x_pad - start_x_pad
            padded_pixels += padded_h * padded_w
            shape_counts[f"{padded_h}x{padded_w}"] += 1
    core_pixels = height * width
    return {
        "tile": tile,
        "tile_pad": tile_pad,
        "tiles_x": tiles_x,
        "tiles_y": tiles_y,
        "tile_count": tiles_x * tiles_y,
        "core_input_pixels": core_pixels,
        "padded_input_pixels": padded_pixels,
        "padded_pixel_overhead_fraction": padded_pixels / core_pixels - 1.0,
        "padded_shape_counts": dict(sorted(shape_counts.items())),
    }


def timed_cpu(function):
    started = time.perf_counter()
    value = function()
    return value, time.perf_counter() - started


def synchronized_wall(function) -> tuple[Any, float, float]:
    """Return value, operation+wait wall time, and empty post-sync wall time."""
    torch.cuda.synchronize()
    started = time.perf_counter()
    value = function()
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    empty_started = time.perf_counter()
    torch.cuda.synchronize()
    empty_sync = time.perf_counter() - empty_started
    return value, elapsed, empty_sync


def event_stats(events: list[tuple[torch.cuda.Event, torch.cuda.Event]]) -> dict[str, Any]:
    values = [float(start.elapsed_time(end)) / 1000.0 for start, end in events]
    if not values:
        return {"count": 0, "total_sec": 0.0, "mean_sec": None, "median_sec": None, "max_sec": None}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * 0.95) - 1))
    return {
        "count": len(values),
        "total_sec": sum(values),
        "mean_sec": statistics.fmean(values),
        "median_sec": statistics.median(values),
        "p95_sec": ordered[p95_index],
        "min_sec": ordered[0],
        "max_sec": ordered[-1],
        "per_tile_sec": values,
    }


def resolve_compare_image(summary_path: Path, image: Path) -> Path | None:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    for item in payload.get("sr_outputs", []):
        source = item.get("image")
        sr_image = item.get("sr_image")
        if source and sr_image and Path(str(source)).name == image.name:
            path = Path(str(sr_image))
            if path.is_file():
                return path
    return None


def compare_images(candidate: np.ndarray, reference_path: Path) -> dict[str, Any]:
    reference = cv2.imread(str(reference_path), cv2.IMREAD_UNCHANGED)
    if reference is None:
        raise FileNotFoundError(reference_path)
    same_shape = candidate.shape == reference.shape
    result: dict[str, Any] = {
        "reference": str(reference_path),
        "reference_sha256": sha256(reference_path),
        "candidate_shape": list(candidate.shape),
        "reference_shape": list(reference.shape),
        "same_shape": same_shape,
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


def create_upsampler(
    tile: int, tile_pad: int, pre_pad: int, fp32: bool
) -> tuple[RealESRGANer, float]:
    model_path = ROOT / "external/realesrgan/weights/RealESRGAN_x4plus.pth"
    if not model_path.is_file():
        raise FileNotFoundError(f"Production Real-ESRGAN weight path is missing: {model_path}")
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
    started = time.perf_counter()
    upsampler = RealESRGANer(
        scale=4,
        model_path=str(model_path),
        model=model,
        tile=tile,
        tile_pad=tile_pad,
        pre_pad=pre_pad,
        half=not fp32,
        device=torch.device("cuda"),
    )
    torch.cuda.synchronize()
    return upsampler, time.perf_counter() - started


def profile_enhance(
    image_bgr: np.ndarray,
    upsampler: RealESRGANer,
    *,
    tile: int,
    tile_pad: int,
    pre_pad: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError(f"Expected BGR image with 3 channels, got {image_bgr.shape}")

    timings: dict[str, Any] = {}
    image, timings["input_astype_float32_sec"] = timed_cpu(lambda: image_bgr.astype(np.float32))
    maximum, timings["input_max_scan_sec"] = timed_cpu(lambda: float(np.max(image)))
    if maximum > 256:
        raise ValueError("The representative production path is expected to be 8-bit")
    image, timings["input_normalize_sec"] = timed_cpu(lambda: image / 255.0)
    image, timings["input_bgr_to_rgb_sec"] = timed_cpu(
        lambda: cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    )

    cpu_tensor, timings["preprocess_numpy_to_cpu_tensor_sec"] = timed_cpu(
        lambda: torch.from_numpy(np.transpose(image, (2, 0, 1))).float().unsqueeze(0)
    )
    gpu_tensor, timings["preprocess_h2d_sec"], timings["preprocess_h2d_empty_sync_sec"] = (
        synchronized_wall(lambda: cpu_tensor.to(torch.device("cuda")))
    )
    if upsampler.half:
        (
            gpu_tensor,
            timings["preprocess_half_conversion_sec"],
            timings["preprocess_half_empty_sync_sec"],
        ) = synchronized_wall(gpu_tensor.half)
    else:
        timings["preprocess_half_conversion_sec"] = 0.0
        timings["preprocess_half_empty_sync_sec"] = 0.0

    if pre_pad:
        from torch.nn import functional as F

        (
            gpu_tensor,
            timings["preprocess_pre_pad_sec"],
            timings["preprocess_pre_pad_empty_sync_sec"],
        ) = synchronized_wall(lambda: F.pad(gpu_tensor, (0, pre_pad, 0, pre_pad), "reflect"))
    else:
        timings["preprocess_pre_pad_sec"] = 0.0
        timings["preprocess_pre_pad_empty_sync_sec"] = 0.0

    # scale=4 has no mod padding in the pinned RealESRGANer implementation.
    batch, channel, height, width = gpu_tensor.shape
    geometry = tile_geometry(height, width, tile, tile_pad)
    output_shape = (batch, channel, height * 4, width * 4)
    (
        output,
        timings["tile_output_allocation_sec"],
        timings["tile_output_allocation_empty_sync_sec"],
    ) = synchronized_wall(lambda: gpu_tensor.new_zeros(output_shape))

    forward_events: list[tuple[torch.cuda.Event, torch.cuda.Event]] = []
    merge_events: list[tuple[torch.cuda.Event, torch.cuda.Event]] = []
    extraction_cpu_sec = 0.0
    launch_started = time.perf_counter()
    tiles_x = int(geometry["tiles_x"])
    tiles_y = int(geometry["tiles_y"])
    with torch.no_grad():
        for y in range(tiles_y):
            for x in range(tiles_x):
                extraction_started = time.perf_counter()
                input_start_x = x * tile if tile > 0 else 0
                input_end_x = min(input_start_x + tile, width) if tile > 0 else width
                input_start_y = y * tile if tile > 0 else 0
                input_end_y = min(input_start_y + tile, height) if tile > 0 else height
                input_start_x_pad = max(input_start_x - tile_pad, 0)
                input_end_x_pad = min(input_end_x + tile_pad, width)
                input_start_y_pad = max(input_start_y - tile_pad, 0)
                input_end_y_pad = min(input_end_y + tile_pad, height)
                input_tile_width = input_end_x - input_start_x
                input_tile_height = input_end_y - input_start_y
                input_tile = gpu_tensor[
                    :, :, input_start_y_pad:input_end_y_pad, input_start_x_pad:input_end_x_pad
                ]
                extraction_cpu_sec += time.perf_counter() - extraction_started

                forward_start = torch.cuda.Event(enable_timing=True)
                forward_end = torch.cuda.Event(enable_timing=True)
                forward_start.record()
                output_tile = upsampler.model(input_tile)
                forward_end.record()
                forward_events.append((forward_start, forward_end))

                output_start_x = input_start_x * 4
                output_end_x = input_end_x * 4
                output_start_y = input_start_y * 4
                output_end_y = input_end_y * 4
                output_start_x_tile = (input_start_x - input_start_x_pad) * 4
                output_end_x_tile = output_start_x_tile + input_tile_width * 4
                output_start_y_tile = (input_start_y - input_start_y_pad) * 4
                output_end_y_tile = output_start_y_tile + input_tile_height * 4

                merge_start = torch.cuda.Event(enable_timing=True)
                merge_end = torch.cuda.Event(enable_timing=True)
                merge_start.record()
                output[:, :, output_start_y:output_end_y, output_start_x:output_end_x] = (
                    output_tile[
                        :,
                        :,
                        output_start_y_tile:output_end_y_tile,
                        output_start_x_tile:output_end_x_tile,
                    ]
                )
                merge_end.record()
                merge_events.append((merge_start, merge_end))

    launch_wall = time.perf_counter() - launch_started
    sync_started = time.perf_counter()
    torch.cuda.synchronize()
    sync_wait = time.perf_counter() - sync_started
    timings["tile_cpu_extraction_sec"] = extraction_cpu_sec
    timings["tile_launch_wall_before_final_sync_sec"] = launch_wall
    timings["tile_final_sync_wait_sec"] = sync_wait
    timings["tile_process_synchronized_wall_sec"] = launch_wall + sync_wait
    timings["tile_forward_gpu"] = event_stats(forward_events)
    timings["tile_merge_gpu"] = event_stats(merge_events)

    post = output
    if pre_pad:
        _, _, out_h, out_w = post.size()
        post = post[:, :, 0 : out_h - pre_pad * 4, 0 : out_w - pre_pad * 4]
    timings["postprocess_crop_cpu_sec"] = (
        0.0  # slicing above is a view; retained for ledger clarity
    )

    (
        gpu_float,
        timings["output_half_to_float_sec"],
        timings["output_half_to_float_empty_sync_sec"],
    ) = synchronized_wall(lambda: post.data.squeeze().float())
    cpu_float, timings["output_d2h_copy_sec"], timings["output_d2h_empty_sync_sec"] = (
        synchronized_wall(gpu_float.cpu)
    )
    cpu_float, timings["output_cpu_clamp_sec"] = timed_cpu(lambda: cpu_float.clamp_(0, 1))
    output_np, timings["output_tensor_to_numpy_sec"] = timed_cpu(cpu_float.numpy)
    output_np, timings["output_channel_reorder_transpose_sec"] = timed_cpu(
        lambda: np.transpose(output_np[[2, 1, 0], :, :], (1, 2, 0))
    )
    output_uint8, timings["output_round_uint8_sec"] = timed_cpu(
        lambda: (output_np * 255.0).round().astype(np.uint8)
    )

    return output_uint8, {"timings": timings, "geometry": geometry}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=CANONICAL_IMAGE)
    parser.add_argument("--tile", type=int, default=400)
    parser.add_argument("--tile-pad", type=int, default=10)
    parser.add_argument("--pre-pad", type=int, default=0)
    parser.add_argument("--fp32", action="store_true")
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output-image", type=Path)
    parser.add_argument("--compare-image", type=Path)
    parser.add_argument("--compare-baseline-summary", type=Path)
    parser.add_argument("--geometry-only", action="store_true")
    args = parser.parse_args()

    require_canonical_container()
    image_path = args.image.resolve()
    image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise FileNotFoundError(image_path)
    height, width = image_bgr.shape[:2]
    candidate_geometry = [
        tile_geometry(height + args.pre_pad, width + args.pre_pad, tile, args.tile_pad)
        for tile in DEFAULT_CANDIDATE_TILES
    ]
    result: dict[str, Any] = {
        "schema_version": "issue284.realesrgan_hotpath_profile.v1",
        "status": "started",
        "image": str(image_path),
        "image_sha256": sha256(image_path),
        "input_shape": list(image_bgr.shape),
        "tile": args.tile,
        "tile_pad": args.tile_pad,
        "pre_pad": args.pre_pad,
        "fp32": args.fp32,
        "candidate_geometry": candidate_geometry,
        "device": torch.cuda.get_device_name(torch.cuda.current_device()),
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)

    if args.geometry_only:
        result["status"] = "completed_geometry_only"
        args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0

    try:
        torch.cuda.empty_cache()
        upsampler, init_sec = create_upsampler(args.tile, args.tile_pad, args.pre_pad, args.fp32)
        torch.cuda.synchronize()
        model_allocated = int(torch.cuda.memory_allocated())
        model_reserved = int(torch.cuda.memory_reserved())
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        output, profile = profile_enhance(
            image_bgr,
            upsampler,
            tile=args.tile,
            tile_pad=args.tile_pad,
            pre_pad=args.pre_pad,
        )
        synchronized_total = time.perf_counter() - started
        torch.cuda.synchronize()
        result.update(profile)
        result.update(
            {
                "status": "completed",
                "model_initialization_sec": init_sec,
                "profiled_enhance_total_wall_sec": synchronized_total,
                "memory": {
                    "after_model_allocated_bytes": model_allocated,
                    "after_model_reserved_bytes": model_reserved,
                    "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                    "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
                    "device_total_bytes": int(torch.cuda.get_device_properties(0).total_memory),
                },
                "output_shape": list(output.shape),
            }
        )

        reference_path = args.compare_image.resolve() if args.compare_image else None
        if reference_path is None and args.compare_baseline_summary:
            reference_path = resolve_compare_image(
                args.compare_baseline_summary.resolve(), image_path
            )
        if reference_path is not None:
            result["comparison"] = compare_images(output, reference_path)

        if args.output_image:
            output_path = args.output_image.resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(output_path), output):
                raise RuntimeError(f"Failed to write profiled SR image: {output_path}")
            result["output_image"] = str(output_path)
            result["output_image_sha256"] = sha256(output_path)
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
