"""Measure reusable SR batch worker wall time against the current per-page baseline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMAGES = (
    ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_012.png",
    ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png",
    ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va/page_014.png",
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", nargs="+", type=Path, default=list(DEFAULT_IMAGES))
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tile", type=int, default=400)
    parser.add_argument("--tile-pad", type=int, default=10)
    args = parser.parse_args()

    baseline = _load_json(args.baseline_summary.resolve())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    worker_result = output / "worker_result.json"
    worker_log = output / "worker.console.log"
    sr_output = output / "sr"

    images = [path.resolve() for path in args.images]
    command = [
        sys.executable,
        str(ROOT / "tools/issue284/sr_batch_probe_worker.py"),
        "--images",
        *[str(path) for path in images],
        "--output-dir",
        str(sr_output),
        "--result",
        str(worker_result),
        "--tile",
        str(args.tile),
        "--tile-pad",
        str(args.tile_pad),
    ]

    started = time.perf_counter()
    with worker_log.open("w", encoding="utf-8") as log_file:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
    child_wall = time.perf_counter() - started

    worker = _load_json(worker_result) if worker_result.is_file() else None
    stage_summary = baseline.get("stage_summary", {})
    current = stage_summary.get("current_support.current_sr_subprocess", {})
    baseline_total = float(current.get("total_sec", 0.0))

    baseline_sha_by_name = {
        Path(str(item["image"])).name: str(item["sr_sha256"])
        for item in baseline.get("sr_outputs", [])
        if item.get("image") and item.get("sr_sha256")
    }
    pages = worker.get("pages", []) if worker else []
    comparisons = []
    for page in pages:
        name = Path(str(page.get("image", ""))).name
        actual = page.get("sr_sha256")
        expected = baseline_sha_by_name.get(name)
        comparisons.append(
            {
                "image": name,
                "candidate_sha256": actual,
                "baseline_sha256": expected,
                "sha256_equal": bool(actual and expected and actual == expected),
            }
        )

    result = {
        "schema_version": "issue284.sr_batch_process_profile.v1",
        "status": "completed" if completed.returncode == 0 and worker else "failed",
        "command": command,
        "returncode": completed.returncode,
        "child_process_wall_sec": child_wall,
        "worker_result": str(worker_result),
        "worker_log": str(worker_log),
        "current_three_page_sr_subprocess_total_sec": baseline_total,
        "candidate_three_page_sr_batch_process_sec": child_wall,
        "saved_sec": baseline_total - child_wall,
        "reduction_fraction": ((baseline_total - child_wall) / baseline_total)
        if baseline_total
        else None,
        "comparisons": comparisons,
        "all_sha256_equal": bool(comparisons) and all(item["sha256_equal"] for item in comparisons),
        "worker": worker,
    }
    summary = output / "batch_process_summary.json"
    summary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "completed" and result["all_sha256_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
