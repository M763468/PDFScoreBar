"""Profile one same-shape RRDB tile batch under the exact current Issue #284 runtime.

This is profiling-only code. It fixes the accepted current execution choices
(channels-last, FP16, inference_mode, cudnn_benchmark=False, tile400/tile_pad10)
and varies only same-shape tile batch size from 1 through 4.
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
import numpy as np
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

IMAGE = ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png"
WEIGHTS = ROOT / "external/realesrgan/weights/RealESRGAN_x4plus.pth"
TILE_SIZE = 400
TILE_PAD = 10
TILE_SHAPE = (1, 3, 420, 420)


def _require_runtime() -> None:
    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 batch profiling requires canonical /workspace container")
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(f"Expected canonical pipeline Python, got {sys.executable}")
    if not torch.cuda.is_available():
        raise RuntimeError("Issue #284 batch profiling requires CUDA")
    if not WEIGHTS.is_file():
        raise FileNotFoundError(WEIGHTS)


def _create_model() -> torch.nn.Module:
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
        tile=TILE_SIZE,
        tile_pad=TILE_PAD,
        pre_pad=0,
        half=True,
        device=torch.device("cuda"),
    )
    return upsampler.model.to(memory_format=torch.channels_last)


def _load_tiles() -> list[torch.Tensor]:
    image = cv2.imread(str(IMAGE), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(IMAGE)
    image = image.astype(np.float32) / 255.0
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(np.transpose(image, (2, 0, 1))).float().unsqueeze(0).cuda().half()

    # Four interior production tile regions from one row. Each includes tile_pad=10
    # and therefore has the dominant 420x420 shape used by page_013.
    tiles = [
        tensor[:, :, 390:810, 390:810],
        tensor[:, :, 390:810, 790:1210],
        tensor[:, :, 390:810, 1190:1610],
        tensor[:, :, 390:810, 1590:2010],
    ]
    actual = [tuple(tile.shape) for tile in tiles]
    if any(shape != TILE_SHAPE for shape in actual):
        raise RuntimeError(f"Unexpected representative tile shapes: {actual}")
    return [tile.contiguous(memory_format=torch.channels_last) for tile in tiles]


def _uint8(value: torch.Tensor) -> torch.Tensor:
    return value.float().clamp(0, 1).mul(255.0).round().to(torch.uint8).cpu()


def _compare(candidate: torch.Tensor, reference: torch.Tensor) -> dict[str, Any]:
    candidate_cpu = candidate.detach().cpu()
    reference_cpu = reference.detach().cpu()
    same_shape = tuple(candidate_cpu.shape) == tuple(reference_cpu.shape)
    result: dict[str, Any] = {
        "same_shape": same_shape,
        "fp16_equal": False,
        "uint8_equal": False,
    }
    if not same_shape:
        return result
    delta = (candidate_cpu.float() - reference_cpu.float()).abs()
    candidate_u8 = _uint8(candidate_cpu)
    reference_u8 = _uint8(reference_cpu)
    result.update(
        {
            "fp16_equal": bool(torch.equal(candidate_cpu, reference_cpu)),
            "different_fp16_values": int(torch.count_nonzero(delta).item()),
            "max_abs_fp16_diff": float(delta.max().item()),
            "mean_abs_fp16_diff": float(delta.mean().item()),
            "uint8_equal": bool(torch.equal(candidate_u8, reference_u8)),
            "different_uint8_values": int(torch.count_nonzero(candidate_u8 != reference_u8).item()),
            "max_abs_uint8_diff": int(
                (candidate_u8.to(torch.int16) - reference_u8.to(torch.int16)).abs().max().item()
            ),
        }
    )
    return result


def _forward(model: torch.nn.Module, batch: torch.Tensor) -> torch.Tensor:
    with torch.inference_mode():
        return model(batch)


def _save_reference(model: torch.nn.Module, tiles: list[torch.Tensor], path: Path) -> None:
    with torch.inference_mode():
        outputs = [model(tile).detach().cpu() for tile in tiles]
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(outputs, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()

    _require_runtime()
    args.result.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "issue284.current_batch_variant.v1",
        "status": "started",
        "batch_size": args.batch_size,
        "image": str(IMAGE),
        "tile": TILE_SIZE,
        "tile_pad": TILE_PAD,
        "tile_shape": list(TILE_SHAPE),
        "channels_last": True,
        "fp16": True,
        "inference_mode": True,
        "cudnn_benchmark": False,
        "iterations": args.iterations,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version(),
        "device": torch.cuda.get_device_name(torch.cuda.current_device()),
    }

    try:
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = False
        model = _create_model()
        tiles = _load_tiles()
        batch = torch.cat(tiles[: args.batch_size], dim=0).contiguous(
            memory_format=torch.channels_last
        )

        reference_path = args.reference.resolve()
        if args.batch_size == 1:
            _save_reference(model, tiles, reference_path)
        if not reference_path.is_file():
            raise FileNotFoundError(reference_path)
        references = torch.load(reference_path, map_location="cpu", weights_only=False)
        if not isinstance(references, list) or len(references) != 4:
            raise ValueError(f"Invalid batch reference payload: {reference_path}")

        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        free_before, total = torch.cuda.mem_get_info()

        torch.cuda.synchronize()
        warmup_started = time.perf_counter()
        warmup_output = _forward(model, batch)
        torch.cuda.synchronize()
        warmup_sec = time.perf_counter() - warmup_started
        del warmup_output

        walls: list[float] = []
        gpu_secs: list[float] = []
        final_output: torch.Tensor | None = None
        for _ in range(args.iterations):
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            torch.cuda.synchronize()
            started = time.perf_counter()
            start_event.record()
            candidate = _forward(model, batch)
            end_event.record()
            torch.cuda.synchronize()
            walls.append(time.perf_counter() - started)
            gpu_secs.append(float(start_event.elapsed_time(end_event)) / 1000.0)
            final_output = candidate

        if final_output is None:
            raise RuntimeError("No timed batch output")

        comparisons = [
            _compare(final_output[index : index + 1], references[index])
            for index in range(args.batch_size)
        ]
        free_after, _ = torch.cuda.mem_get_info()
        median_batch = statistics.median(walls)
        median_gpu = statistics.median(gpu_secs)
        payload.update(
            {
                "status": "completed",
                "warmup_sec": warmup_sec,
                "wall_sec": {
                    "values": walls,
                    "mean": statistics.fmean(walls),
                    "median": median_batch,
                    "per_tile_median": median_batch / args.batch_size,
                },
                "gpu_sec": {
                    "values": gpu_secs,
                    "mean": statistics.fmean(gpu_secs),
                    "median": median_gpu,
                    "per_tile_median": median_gpu / args.batch_size,
                },
                "comparisons": comparisons,
                "all_fp16_equal": all(item["fp16_equal"] for item in comparisons),
                "all_uint8_equal": all(item["uint8_equal"] for item in comparisons),
                "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
                "device_total_bytes": int(total),
                "device_free_before_bytes": int(free_before),
                "device_free_after_bytes": int(free_after),
            }
        )
    except Exception as error:  # noqa: BLE001
        payload.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "allocated_bytes_at_failure": int(torch.cuda.memory_allocated()),
                "reserved_bytes_at_failure": int(torch.cuda.memory_reserved()),
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
