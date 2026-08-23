"""Run isolated full-page SR stitch variants for Issue #284.

The first NCHW/tile400 candidate is the fidelity gate for GPU-uint8 CPU stitching.
Channels-last variants then test full-page performance and pixel propagation. Each
candidate runs in a fresh process so CUDA allocator/cuDNN state is isolated.
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

from tools.issue284.profile_realesrgan_hotpath import CANONICAL_IMAGE, require_canonical_container

VARIANTS = (
    ("nchw_tile400_stitch", 400, False, False),
    ("channels_last_tile400_stitch", 400, True, False),
    ("channels_last_benchmark_tile400_stitch", 400, True, True),
    ("channels_last_tile480_stitch", 480, True, False),
    ("channels_last_tile512_stitch", 512, True, False),
)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=CANONICAL_IMAGE)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=float, default=180.0)
    args = parser.parse_args()

    require_canonical_container()
    image = args.image.resolve()
    baseline = args.baseline_summary.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not image.is_file():
        raise FileNotFoundError(image)
    if not baseline.is_file():
        raise FileNotFoundError(baseline)

    records: list[dict[str, Any]] = []
    for name, tile, channels_last, benchmark in VARIANTS:
        result_path = output / f"{name}.json"
        log_path = output / f"{name}.console.log"
        command = [
            sys.executable,
            str(ROOT / "tools/issue284/profile_sr_stitch_variant_worker.py"),
            "--image",
            str(image),
            "--tile",
            str(tile),
            "--tile-pad",
            "10",
            "--baseline-summary",
            str(baseline),
            "--result",
            str(result_path),
        ]
        if channels_last:
            command.append("--channels-last")
        if benchmark:
            command.append("--benchmark")

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
        process_wall = time.perf_counter() - started
        payload = _load(result_path)
        record: dict[str, Any] = {
            "variant": name,
            "tile": tile,
            "channels_last": channels_last,
            "benchmark": benchmark,
            "returncode": returncode,
            "timed_out": timed_out,
            "process_wall_sec": process_wall,
            "result": str(result_path),
            "log": str(log_path),
            "status": payload.get("status") if payload else ("timed_out" if timed_out else "missing_result"),
        }
        if payload:
            record.update(
                {
                    "profiled_total_wall_sec": payload.get("profiled_total_wall_sec"),
                    "timings": payload.get("timings"),
                    "geometry": payload.get("geometry"),
                    "memory": payload.get("memory") or payload.get("memory_at_failure"),
                    "comparison": payload.get("comparison"),
                    "error_type": payload.get("error_type"),
                    "error": payload.get("error"),
                }
            )
        records.append(record)

    completed_records = [item for item in records if item.get("status") == "completed"]
    faithful = [item for item in completed_records if (item.get("comparison") or {}).get("array_equal")]
    fastest = min(
        completed_records,
        key=lambda item: float(item["profiled_total_wall_sec"]),
        default=None,
    )
    fastest_faithful = min(
        faithful,
        key=lambda item: float(item["profiled_total_wall_sec"]),
        default=None,
    )
    summary = {
        "schema_version": "issue284.sr_stitch_variant_sweep.v1",
        "image": str(image),
        "baseline_summary": str(baseline),
        "candidates": records,
        "fastest_completed": fastest,
        "fastest_array_equal": fastest_faithful,
        "notes": [
            "nchw_tile400_stitch must be array-equal before CPU-stitch timings are trusted.",
            "Pixel-changing channels-last/tile candidates require downstream propagation gates before adoption.",
            "This runner measures one full page per fresh process; cuDNN benchmark startup is therefore intentionally visible.",
        ],
    }
    summary_path = output / "sr_stitch_variant_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if completed_records else 1


if __name__ == "__main__":
    raise SystemExit(main())
