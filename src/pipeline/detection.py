"""Detection step orchestration."""

from __future__ import annotations

import subprocess
import sys

# Pre-import torch to avoid symbol conflict with onnxruntime-gpu
try:
    import torch
except ImportError:
    pass
from pathlib import Path
from typing import Any, Dict, List

from src.homr_eval_scripts import homr_evaluator
from src.pipeline.config import get_nested
from src.pipeline.io import ensure_dir

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_hybrid_detection_in_process(
    det_cfg: Dict[str, Any],
    images: List[Path],
    run_id: str,
    *,
    dry_run: bool,
) -> Dict[str, Any]:
    # Ensure external/homr is in sys.path for training module imports
    homr_path = str((PROJECT_ROOT / "external" / "homr").resolve())
    if homr_path not in sys.path:
        sys.path.insert(0, homr_path)

    hybrid_root = Path(det_cfg.get("hybrid_output_root", "logs/hybrid_generalization"))
    hybrid_output_dir = hybrid_root / run_id
    ensure_dir(hybrid_output_dir)

    image_paths = [str(path.resolve()) for path in images]
    stems = [path.stem for path in images]

    commands: List[List[str]] = []

    print("--- Step 2.1: Hybrid Detection (In-Process homr baseline/SR) ---")

    baseline_args = [
        "--images",
        *image_paths,
        "--output-root",
        str(hybrid_output_dir / "baseline"),
        "--force-run-id",
        "batch",
        "--enable-segnet-cache",
    ]
    commands.append(["homr_evaluator.run_evaluation", *baseline_args])
    if not dry_run:
        homr_evaluator.run_evaluation(baseline_args)

    sr_args = [
        "--images",
        *image_paths,
        "--output-root",
        str(hybrid_output_dir / "sr"),
        "--force-run-id",
        "batch",
        "--enable-sr",
        "--enable-segnet-cache",
    ]
    commands.append(["homr_evaluator.run_evaluation", *sr_args])
    if not dry_run:
        homr_evaluator.run_evaluation(sr_args)

    print("--- Step 2.1b: OMR-DLN SR (Subprocess) ---")
    sr_root = hybrid_output_dir / "sr" / "batch"
    omr_cmd = (
        [sys.executable, "experiments/models/eval_omr_dln.py", "--images"]
        + image_paths
        + ["--output-dir", str(hybrid_output_dir / "omr_sr"), "--pre-computed-sr", str(sr_root)]
    )
    commands.append(omr_cmd)
    if not dry_run:
        subprocess.run(omr_cmd, check=True)

    print("--- Step 2.1c: Hybrid Consensus Generation ---")
    hybrid_results_dir = hybrid_output_dir / "hybrid_results"
    ensure_dir(hybrid_results_dir)

    for stem in stems:
        baseline_json = hybrid_output_dir / "baseline" / "batch" / stem / f"{stem}_detections.json"
        sr_json = hybrid_output_dir / "sr" / "batch" / stem / f"{stem}_detections.json"
        omr_json = hybrid_output_dir / "omr_sr" / stem / "predictions.json"

        if not baseline_json.exists() or not sr_json.exists() or not omr_json.exists():
            print(f"Warning: Missing components for {stem}. Skipping consensus.")
            continue

        output_json = hybrid_results_dir / f"{stem}_hybrid.json"
        consensus_cmd = [
            sys.executable,
            "tools/generate_hybrid_results.py",
            "--baseline",
            str(baseline_json),
            "--sr",
            str(sr_json),
            "--omr",
            str(omr_json),
            "--output",
            str(output_json),
        ]
        commands.append(consensus_cmd)
        if not dry_run:
            subprocess.run(consensus_cmd, check=True)

    return {"commands": commands, "hybrid_output_dir": hybrid_output_dir}


