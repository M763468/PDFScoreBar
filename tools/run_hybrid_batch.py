#!/usr/bin/env python3
"""Batch orchestrator for Hybrid Barline Detection (Docker-side)."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List

# Use the virtualenv inside the container
CONTAINER_PY = "/opt/venv_sr/bin/python"

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from homr_eval_scripts import homr_evaluator  # noqa: E402


def run_command(cmd: List[str]):
    print(f"\n[Batch Runner] Executing: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images",
        nargs="+",
        required=True,
        help="List of image paths (absolute or relative to workspace)",
    )
    parser.add_argument("--run-id", required=True, help="Identifier for this run")
    parser.add_argument(
        "--output-root",
        default="/workspace/logs/hybrid_pipeline_bench",
        help="Root directory for outputs",
    )
    parser.add_argument(
        "--gt-map", type=str, help="Optional JSON file mapping image stem to GT JSON path"
    )
    args = parser.parse_args()

    # Determine unique output directory for this run
    # timestamp = int(time.time())
    # batch_dir = Path(args.output_root) / f"{args.run_id}_{timestamp}"
    # Actually, orchestrator might have already created a directory.
    # Let's use the run-id as is if it looks like a path, otherwise create under output-root.
    if args.run_id.startswith("/"):
        batch_dir = Path(args.run_id)
    else:
        batch_dir = Path(args.output_root) / args.run_id

    batch_dir.mkdir(parents=True, exist_ok=True)
    print(f"Batch Output Directory: {batch_dir}")

    # Prepare Image List
    image_paths = [str(Path(img).resolve()) for img in args.images]
    stems = [Path(img).stem for img in args.images]

    # --- Step 1: homr Baseline Batch ---
    print("\n=== [Batch Step 1] homr Baseline ===")
    homr_evaluator.run_evaluation(
        [
            "--images",
            *image_paths,
            "--output-root",
            str(batch_dir / "baseline"),
            "--force-run-id",
            "batch",
            "--enable-segnet-cache",
        ]
    )

    # --- Step 2: homr SR Batch ---
    print("\n=== [Batch Step 2] homr SR (Real-ESRGAN x4) ===")
    homr_evaluator.run_evaluation(
        [
            "--images",
            *image_paths,
            "--output-root",
            str(batch_dir / "sr"),
            "--force-run-id",
            "batch",
            "--enable-sr",
            "--enable-segnet-cache",
        ]
    )

    # --- Step 3: OMR-DLN Batch ---
    print("\n=== [Batch Step 3] OMR-DLN SR (YOLOv8 Measures) ===")
    # Step 2 outputs SR images at batch_dir / sr / batch / <stem> / <stem>.png
    sr_root = batch_dir / "sr" / "batch"
    cmd3 = (
        [CONTAINER_PY, "/workspace/experiments/models/eval_omr_dln.py", "--images"]
        + image_paths
        + ["--output-dir", str(batch_dir / "omr_sr"), "--pre-computed-sr", str(sr_root)]
    )
    run_command(cmd3)

    # --- Step 4: Hybrid Consensus Batch ---
    print("\n=== [Batch Step 4] Hybrid Consensus Generation ===")
    hybrid_output_dir = batch_dir / "hybrid_results"
    hybrid_output_dir.mkdir(parents=True, exist_ok=True)

    for stem in stems:
        print(f"Generating hybrid results for {stem}...")
        # Paths are fixed by conventions of previous steps
        baseline_json = batch_dir / "baseline" / "batch" / stem / f"{stem}_detections.json"
        sr_json = batch_dir / "sr" / "batch" / stem / f"{stem}_detections.json"
        omr_json = batch_dir / "omr_sr" / stem / "predictions.json"

        if not baseline_json.exists() or not sr_json.exists() or not omr_json.exists():
            print(f"Warning: Missing components for {stem}. Skipping consensus.")
            continue

        output_json = hybrid_output_dir / f"{stem}_hybrid.json"

        cmd4 = [
            CONTAINER_PY,
            "/workspace/tools/generate_hybrid_results.py",
            "--baseline",
            str(baseline_json),
            "--sr",
            str(sr_json),
            "--omr",
            str(omr_json),
            "--output",
            str(output_json),
        ]

        # Add GT if map provided
        if args.gt_map and Path(args.gt_map).exists():
            with open(args.gt_map, "r") as f:
                gt_data = json.load(f)
                if stem in gt_data:
                    cmd4 += ["--gt", gt_data[stem]]

        subprocess.run(cmd4, check=True)

    print(f"\n[Batch Runner] Completed. Results in {hybrid_output_dir}")


if __name__ == "__main__":
    main()
