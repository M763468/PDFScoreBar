"""Profile one full-page Real-ESRGAN CPU-stitch variant for Issue #284.

Profiling-only worker. Unlike pinned RealESRGANer.tile_process(), this experiment
never allocates the full x4 FP16 output on CUDA. Each accepted tile core is
converted to BGR/HWC uint8 on CUDA, copied to CPU, and stitched into the final
uint8 image. This isolates the combined effects of output staging, channels-last
RRDB inference, cuDNN benchmark mode, and tile size while comparing the result
mechanically with retained production SR output.
"""

from __future__ import annotations

import argparse
import json
import math
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
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

from tools.issue284.profile_realesrgan_hotpath import compare_images, resolve_compare_image, sha256

IMAGE = ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png"
WEIGHTS = ROOT / "external/realesrgan/weights/RealESRGAN_x4plus.pth"


def _require_runtime() -> None:
    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 SR stitch profiling requires canonical /workspace container")
    if not torch.cuda.is_available():
        raise RuntimeError("Issue #284 SR stitch profiling requires CUDA")
    if not WEIGHTS.is_file():
        raise FileNotFoundError(WEIGHTS)


def _create_model(*, channels_last: bool) -> torch.nn.Module:
    model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        num_feat=64,
        num_block=23,
        num_grow_ch=32,
        scale=4,
    )
    upsampler = RealESRGANer(
        scale=4,
        model_path=str(WEIGHTS),
        model=model,
        tile=400,
        tile_pad=10,
        pre_pad=0,
        half=True,
        device=torch.device("cuda"),
    )
    result = upsampler.model
    if channels_last:
        result = result.to(memory_format=torch.channels_last)
    return result


def _gpu_uint8_bgr_hwc(core: torch.Tensor) -> torch.Tensor:
    converted = core.float()
    converted.clamp_(0, 1).mul_(255.0).round_()
    converted = converted.to(torch.uint8)
    return converted[0, [2, 1, 0], :, :].permute(1, 2, 0).contiguous()


