"""Profile current Issue #284 SR tile execution with a GPU utilization timeline.

This profiling-only worker reproduces the accepted current runtime choices for one
representative page: RealESRGAN_x4plus FP16, channels-last, tile400/tile_pad10,
batch size 1, inference mode, and GPU-uint8/CPU stitching.  It records synchronized
per-tile forward/copy timing while sampling nvidia-smi in parallel.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np

from src.pipeline.detection.current_sr_runtime import CurrentX4SRRuntime

IMAGE = ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png"
GPU_QUERY_FIELDS = (
    "utilization.gpu",
    "utilization.memory",
    "memory.used",
    "memory.free",
    "power.draw",
    "clocks.current.sm",
    "clocks.current.memory",
)


def _require_runtime() -> None:
    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 SR timeline profiling requires canonical /workspace container")
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(f"Expected canonical pipeline Python, got {sys.executable}")


def _sha256_bytes(value: np.ndarray) -> str:
    return hashlib.sha256(value.tobytes()).hexdigest()


def _compare(candidate: np.ndarray, reference_path: Path) -> dict[str, Any]:
    reference = cv2.imread(str(reference_path), cv2.IMREAD_UNCHANGED)
    if reference is None:
        raise FileNotFoundError(reference_path)
    same_shape = candidate.shape == reference.shape
    result: dict[str, Any] = {
        "reference": str(reference_path),
        "same_shape": same_shape,
        "array_equal": False,
        "candidate_shape": list(candidate.shape),
        "reference_shape": list(reference.shape),
    }
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


class NvidiaSmiSampler:
    def __init__(self, *, zero: float, interval_ms: int = 100) -> None:
        self.zero = zero
        self.interval_ms = interval_ms
        self.samples: list[dict[str, float]] = []
        self.error: str | None = None
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        query = ",".join(GPU_QUERY_FIELDS)
        command = [
            "nvidia-smi",
            f"--query-gpu={query}",
            "--format=csv,noheader,nounits",
            "-lms",
            str(self.interval_ms),
        ]
        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as error:
            self.error = str(error)
            return
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        for line in self._process.stdout:
            received = time.perf_counter() - self.zero
            parts = [item.strip() for item in line.strip().split(",")]
            if len(parts) != len(GPU_QUERY_FIELDS):
                continue
            try:
                values = [float(value) for value in parts]
            except ValueError:
                continue
            self.samples.append(
                {
                    "relative_sec": received,
                    **dict(zip(GPU_QUERY_FIELDS, values, strict=True)),
                }
            )

    def stop(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=2)
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._process.returncode not in (0, -15, 143):
            stderr = ""
            if self._process.stderr is not None:
                stderr = self._process.stderr.read().strip()
            if stderr:
                self.error = stderr

    def write_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = ["relative_sec", *GPU_QUERY_FIELDS]
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.samples)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def _sample_summary(samples: list[dict[str, float]]) -> dict[str, Any]:
    result: dict[str, Any] = {"sample_count": len(samples)}
    for field in GPU_QUERY_FIELDS:
        values = [sample[field] for sample in samples]
        result[field] = {
            "mean": statistics.fmean(values) if values else None,
            "p50": statistics.median(values) if values else None,
            "p95": _percentile(values, 0.95),
            "max": max(values) if values else None,
            "min": min(values) if values else None,
        }
    return result


def _warmup(runtime: CurrentX4SRRuntime, image_bgr: np.ndarray) -> None:
    torch = runtime.torch
    image = image_bgr.astype(np.float32) / 255.0
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(np.transpose(image, (2, 0, 1))).float().unsqueeze(0)
    tensor = tensor.to(runtime.device).half().contiguous(memory_format=torch.channels_last)
    _, _, height, width = tensor.shape
    start_y = min(400, max(0, height - 420))
    start_x = min(400, max(0, width - 420))
    tile = tensor[:, :, start_y : start_y + 420, start_x : start_x + 420]
    tile = tile.contiguous(memory_format=torch.channels_last)
    with torch.inference_mode():
        output = runtime.model(tile)
    torch.cuda.synchronize()
    del output, tile, tensor


def _profile(
    runtime: CurrentX4SRRuntime,
    image_bgr: np.ndarray,
    *,
    sampler: NvidiaSmiSampler,
    zero: float,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    torch = runtime.torch
    image = image_bgr.astype(np.float32) / 255.0
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(np.transpose(image, (2, 0, 1))).float().unsqueeze(0)
    tensor = tensor.to(runtime.device).half().contiguous(memory_format=torch.channels_last)

    _, _, height, width = tensor.shape
    tile = runtime._effective_tile(image_bgr)  # noqa: SLF001 - exact profiling contract
    tiles_x = math.ceil(width / tile)
    tiles_y = math.ceil(height / tile)
    output = np.empty((height * 4, width * 4, 3), dtype=np.uint8)
    records: list[dict[str, Any]] = []

    torch.cuda.synchronize()
    sampler.start()
    try:
        with torch.inference_mode():
            index = 0
            for y in range(tiles_y):
                for x in range(tiles_x):
                    record: dict[str, Any] = {
                        "index": index,
                        "x": x,
                        "y": y,
                        "tile_start_sec": time.perf_counter() - zero,
                    }
                    input_start_x = x * tile
                    input_end_x = min(input_start_x + tile, width)
                    input_start_y = y * tile
                    input_end_y = min(input_start_y + tile, height)
                    input_start_x_pad = max(input_start_x - runtime.tile_pad, 0)
                    input_end_x_pad = min(input_end_x + runtime.tile_pad, width)
                    input_start_y_pad = max(input_start_y - runtime.tile_pad, 0)
                    input_end_y_pad = min(input_end_y + runtime.tile_pad, height)
                    input_tile_width = input_end_x - input_start_x
                    input_tile_height = input_end_y - input_start_y

                    input_tile = tensor[
                        :,
                        :,
                        input_start_y_pad:input_end_y_pad,
                        input_start_x_pad:input_end_x_pad,
                    ]
                    record["input_shape"] = list(input_tile.shape)

                    torch.cuda.synchronize()
                    started = time.perf_counter()
                    input_tile = input_tile.contiguous(memory_format=torch.channels_last)
                    torch.cuda.synchronize()
                    record["format_wall_sec"] = time.perf_counter() - started

                    torch.cuda.synchronize()
                    forward_started = time.perf_counter()
                    output_tile = runtime.model(input_tile)
                    torch.cuda.synchronize()
                    record["forward_start_sec"] = forward_started - zero
                    record["forward_end_sec"] = time.perf_counter() - zero
                    record["forward_wall_sec"] = record["forward_end_sec"] - record["forward_start_sec"]

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

                    copy_started = time.perf_counter()
                    core_u8 = core.float()
                    core_u8.clamp_(0, 1).mul_(255.0).round_()
                    core_u8 = core_u8.to(torch.uint8)
                    core_u8 = core_u8[0, [2, 1, 0], :, :].permute(1, 2, 0).contiguous()
                    core_cpu = core_u8.cpu().numpy()
                    output[output_start_y:output_end_y, output_start_x:output_end_x] = core_cpu
                    torch.cuda.synchronize()
                    record["copy_start_sec"] = copy_started - zero
                    record["copy_end_sec"] = time.perf_counter() - zero
                    record["copy_wall_sec"] = record["copy_end_sec"] - record["copy_start_sec"]
                    record["allocated_bytes_after"] = int(torch.cuda.memory_allocated())
                    record["reserved_bytes_after"] = int(torch.cuda.memory_reserved())
                    record["tile_end_sec"] = time.perf_counter() - zero
                    records.append(record)
                    index += 1
                    del output_tile, core, core_u8, core_cpu, input_tile
    finally:
        sampler.stop()
    del tensor
    return output, records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=IMAGE)
    parser.add_argument("--reference-image", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--gpu-samples", type=Path, required=True)
    parser.add_argument("--sample-interval-ms", type=int, default=100)
    args = parser.parse_args()

    _require_runtime()
    image_path = args.image.resolve()
    reference_path = args.reference_image.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    if not reference_path.is_file():
        raise FileNotFoundError(reference_path)
    image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise FileNotFoundError(image_path)

    payload: dict[str, Any] = {
        "schema_version": "issue284.current_sr_timeline.v1",
        "status": "started",
        "image": str(image_path),
        "reference_image": str(reference_path),
        "sample_interval_ms": args.sample_interval_ms,
    }
    try:
        runtime = CurrentX4SRRuntime(tile=400, tile_pad=10, fp32=False, channels_last=True)
        torch = runtime.torch
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = False
        _warmup(runtime, image_bgr)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

        zero = time.perf_counter()
        sampler = NvidiaSmiSampler(zero=zero, interval_ms=args.sample_interval_ms)
        output, tiles = _profile(runtime, image_bgr, sampler=sampler, zero=zero)
        total_wall = time.perf_counter() - zero
        sampler.write_csv(args.gpu_samples.resolve())

        forward_values = [float(item["forward_wall_sec"]) for item in tiles]
        copy_values = [float(item["copy_wall_sec"]) for item in tiles]
        format_values = [float(item["format_wall_sec"]) for item in tiles]
        payload.update(
            {
                "status": "completed",
                "runtime": runtime.metadata(),
                "total_wall_sec": total_wall,
                "tile_count": len(tiles),
                "tile_timeline": tiles,
                "timing_summary": {
                    "forward_total_sec": sum(forward_values),
                    "forward_mean_sec": statistics.fmean(forward_values),
                    "forward_p50_sec": statistics.median(forward_values),
                    "copy_total_sec": sum(copy_values),
                    "copy_mean_sec": statistics.fmean(copy_values),
                    "copy_p50_sec": statistics.median(copy_values),
                    "format_total_sec": sum(format_values),
                },
                "gpu_samples": {
                    "path": str(args.gpu_samples.resolve()),
                    "error": sampler.error,
                    "summary": _sample_summary(sampler.samples),
                },
                "memory": {
                    "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                    "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
                    "device_total_bytes": int(torch.cuda.get_device_properties(0).total_memory),
                },
                "comparison": _compare(output, reference_path),
                "output_array_sha256": _sha256_bytes(output),
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
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
