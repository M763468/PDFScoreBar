"""Detection step orchestration."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from importlib import import_module

# Pre-import torch to avoid symbol conflict with onnxruntime-gpu
try:
    import_module("torch")
except ImportError:
    pass
from pathlib import Path
from typing import Any, Dict, List

from src.pipeline.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.hybrid_consensus import load_json_boxes, phase4_hybrid_consensus

logger = logging.getLogger(__name__)
from src.pipeline.config import get_nested
from src.pipeline.io import ensure_dir
from src.pipeline.probe_scan import run_probe_scan_batch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROBE_SCAN_KWARG_KEYS = (
    "probe_width",
    "use_peak_relative_ratio",
    "peak_ratio_min",
    "extend_scale",
    "extend_max_ratio",
    "extend_top_max_ratio",
    "extend_bottom_max_ratio",
    "min_peak_distance",
    "min_peak_distance_unit_ratio",
    "refine_window",
    "max_per_band",
    "band_height_mode",
    "band_height_scale",
    "band_height_min",
    "x_merge_tol",
    "x_merge_tol_unit_ratio",
    "post_emit_unit_normalized_box",
    "post_norm_width_unit_ratio",
    "post_norm_height_unit_ratio",
    "post_apply_if_width_gt_unit_ratio",
    "post_apply_if_height_gt_unit_ratio",
    "post_vertical_min_height_unit_ratio",
    "post_vertical_min_aspect_ratio",
    "post_split_wide_candidates",
    "post_split_min_width_unit_ratio",
    "post_split_box_width_unit_ratio",
    "post_split_peak_distance_unit_ratio",
    "post_split_peak_prominence_ratio",
    "scan_fallback_pred_band",
    "scan_disable_non_scan_extend",
    "scan_disable_existing_suppression",
    "scan_existing_min_vertical_iou",
    "scan_peak_band_height",
    "scan_center_on_peak",
    "scan_x_peak_rescue",
    "scan_x_peak_window",
    "scan_x_peak_ratio_min",
    "scan_x_peak_max_overhang",
    "scan_x_peak_rescue_mode",
    "scan_x_peak_segment_height",
    "scan_x_peak_segment_pass_ratio",
    "scan_x_peak_segment_source",
    "scan_x_peak_ignore_staff_peak",
    "scan_x_peak_ignore_radius",
    "scan_rightmost_rescue",
    "scan_rightmost_tolerance",
    "scan_rightmost_min_rows",
    "scan_rightmost_min_ratio",
    "scan_gap_rescue",
    "scan_gap_threshold_ratio",
    "scan_gap_rescue_min_ratio",
    "scan_gap_margin_ratio",
    "scan_ratio_rel_rescue",
    "scan_ratio_rel_rescue_min",
    "scan_ratio_rel_rescue_xpeak_min",
    "scan_ratio_rel_rescue_max_overhang",
    "divisi_rescue",
    "divisi_dist_ratio",
    "divisi_align_tol",
    "divisi_align_min_count",
)


def _run_hybrid_detection_in_process(
    det_cfg: Dict[str, Any],
    images: List[Path],
    run_id: str,
    *,
    dry_run: bool,
) -> Dict[str, Any]:
    from src.homr_eval_scripts import homr_evaluator

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

    logger.info("--- Step 2.1: Hybrid Detection (In-Process homr baseline/SR) ---")

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

    logger.info("--- Step 2.1b: OMR-DLN SR (Subprocess) ---")
    sr_root = hybrid_output_dir / "sr" / "batch"
    omr_cmd = (
        [sys.executable, "experiments/models/eval_omr_dln.py", "--images"]
        + image_paths
        + ["--output-dir", str(hybrid_output_dir / "omr_sr"), "--pre-computed-sr", str(sr_root)]
    )
    commands.append(omr_cmd)
    if not dry_run:
        subprocess.run(omr_cmd, check=True)

    logger.info("--- Step 2.1c: Hybrid Consensus Generation ---")
    hybrid_results_dir = hybrid_output_dir / "hybrid_results"
    ensure_dir(hybrid_results_dir)

    for stem in stems:
        baseline_json = hybrid_output_dir / "baseline" / "batch" / stem / f"{stem}_detections.json"
        sr_json = hybrid_output_dir / "sr" / "batch" / stem / f"{stem}_detections.json"
        omr_json = hybrid_output_dir / "omr_sr" / stem / "predictions.json"

        if not baseline_json.exists() or not sr_json.exists() or not omr_json.exists():
            logger.warning(f"Missing components for {stem}. Skipping consensus.")
            continue

        output_json = hybrid_results_dir / f"{stem}_hybrid.json"
        consensus_cmd = [
            "inprocess:hybrid_consensus",
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
            baseline_boxes = load_json_boxes(baseline_json)
            sr_boxes = load_json_boxes(sr_json)
            omr_boxes = load_json_boxes(omr_json)
            hybrid_preds = phase4_hybrid_consensus(
                baseline_boxes=baseline_boxes,
                sr_boxes=sr_boxes,
                omr_boxes=omr_boxes,
            )
            output_json.write_text(json.dumps(hybrid_preds, indent=2))

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

    logger.info("--- Step 2.2: Probe Scan (Host) ---")
    probe_output_root = Path(f"logs/full_pipeline_runs/{run_id}/intermediate/probe_scan")
    ensure_dir(probe_output_root)

    image_root = get_nested(config, "inputs", "pdf_to_images", "output_dir")

    cmd_probe = [
        "inprocess:probe_scan",
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
    detect_probe_kwargs = {
        key: det_cfg[key]
        for key in _PROBE_SCAN_KWARG_KEYS
        if key in det_cfg and det_cfg.get(key) is not None
    }
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
    for key, value in sorted(detect_probe_kwargs.items()):
        cmd_probe += [f"--{key.replace('_', '-')}", str(value)]

    if det_cfg.get("probe_skip_existing"):
        cmd_probe.append("--skip-existing")

    if not dry_run:
        run_probe_scan_batch(
            images=images,
            output_root=probe_output_root,
            bands_from=hybrid_output_dir,
            staff_mask_dir=hybrid_output_dir,
            ink_threshold=int(det_cfg.get("ink_threshold", 230)),
            min_ratio=float(det_cfg.get("min_ratio", 0.70)),
            min_height_ratio=float(det_cfg.get("min_height_ratio", 0.012)),
            min_width_ratio=(
                float(det_cfg.get("min_width_ratio"))
                if det_cfg.get("min_width_ratio") is not None
                else None
            ),
            score_name=(
                str(det_cfg.get("probe_score_name")) if det_cfg.get("probe_score_name") else None
            ),
            detect_probe_kwargs=detect_probe_kwargs,
            probe_row_filter_mode=(
                str(det_cfg.get("probe_row_filter_mode"))
                if det_cfg.get("probe_row_filter_mode") is not None
                else None
            ),
            probe_endpoint_x_scale=(
                float(det_cfg.get("probe_endpoint_x_scale"))
                if det_cfg.get("probe_endpoint_x_scale") is not None
                else None
            ),
            probe_endpoint_y_scale=(
                float(det_cfg.get("probe_endpoint_y_scale"))
                if det_cfg.get("probe_endpoint_y_scale") is not None
                else None
            ),
            skip_existing=bool(det_cfg.get("probe_skip_existing")),
        )
    commands.append(cmd_probe)

    logger.info("--- Step 2.3: CNN Scoring (Host) ---")
    cnn_model = det_cfg.get("cnn_model_path")
    if not cnn_model:
        raise ValueError("detection.cnn_model_path is required.")

    cmd_score = [
        "inprocess:cnn_scoring",
        "--logs",
        str(probe_output_root),
        "--model",
        str(cnn_model),
        "--threshold",
        str(det_cfg.get("cnn_threshold", 0.1)),
    ]
    if not dry_run:
        run_cnn_scoring_batch(
            probe_output_root=probe_output_root,
            images=images,
            model_path=Path(cnn_model),
            threshold=float(det_cfg.get("cnn_threshold", 0.1)),
            score_name=(
                str(det_cfg.get("probe_score_name")) if det_cfg.get("probe_score_name") else None
            ),
        )
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
        # Match either original stem or proxy-suffixed stem (from Proxy Inference)
        # Examples: page_001_debug_3_staff.png or page_001_proxy_debug_3_staff.png
        for path in hybrid_output_dir.rglob("*_debug_3_staff.png"):
            name = path.name
            stem = name.replace("_proxy_debug_3_staff.png", "").replace("_debug_3_staff.png", "")
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
            logger.warning(f"Warning: Barlines not found for {page_id} (stem: {stem})")
            barlines_path = Path("MISSING_BARLINES.json")

        if not staff_mask_path or not staff_mask_path.exists():
            logger.warning(f"Warning: Staff mask not found for {page_id} (stem: {stem})")
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
