"""Run Issue #284 batch-size 1/2/3/4 screening under the exact current SR runtime.

Each batch size runs in a fresh child process. The runner writes a compact summary
and a single ZIP bundle containing all shareable results/logs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BATCH_SIZES = (1, 2, 3, 4)
COMMON_TILE_COUNT_PAGE013 = 54


def _require_runtime() -> None:
    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 batch sweep requires canonical /workspace container")
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(f"Expected canonical pipeline Python, got {sys.executable}")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _bundle(output: Path, paths: list[Path]) -> Path:
    bundle = output / "issue284_current_batch_sweep_bundle.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.is_file():
                archive.write(path, arcname=path.name)
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--timeout-sec", type=float, default=240.0)
    args = parser.parse_args()

    _require_runtime()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output must be fresh and empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    reference = output / "batch1_reference.pt"
    records: list[dict[str, Any]] = []
    share_paths: list[Path] = []

    for batch_size in BATCH_SIZES:
        result_path = output / f"batch{batch_size}.json"
        log_path = output / f"batch{batch_size}.console.log"
        command = [
            sys.executable,
            str(ROOT / "tools/issue284/profile_current_batch_variant_worker.py"),
            "--batch-size",
            str(batch_size),
            "--reference",
            str(reference),
            "--result",
            str(result_path),
            "--iterations",
            str(args.iterations),
        ]

        started = time.perf_counter()
        timed_out = False
        returncode: int | None = None
        with log_path.open("w", encoding="utf-8") as log:
            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=args.timeout_sec,
                )
                returncode = completed.returncode
            except subprocess.TimeoutExpired:
                timed_out = True

        payload = _load_json(result_path)
        record: dict[str, Any] = {
            "batch_size": batch_size,
            "returncode": returncode,
            "timed_out": timed_out,
            "process_wall_sec": time.perf_counter() - started,
            "status": payload.get("status")
            if payload
            else ("timeout" if timed_out else "missing_result"),
            "result": str(result_path),
            "log": str(log_path),
        }
        if payload:
            record.update(
                {
                    "warmup_sec": payload.get("warmup_sec"),
                    "wall_sec": payload.get("wall_sec"),
                    "gpu_sec": payload.get("gpu_sec"),
                    "all_fp16_equal": payload.get("all_fp16_equal"),
                    "all_uint8_equal": payload.get("all_uint8_equal"),
                    "peak_allocated_bytes": payload.get("peak_allocated_bytes"),
                    "peak_reserved_bytes": payload.get("peak_reserved_bytes"),
                    "device_total_bytes": payload.get("device_total_bytes"),
                    "device_free_before_bytes": payload.get("device_free_before_bytes"),
                    "device_free_after_bytes": payload.get("device_free_after_bytes"),
                    "error_type": payload.get("error_type"),
                    "error": payload.get("error"),
                }
            )
        records.append(record)
        share_paths.extend([result_path, log_path])

        if batch_size == 1 and (not payload or payload.get("status") != "completed"):
            break

    baseline = next(
        (item for item in records if item["batch_size"] == 1 and item.get("status") == "completed"),
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
        per_tile_value = float(per_tile)
        record["speedup_vs_batch1_per_tile"] = float(baseline_per_tile) / per_tile_value
        record["reduction_vs_batch1_fraction"] = 1.0 - per_tile_value / float(baseline_per_tile)
        batch_size = int(record["batch_size"])
        batches = (COMMON_TILE_COUNT_PAGE013 + batch_size - 1) // batch_size
        record["page013_common_shape_batch_count"] = batches
        record["estimated_page013_common_shape_sec"] = batches * float(wall.get("median") or 0.0)

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
        "schema_version": "issue284.current_batch_sweep.v1",
        "fixed_runtime": {
            "channels_last": True,
            "fp16": True,
            "inference_mode": True,
            "cudnn_benchmark": False,
            "tile": 400,
            "tile_pad": 10,
            "representative_tile_shape": [1, 3, 420, 420],
        },
        "common_tile_count_page013": COMMON_TILE_COUNT_PAGE013,
        "iterations": args.iterations,
        "timeout_sec": args.timeout_sec,
        "variants": records,
        "fastest_uint8_equivalent": fastest,
        "notes": [
            "This is same-shape tile batching, not concurrent page batching.",
            "Each batch size runs in a fresh process so OOM/paging pressure does not contaminate later variants.",
            "A material winner must be validated in the full-page current runtime before production adoption.",
        ],
    }
    summary_path = output / "current_batch_sweep_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    share_paths.append(summary_path)

    bundle = _bundle(output, share_paths)
    print(json.dumps(summary, indent=2))
    print(f"share_bundle={bundle}")
    return 0 if baseline else 1


if __name__ == "__main__":
    raise SystemExit(main())
