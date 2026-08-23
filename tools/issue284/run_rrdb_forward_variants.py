"""Run isolated RRDBNet forward microbenchmarks for Issue #284.

The sweep intentionally uses short representative-tile runs before any full-page
experiments. Each variant is a fresh process so cuDNN autotune state and CUDA OOM
failures do not contaminate other candidates.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VARIANTS = (
    "baseline",
    "inference_mode",
    "cudnn_benchmark",
    "channels_last",
    "channels_last_benchmark",
    "batch2",
    "batch2_benchmark",
    "batch2_channels_last_benchmark",
)
COMMON_TILE_COUNT_PAGE013 = 54


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--timeout-sec", type=int, default=180)
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    reference = output / "baseline_reference.pt"
    records: list[dict[str, Any]] = []

    for variant in VARIANTS:
        result_path = output / f"{variant}.json"
        log_path = output / f"{variant}.console.log"
        command = [
            sys.executable,
            str(ROOT / "tools/issue284/profile_rrdb_forward_variant_worker.py"),
            "--variant",
            variant,
            "--reference",
            str(reference),
            "--result",
            str(result_path),
            "--iterations",
            str(args.iterations),
        ]
        started = time.perf_counter()
        timed_out = False
        with log_path.open("w", encoding="utf-8") as log_file:
            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=args.timeout_sec,
                )
                returncode: int | None = completed.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                returncode = None
        payload = _load_json(result_path)
        record: dict[str, Any] = {
            "variant": variant,
            "returncode": returncode,
            "timed_out": timed_out,
            "process_wall_sec": time.perf_counter() - started,
            "result": str(result_path),
            "log": str(log_path),
            "status": payload.get("status") if payload else ("timeout" if timed_out else "missing_result"),
        }
        if payload:
            record.update(
                {
                    "config": payload.get("config"),
                    "torch_version": payload.get("torch_version"),
                    "torch_cuda_version": payload.get("torch_cuda_version"),
                    "cudnn_version": payload.get("cudnn_version"),
                    "device": payload.get("device"),
                    "warmup_sec": payload.get("warmup_sec"),
                    "wall_sec": payload.get("wall_sec"),
                    "gpu_sec": payload.get("gpu_sec"),
                    "all_fp16_equal": payload.get("all_fp16_equal"),
                    "all_uint8_equal": payload.get("all_uint8_equal"),
                    "peak_allocated_bytes": payload.get("peak_allocated_bytes"),
                    "peak_reserved_bytes": payload.get("peak_reserved_bytes"),
                    "backend": payload.get("backend"),
                    "error_type": payload.get("error_type"),
                    "error": payload.get("error"),
                }
            )
        records.append(record)
        if variant == "baseline" and (not payload or payload.get("status") != "completed"):
            break

    baseline = next(
        (item for item in records if item["variant"] == "baseline" and item["status"] == "completed"),
        None,
    )
    baseline_per_tile = None
    if baseline and isinstance(baseline.get("wall_sec"), dict):
        baseline_per_tile = baseline["wall_sec"].get("per_tile_median")

    for record in records:
        wall = record.get("wall_sec")
        if not isinstance(wall, dict) or baseline_per_tile in (None, 0):
            continue
        per_tile = wall.get("per_tile_median")
        if per_tile is None:
            continue
        record["steady_state_speedup_vs_baseline"] = float(baseline_per_tile) / float(per_tile)
        record["steady_state_reduction_fraction"] = 1.0 - float(per_tile) / float(baseline_per_tile)
        batch_size = int((record.get("config") or {}).get("batch", 1))
        batches = (COMMON_TILE_COUNT_PAGE013 + batch_size - 1) // batch_size
        warmup = float(record.get("warmup_sec") or 0.0)
        median_batch = float(wall.get("median") or 0.0)
        # Approximation only for the dominant 420x420 shape. Full-page validation follows
        # for any candidate that is materially faster and uint8-equivalent.
        record["estimated_page013_common_shape_sec"] = warmup + max(0, batches - 1) * median_batch
        record["page013_common_shape_batch_count"] = batches

    eligible = [
        item
        for item in records
        if item.get("status") == "completed"
        and item.get("all_uint8_equal") is True
        and isinstance(item.get("wall_sec"), dict)
    ]
    fastest = min(
        eligible,
        key=lambda item: float(item["wall_sec"]["per_tile_median"]),
        default=None,
    )
    summary = {
        "schema_version": "issue284.rrdb_forward_variant_sweep.v1",
        "common_tile_shape": [1, 3, 420, 420],
        "common_tile_count_page013": COMMON_TILE_COUNT_PAGE013,
        "iterations": args.iterations,
        "variants": records,
        "fastest_uint8_equivalent": fastest,
        "notes": [
            "This is a representative-tile screening benchmark, not a production timing gate.",
            "cudnn benchmark warmup cost is reported separately and must be amortized across repeated shapes.",
            "Any promising variant must reproduce the full production SR image before adoption.",
        ],
    }
    summary_path = output / "rrdb_forward_variant_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if baseline else 1


if __name__ == "__main__":
    raise SystemExit(main())
