#!/usr/bin/env python3
"""Evaluate an existing Issue #294 A/B run against local barline ground truth."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from tools.issue294.run_same_original_ab_host import (  # noqa: E402
    CONTAINER,
    CONTAINER_ROOT,
    PIPELINE_PYTHON,
    PROJECT_ROOT,
    _restore_host_ownership,
    container_path,
    require_container,
    require_host_checkout,
)

DEFAULT_GT_ROOT = PROJECT_ROOT / "data/training/annotations"


def run(run_tag: str, ground_truth_root: Path) -> dict[str, str]:
    require_host_checkout()
    require_container()

    output_root = (PROJECT_ROOT / "logs/issue294" / run_tag).resolve()
    if not output_root.is_dir():
        raise FileNotFoundError(output_root)
    summary = output_root / "summary.json"
    if not summary.is_file():
        raise FileNotFoundError(summary)

    ground_truth_root = ground_truth_root.resolve()
    if not ground_truth_root.is_dir():
        raise FileNotFoundError(ground_truth_root)
    container_path(ground_truth_root)

    output = output_root / "gt_detection_comparison.json"
    if output.exists():
        raise FileExistsError(output)

    command = [
        "docker",
        "exec",
        "-w",
        str(CONTAINER_ROOT),
        "-e",
        "PYTHONPATH=/workspace",
        CONTAINER,
        PIPELINE_PYTHON,
        "tools/issue294/evaluate_existing_ab_against_gt.py",
        "--summary",
        str(container_path(summary)),
        "--ground-truth-root",
        str(container_path(ground_truth_root)),
        "--output",
        str(container_path(output)),
    ]
    try:
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    finally:
        _restore_host_ownership(output_root)

    if not output.is_file():
        raise FileNotFoundError(output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise ValueError(f"Incomplete GT comparison: {output}")
    return {"gt_detection_comparison": str(output)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--ground-truth-root", type=Path, default=DEFAULT_GT_ROOT)
    args = parser.parse_args()
    try:
        result = run(args.run_tag, args.ground_truth_root)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": "completed", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
