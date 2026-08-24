"""Benchmark one isolated RRDBNet forward variant for Issue #284.

Profiling-only worker. It uses two real 420x420 padded tiles from page_013 and
compares candidate FP16 and rounded uint8 outputs with a baseline reference.
Each invocation runs in a fresh Python process so cuDNN state and OOM failures
are isolated between variants.
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
VARIANTS = {
    "baseline": {"benchmark": False, "channels_last": False, "batch": 1, "inference_mode": False},
    "inference_mode": {
        "benchmark": False,
        "channels_last": False,
        "batch": 1,
        "inference_mode": True,
    },
    "cudnn_benchmark": {
        "benchmark": True,
        "channels_last": False,
        "batch": 1,
        "inference_mode": False,
    },
    "channels_last": {
        "benchmark": False,
        "channels_last": True,
        "batch": 1,
        "inference_mode": False,
    },
    "channels_last_benchmark": {
        "benchmark": True,
        "channels_last": True,
        "batch": 1,
        "inference_mode": False,
    },
    "batch2": {"benchmark": False, "channels_last": False, "batch": 2, "inference_mode": False},
    "batch2_benchmark": {
        "benchmark": True,
        "channels_last": False,
        "batch": 2,
        "inference_mode": False,
    },
    "batch2_channels_last_benchmark": {
        "benchmark": True,
        "channels_last": True,
        "batch": 2,
        "inference_mode": False,
    },
}


def _require_runtime() -> None:
    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 RRDB profiling requires canonical /workspace container")
    if not torch.cuda.is_available():
        raise RuntimeError("Issue #284 RRDB profiling requires CUDA")
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
        tile=400,
        tile_pad=10,
        pre_pad=0,
        half=True,
        device=torch.device("cuda"),
    )
    return upsampler.model


def _load_tiles() -> list[torch.Tensor]:
    image = cv2.imread(str(IMAGE), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(IMAGE)
    image = image.astype(np.float32) / 255.0
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(np.transpose(image, (2, 0, 1))).float().unsqueeze(0).cuda().half()
    # Interior production tile cores (x=1/y=1 and x=2/y=1), including tile_pad=10.
    # Both are exactly 420x420, the dominant page_013 shape (54 of 88 tiles).
    tiles = [
        tensor[:, :, 390:810, 390:810],
        tensor[:, :, 390:810, 790:1210],
    ]
    if any(tuple(tile.shape) != (1, 3, 420, 420) for tile in tiles):
        raise RuntimeError(
            f"Unexpected representative tile shapes: {[tuple(t.shape) for t in tiles]}"
        )
    return tiles


def _uint8_tensor(value: torch.Tensor) -> torch.Tensor:
    return value.float().clamp(0, 1).mul(255.0).round().to(torch.uint8).cpu()


def _compare(candidate: torch.Tensor, reference: torch.Tensor) -> dict[str, Any]:
    candidate_cpu = candidate.detach().cpu()
    reference_cpu = reference.detach().cpu()
    same_shape = tuple(candidate_cpu.shape) == tuple(reference_cpu.shape)
    result: dict[str, Any] = {
        "same_shape": same_shape,
        "candidate_shape": list(candidate_cpu.shape),
        "reference_shape": list(reference_cpu.shape),
        "fp16_equal": False,
        "uint8_equal": False,
    }
    if not same_shape:
        return result
    delta = (candidate_cpu.float() - reference_cpu.float()).abs()
    result.update(
        {
            "fp16_equal": bool(torch.equal(candidate_cpu, reference_cpu)),
            "different_fp16_values": int(torch.count_nonzero(delta).item()),
            "max_abs_fp16_diff": float(delta.max().item()),
            "mean_abs_fp16_diff": float(delta.mean().item()),
            "uint8_equal": bool(
                torch.equal(_uint8_tensor(candidate_cpu), _uint8_tensor(reference_cpu))
            ),
        }
    )
    return result


def _context(inference_mode: bool):
    return torch.inference_mode() if inference_mode else torch.no_grad()


def _run_forward(model: torch.nn.Module, batch: torch.Tensor, inference_mode: bool) -> torch.Tensor:
    with _context(inference_mode):
        return model(batch)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=sorted(VARIANTS), required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()

    _require_runtime()
    args.result.parent.mkdir(parents=True, exist_ok=True)
    cfg = VARIANTS[args.variant]
    payload: dict[str, Any] = {
        "schema_version": "issue284.rrdb_forward_variant.v1",
        "status": "started",
        "variant": args.variant,
        "config": cfg,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version(),
        "device": torch.cuda.get_device_name(torch.cuda.current_device()),
        "iterations": args.iterations,
    }

    try:
        torch.backends.cudnn.benchmark = bool(cfg["benchmark"])
        torch.backends.cudnn.deterministic = False
        model = _create_model()
        tiles = _load_tiles()
        if cfg["channels_last"]:
            model = model.to(memory_format=torch.channels_last)
            tiles = [tile.contiguous(memory_format=torch.channels_last) for tile in tiles]

        if int(cfg["batch"]) == 2:
            batch = torch.cat(tiles, dim=0)
        else:
            batch = tiles[0]

        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        warmup_started = time.perf_counter()
        warmup_output = _run_forward(model, batch, bool(cfg["inference_mode"]))
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
            candidate = _run_forward(model, batch, bool(cfg["inference_mode"]))
            end_event.record()
            torch.cuda.synchronize()
            walls.append(time.perf_counter() - started)
            gpu_secs.append(float(start_event.elapsed_time(end_event)) / 1000.0)
            final_output = candidate

        if final_output is None:
            raise RuntimeError("No timed forward output")

        reference_path = args.reference.resolve()
        comparisons: list[dict[str, Any]] = []
        if args.variant == "baseline":
            with torch.no_grad():
                reference_outputs = [model(tile).detach().cpu() for tile in tiles]
            reference_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(reference_outputs, reference_path)
            if int(cfg["batch"]) == 1:
                comparisons.append(_compare(final_output, reference_outputs[0]))
        else:
            reference_outputs = torch.load(reference_path, map_location="cpu", weights_only=False)
            if not isinstance(reference_outputs, list) or len(reference_outputs) != 2:
                raise ValueError(f"Invalid reference payload: {reference_path}")
            if int(cfg["batch"]) == 2:
                comparisons = [
                    _compare(final_output[index : index + 1], reference_outputs[index])
                    for index in range(2)
                ]
            else:
                comparisons.append(_compare(final_output, reference_outputs[0]))
                second = _run_forward(model, tiles[1], bool(cfg["inference_mode"]))
                torch.cuda.synchronize()
                comparisons.append(_compare(second, reference_outputs[1]))
                del second

        per_batch_median = statistics.median(walls)
        batch_size = int(cfg["batch"])
        payload.update(
            {
                "status": "completed",
                "warmup_sec": warmup_sec,
                "wall_sec": {
                    "values": walls,
                    "mean": statistics.fmean(walls),
                    "median": per_batch_median,
                    "per_tile_median": per_batch_median / batch_size,
                },
                "gpu_sec": {
                    "values": gpu_secs,
                    "mean": statistics.fmean(gpu_secs),
                    "median": statistics.median(gpu_secs),
                    "per_tile_median": statistics.median(gpu_secs) / batch_size,
                },
                "comparisons": comparisons,
                "all_fp16_equal": all(item.get("fp16_equal") for item in comparisons),
                "all_uint8_equal": all(item.get("uint8_equal") for item in comparisons),
                "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
                "backend": {
                    "cudnn_benchmark": torch.backends.cudnn.benchmark,
                    "cudnn_deterministic": torch.backends.cudnn.deterministic,
                    "cudnn_allow_tf32": torch.backends.cudnn.allow_tf32,
                    "matmul_allow_tf32": torch.backends.cuda.matmul.allow_tf32,
                },
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