def _profile(
    image_bgr: np.ndarray,
    model: torch.nn.Module,
    *,
    tile: int,
    tile_pad: int,
    channels_last: bool,
) -> tuple[np.ndarray, dict[str, Any]]:
    timings: dict[str, float] = {}

    started = time.perf_counter()
    image = image_bgr.astype(np.float32)
    image /= 255.0
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    timings["cpu_normalize_bgr_to_rgb_sec"] = time.perf_counter() - started

    torch.cuda.synchronize()
    started = time.perf_counter()
    img = torch.from_numpy(np.transpose(image, (2, 0, 1))).float().unsqueeze(0).cuda().half()
    if channels_last:
        img = img.contiguous(memory_format=torch.channels_last)
    torch.cuda.synchronize()
    timings["tensor_h2d_and_format_sec"] = time.perf_counter() - started

    _, _, height, width = img.shape
    output = np.empty((height * 4, width * 4, 3), dtype=np.uint8)
    tiles_x = math.ceil(width / tile)
    tiles_y = math.ceil(height / tile)

    forward_sec = 0.0
    tile_format_sec = 0.0
    convert_copy_stitch_sec = 0.0
    torch.cuda.synchronize()
    tile_loop_started = time.perf_counter()
    with torch.inference_mode():
        for y in range(tiles_y):
            for x in range(tiles_x):
                input_start_x = x * tile
                input_end_x = min(input_start_x + tile, width)
                input_start_y = y * tile
                input_end_y = min(input_start_y + tile, height)
                input_start_x_pad = max(input_start_x - tile_pad, 0)
                input_end_x_pad = min(input_end_x + tile_pad, width)
                input_start_y_pad = max(input_start_y - tile_pad, 0)
                input_end_y_pad = min(input_end_y + tile_pad, height)
                input_tile_width = input_end_x - input_start_x
                input_tile_height = input_end_y - input_start_y

                input_tile = img[
                    :,
                    :,
                    input_start_y_pad:input_end_y_pad,
                    input_start_x_pad:input_end_x_pad,
                ]
                if channels_last:
                    torch.cuda.synchronize()
                    fmt_started = time.perf_counter()
                    input_tile = input_tile.contiguous(memory_format=torch.channels_last)
                    torch.cuda.synchronize()
                    tile_format_sec += time.perf_counter() - fmt_started

                torch.cuda.synchronize()
                forward_started = time.perf_counter()
                output_tile = model(input_tile)
                torch.cuda.synchronize()
                forward_sec += time.perf_counter() - forward_started

                output_start_x = input_start_x * 4
                output_end_x = input_end_x * 4
                output_start_y = input_start_y * 4
                output_end_y = input_end_y * 4
                output_start_x_tile = (input_start_x - input_start_x_pad) * 4
                output_start_y_tile = (input_start_y - input_start_y_pad) * 4
                output_end_x_tile = output_start_x_tile + input_tile_width * 4
                output_end_y_tile = output_start_y_tile + input_tile_height * 4
                core = output_tile[
                    :,
                    :,
                    output_start_y_tile:output_end_y_tile,
                    output_start_x_tile:output_end_x_tile,
                ]

                torch.cuda.synchronize()
                copy_started = time.perf_counter()
                core_u8 = _gpu_uint8_bgr_hwc(core)
                core_cpu = core_u8.cpu().numpy()
                output[output_start_y:output_end_y, output_start_x:output_end_x] = core_cpu
                torch.cuda.synchronize()
                convert_copy_stitch_sec += time.perf_counter() - copy_started
                del output_tile, core, core_u8, core_cpu, input_tile

    torch.cuda.synchronize()
    timings["tile_loop_wall_sec"] = time.perf_counter() - tile_loop_started
    timings["tile_forward_synchronized_sec"] = forward_sec
    timings["tile_channels_last_format_synchronized_sec"] = tile_format_sec
    timings["tile_gpu_uint8_d2h_stitch_synchronized_sec"] = convert_copy_stitch_sec
    return output, {
        "timings": timings,
        "geometry": {
            "tile": tile,
            "tile_pad": tile_pad,
            "tiles_x": tiles_x,
            "tiles_y": tiles_y,
            "tile_count": tiles_x * tiles_y,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=IMAGE)
    parser.add_argument("--tile", type=int, default=400)
    parser.add_argument("--tile-pad", type=int, default=10)
    parser.add_argument("--channels-last", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    _require_runtime()
    image_path = args.image.resolve()
    baseline = args.baseline_summary.resolve()
    reference = resolve_compare_image(baseline, image_path)
    if reference is None:
        raise FileNotFoundError(f"No retained baseline SR image for {image_path.name}")
    image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise FileNotFoundError(image_path)
    args.result.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "schema_version": "issue284.sr_stitch_variant.v1",
        "status": "started",
        "image": str(image_path),
        "image_sha256": sha256(image_path),
        "tile": args.tile,
        "tile_pad": args.tile_pad,
        "channels_last": args.channels_last,
        "benchmark": args.benchmark,
        "inference_mode": True,
        "output_mode": "gpu_uint8_cpu_stitch",
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version(),
        "device": torch.cuda.get_device_name(torch.cuda.current_device()),
    }

    try:
        torch.backends.cudnn.benchmark = args.benchmark
        torch.backends.cudnn.deterministic = False
        torch.cuda.empty_cache()
        model = _create_model(channels_last=args.channels_last)
        torch.cuda.synchronize()
        model_allocated = int(torch.cuda.memory_allocated())
        model_reserved = int(torch.cuda.memory_reserved())
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
        total = time.perf_counter() - started
        payload.update(profile)
        payload.update(
            {
                "status": "completed",
                "profiled_total_wall_sec": total,
                "comparison": compare_images(output, reference),
                "memory": {
                    "after_model_allocated_bytes": model_allocated,
                    "after_model_reserved_bytes": model_reserved,
                    "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                    "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
                    "device_total_bytes": int(torch.cuda.get_device_properties(0).total_memory),
                },
            }
        )
    except Exception as error:  # noqa: BLE001
        payload.update(
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
        args.result.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    args.result.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
