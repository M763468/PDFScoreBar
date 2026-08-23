"""Run isolated Real-ESRGAN tile-size experiments for Issue #284.

Each candidate runs in a fresh child Python process so a CUDA OOM does not poison
subsequent candidates. The child profiler compares its in-memory SR output with
the retained post-#285 production baseline and records peak CUDA memory.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from tools.issue284.profile_realesrgan_hotpath import CANONICAL_IMAGE, require_canonical_container

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TILES = (480, 512, 576, 640)


def _parse_tiles(value: str) -> list[int]:
    tiles = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not tiles or any(tile <= 0 for tile in tiles):
        raise argparse.ArgumentTypeError("tiles must be a comma-separated list of positive integers")
    return tiles


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=CANONICAL_IMAGE)
    parser.add_argument("--tiles", type=_parse_tiles, default=list(DEFAULT_TILES))
    parser.add_argument("--tile-pad", type=int, default=10)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_canonical_container()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    image = args.image.resolve()
    baseline = args.baseline_summary.resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    if not baseline.is_file():
        raise FileNotFoundError(baseline)

    records: list[dict[str, Any]] = []
    for tile in args.tiles:
        result_path = output / f"tile{tile}.json"
        log_path = output / f"tile{tile}.console.log"
        command = [
            sys.executable,
            str(ROOT / "tools/issue284/profile_realesrgan_hotpath.py"),
            "--image",
            str(image),
            "--tile",
            str(tile),
            "--tile-pad",
            str(args.tile_pad),
            "--result",
            str(result_path),
            "--compare-baseline-summary",
            str(baseline),
        ]
        started = time.perf_counter()
        with log_path.open("w", encoding="utf-8") as log_file:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
        payload = _load_json(result_path)
        record: dict[str, Any] = {
            "tile": tile,
            "returncode": completed.returncode,
            "wall_sec": time.perf_counter() - started,
            "result": str(result_path),
            "log": str(log_path),
            "status": payload.get("status") if payload else "missing_result",
        }
        if payload:
            record.update(
                {
                    "profiled_enhance_total_wall_sec": payload.get("profiled_enhance_total_wall_sec"),
                    "geometry": payload.get("geometry"),
                    "memory": payload.get("memory") or payload.get("memory_at_failure"),
                    "comparison": payload.get("comparison"),
                    "error_type": payload.get("error_type"),
                    "error": payload.get("error"),
                }
            )
        records.append(record)

    completed_records = [item for item in records if item.get("status") == "completed"]
    fastest = min(
        completed_records,
        key=lambda item: float(item["profiled_enhance_total_wall_sec"]),
        default=None,
    )
    summary = {
        "schema_version": "issue284.tile_sweep.v1",
        "image": str(image),
        "baseline_summary": str(baseline),
        "tile_pad": args.tile_pad,
        "candidates": records,
        "fastest_completed": fastest,
    }
    summary_path = output / "tile_sweep_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    # A candidate OOM is data, not a sweep-runner failure. Fail only if none completed.
    return 0 if completed_records else 1


if __name__ == "__main__":
    raise SystemExit(main())