def run_detection_step(
    config: Dict[str, Any],
    images: List[Path],
    page_ids: List[str],
    run_id: str,
    *,
    dry_run: bool,
) -> Dict[str, Any]:
    """Run hybrid detection -> probe scan -> CNN scoring."""
    det_cfg = get_nested(config, "detection", default={}) or {}
    hybrid_run_id = run_id
    hybrid_result = _run_hybrid_detection_in_process(
        det_cfg, images, hybrid_run_id, dry_run=dry_run
    )
    commands = hybrid_result["commands"]
    hybrid_output_dir = hybrid_result["hybrid_output_dir"]

    print("--- Step 2.2: Probe Scan (Host) ---")
    probe_output_root = Path(f"logs/full_pipeline_runs/{run_id}/intermediate/probe_scan")
    ensure_dir(probe_output_root)

    image_root = get_nested(config, "inputs", "pdf_to_images", "output_dir")

    cmd_probe = [
        sys.executable,
        "tools/run_eval_experiment.py",
        "--image-root",
        str(image_root),
        "--output-root",
        str(probe_output_root),
        "--bands-from",
        str(hybrid_output_dir),
        "--staff-mask-dir",
        str(hybrid_output_dir),
        "--ink-threshold",
        str(det_cfg.get("ink_threshold", 230)),
        "--min-ratio",
        str(det_cfg.get("min_ratio", 0.70)),
        "--min-height-ratio",
        str(det_cfg.get("min_height_ratio", 0.012)),
    ]
    if det_cfg.get("min_width_ratio") is not None:
        cmd_probe += ["--min-width-ratio", str(det_cfg.get("min_width_ratio"))]
    if det_cfg.get("probe_row_filter_mode"):
        cmd_probe += ["--probe-row-filter-mode", str(det_cfg.get("probe_row_filter_mode"))]
    if det_cfg.get("probe_endpoint_x_scale") is not None:
        cmd_probe += ["--probe-endpoint-x-scale", str(det_cfg.get("probe_endpoint_x_scale"))]
    if det_cfg.get("probe_endpoint_y_scale") is not None:
        cmd_probe += ["--probe-endpoint-y-scale", str(det_cfg.get("probe_endpoint_y_scale"))]
    if det_cfg.get("probe_score_name"):
        cmd_probe += ["--score-name", str(det_cfg.get("probe_score_name"))]

    if det_cfg.get("probe_skip_existing"):
        cmd_probe.append("--skip-existing")

    subprocess.run(cmd_probe, check=not dry_run)
    commands.append(cmd_probe)

    print("--- Step 2.3: CNN Scoring (Host) ---")
    cnn_model = det_cfg.get("cnn_model_path")
    if not cnn_model:
        raise ValueError("detection.cnn_model_path is required.")

    cmd_score = [
        sys.executable,
        "tools/cnn_classifier/score_candidates_batch.py",
        "--logs",
        str(probe_output_root),
        "--model",
        str(cnn_model),
        "--threshold",
        str(det_cfg.get("cnn_threshold", 0.1)),
    ]
    subprocess.run(cmd_score, check=not dry_run)
    commands.append(cmd_score)

    return {
        "commands": commands,
        "hybrid_output_dir": hybrid_output_dir,
        "probe_output_dir": probe_output_root,
    }


def resolve_paths_from_detection(
    probe_output_dir: Path, hybrid_output_dir: Path, page_ids: List[str], images: List[Path]
) -> List[Dict[str, str]]:
    resolved: List[Dict[str, str]] = []

    staff_mask_map: Dict[str, Path] = {}
    if hybrid_output_dir.exists():
        for path in hybrid_output_dir.rglob("*_debug_3_staff.png"):
            stem = path.name.replace("_debug_3_staff.png", "")
            staff_mask_map[stem] = path

    for page_id, img_path in zip(page_ids, images):
        stem = img_path.stem

        candidate_dirs = list(probe_output_dir.glob(f"*_{stem}"))
        if not candidate_dirs:
            candidate_dirs = list(probe_output_dir.glob(f"*{stem}*"))

        barlines_path = None
        if candidate_dirs:
            target_dir = candidate_dirs[0]
            barlines_path = target_dir / "pipeline2_no_peak_filtered_cnn.json"

        if not barlines_path or not barlines_path.exists():
            hybrid_batch_json = hybrid_output_dir / "hybrid_results" / f"{stem}_hybrid.json"
            if hybrid_batch_json.exists():
                barlines_path = hybrid_batch_json

        staff_mask_path = staff_mask_map.get(stem)

        if not barlines_path or not barlines_path.exists():
            print(f"Warning: Barlines not found for {page_id} (stem: {stem})")
            barlines_path = Path("MISSING_BARLINES.json")

        if not staff_mask_path or not staff_mask_path.exists():
            print(f"Warning: Staff mask not found for {page_id} (stem: {stem})")
            staff_mask_path = Path("MISSING_STAFF_MASK.png")

        resolved.append(
            {
                "page_id": page_id,
                "page_run": stem,
                "barlines_json": str(barlines_path),
                "staff_mask": str(staff_mask_path),
            }
        )

    return resolved


def resolve_barlines_and_masks_config(
    config: Dict[str, Any],
    page_ids: List[str],
    page_runs: List[str],
    *,
    excluded_page_ids: set[str] | None = None,
) -> List[Dict[str, str]]:
    barlines_root = get_nested(config, "inputs", "barlines_root")
    barlines_pattern = get_nested(config, "inputs", "barlines_pattern")
    staff_mask_pattern = get_nested(config, "inputs", "staff_mask_pattern")
    if not barlines_root or not barlines_pattern or not staff_mask_pattern:
        raise ValueError("inputs.barlines_root/pattern and inputs.staff_mask_pattern are required.")

    resolved = []
    for page_id, page_run in zip(page_ids, page_runs):
        if excluded_page_ids and page_id in excluded_page_ids:
            resolved.append(
                {
                    "page_id": page_id,
                    "page_run": page_run,
                    "barlines_json": "MISSING_BARLINES.json",
                    "staff_mask": "MISSING_STAFF_MASK.png",
                }
            )
            continue

        barlines_path = Path(barlines_root) / barlines_pattern.format(
            page_run=page_run, page_id=page_id
        )
        staff_mask_path = Path(barlines_root) / staff_mask_pattern.format(
            page_run=page_run, page_id=page_id
        )

        resolved.append(
            {
                "page_id": page_id,
                "page_run": page_run,
                "barlines_json": str(barlines_path),
                "staff_mask": str(staff_mask_path),
            }
        )
    return resolved
