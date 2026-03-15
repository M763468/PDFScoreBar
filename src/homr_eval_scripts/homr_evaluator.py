#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import torch
except ImportError:
    pass


import cv2
import numpy as np

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


from common.preprocessing import apply_advanced_sr
from common.thin_barline_finder import ThinBarlineConfig, detect_thin_vertical_runs
from homr.main import ProcessingConfig, download_weights
from homr.music_xml_generator import XmlGeneratorArguments

REPO_ROOT = Path(__file__).resolve().parents[2]
if __name__ != "__main__":
    REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
_HOMR_CANDIDATES = (REPO_ROOT / "homr", REPO_ROOT / "external" / "homr")
HOMR_REPO = next((p for p in _HOMR_CANDIDATES if (p / "homr").exists()), _HOMR_CANDIDATES[1])
JST = ZoneInfo("Asia/Tokyo")

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

logger = logging.getLogger("homr_evaluator")

from src.homr_eval_scripts.core.heuristics import (
    compute_and_save_gap_stats,
    compute_candidate_stats,
    compute_transform_info,
    export_measure_grid_candidates,
    filter_detections_by_notehead_proximity,
    recover_end_barlines,
    resolve_clusters_dry_run,
    resolve_tight_duplicates_dry_run,
)
from src.homr_eval_scripts.core.metrics import (
    BarlinePrediction,
    ImageMetrics,
    aggregate_metrics,
    compute_metrics,
    load_ground_truth_boxes,
)
from src.homr_eval_scripts.core.predictor import run_homr_on_image
from src.homr_eval_scripts.core.reporting import (
    draw_overlay,
    save_debug_mask_overlay,
    save_debug_staff_overlay,
    write_compare_md,
    write_metrics_csv,
    write_metrics_json,
    write_readme,
    write_run_config,
    write_run_sh,
)
from src.homr_eval_scripts.core.utils import (
    STEM_CONTEXT_HEURISTICS,
    choose_run_id,
    ensure_dir,
    eprint,
    git_info,
    load_ground_truth_mapping,
    map_pred_to_orig,
    prepare_working_image,
    sanitise_images,
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images",
        nargs="+",
        required=True,
        help="List of image files to evaluate",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("logs/homr_eval"),
        help="Root directory for evaluation outputs",
    )
    parser.add_argument(
        "--run-tag",
        type=str,
        help="Optional suffix appended to the run identifier",
    )
    parser.add_argument(
        "--ground-truth",
        action="append",
        default=[],
        help="Mapping of image stem to ground truth JSON, e.g. page_001:data/training/annotations/page_001/boxes_sorted.json",
    )
    parser.add_argument(
        "--ground-truth-dir",
        type=Path,
        help="Directory containing <stem>.json ground truth files",
    )
    parser.add_argument(
        "--iou-threshold",
        type=float,
        default=0.5,
        help="IoU threshold to consider a detection a true positive",
    )
    parser.add_argument(
        "--docker-tag",
        type=str,
        help="Docker image tag recorded in run_config.json",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Enable homr cache file usage",
    )
    parser.add_argument(
        "--write-staff-positions",
        action="store_true",
        help="Persist staff position text files alongside debug outputs",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Timeout (seconds) when waiting for title detection futures",
    )
    parser.add_argument(
        "--baseline-metrics",
        type=Path,
        help="Optional metrics.json from baseline detector for comparison",
    )
    parser.add_argument(
        "--force-run-id",
        type=str,
        help="Override automatically generated run identifier",
    )
    parser.add_argument(
        "--barline-min-height-factor",
        type=float,
        default=1.0,
        help="Scale factor applied to barline minimum height threshold",
    )
    parser.add_argument(
        "--barline-max-width-factor",
        type=float,
        default=1.0,
        help="Scale factor applied to barline maximum width threshold",
    )
    parser.add_argument(
        "--barline-staff-overlap-min",
        type=float,
        default=0.0,
        help="Minimum staff mask overlap ratio required to keep a barline candidate",
    )
    parser.add_argument(
        "--barline-edge-margin-x",
        type=int,
        default=0,
        help="Reject barline candidates within this x-margin of page edges",
    )
    parser.add_argument(
        "--barline-edge-margin-y",
        type=int,
        default=0,
        help="Reject barline candidates within this y-margin of page edges",
    )
    parser.add_argument(
        "--enable-sr",
        action="store_true",
        help="Enable Super-Resolution (Real-ESRGAN) preprocessing",
    )
    parser.add_argument(
        "--sr-scale",
        type=int,
        default=4,
        help="SR scale factor (2 or 4)",
    )
    parser.add_argument(
        "--sr-tile",
        type=int,
        default=-1,
        help="Tile size for SR (-1=auto/default). 0=force no tiling (fastest but high VRAM). 512=conservative tiling.",
    )
    parser.add_argument(
        "--sr-tile-pad",
        type=int,
        default=10,
        help="Tile padding for SR (overlap pixels).",
    )
    parser.add_argument(
        "--sr-fp32",
        action="store_true",
        help="Force full precision (fp32) for SR. Default is fp16 (half) if CUDA available.",
    )
    parser.add_argument(
        "--pre-computed-sr",
        type=Path,
        help="Path to a pre-computed SR image (skips SR inference)",
    )
    parser.add_argument(
        "--gen-vertical-run",
        action="store_true",
        help="Enable staff-constrained vertical run-length candidate generator",
    )
    parser.add_argument(
        "--gen-vertical-run-weak",
        action="store_true",
        help="Enable weaker staff-constrained vertical run-length generator (lower min-run, higher threshold)",
    )
    parser.add_argument(
        "--gen-barline-cc-relaxed",
        action="store_true",
        help="Enable relaxed CC extraction on bar_line_img",
    )
    parser.add_argument(
        "--gen-barline-cc-dilated",
        action="store_true",
        help="Enable dilated CC extraction on bar_line_img",
    )
    parser.add_argument(
        "--gen-sobel-vertical",
        action="store_true",
        help="Enable staff-constrained vertical Sobel candidate generator",
    )
    parser.add_argument(
        "--gen-sobel-vertical-weak",
        action="store_true",
        help="Enable weaker staff-constrained vertical Sobel generator (lower threshold)",
    )
    parser.add_argument(
        "--gen-column-sum-staff",
        action="store_true",
        help="Enable staff-masked column-sum candidate generator",
    )
    parser.add_argument(
        "--gen-column-sum-weak",
        action="store_true",
        help="Enable weaker staff-masked column-sum candidate generator",
    )
    parser.add_argument(
        "--gen-column-sum-no-staff",
        action="store_true",
        help="Enable column-sum candidate generator without staff mask",
    )
    parser.add_argument(
        "--gen-hough-vertical",
        action="store_true",
        help="Enable staff-masked Hough vertical line candidate generator",
    )
    parser.add_argument(
        "--gen-hough-vertical-weak",
        action="store_true",
        help="Enable weaker staff-masked Hough vertical line generator",
    )
    parser.add_argument(
        "--gen-vertical-run-no-staff",
        action="store_true",
        help="Enable vertical run-length candidate generator without staff mask",
    )
    parser.add_argument(
        "--gen-barline-cc-tiny",
        action="store_true",
        help="Enable tiny CC extraction on bar_line_img (min_size=(1,1))",
    )
    parser.add_argument(
        "--gen-sobel-no-staff",
        action="store_true",
        help="Enable vertical Sobel candidate generator without staff mask",
    )
    parser.add_argument(
        "--enable-end-barline-recovery",
        action="store_true",
        help="Enable post-processing to recover staff-end barlines",
    )
    parser.add_argument(
        "--enable-segnet-cache",
        action="store_true",
        help="Enable cached Segnet ONNXRuntime session reuse",
    )
    return parser.parse_args(argv)


def run_evaluation(argv: Optional[Sequence[str]] = None) -> Path:
    args = parse_args(argv)
    if argv is None:
        command_args = list(sys.argv)
    else:
        command_args = ["homr_evaluator.py", *argv]
    images = sanitise_images(args.images)
    ground_truth_map = load_ground_truth_mapping(args)

    run_id = choose_run_id(args)
    run_dir = args.output_root / run_id
    ensure_dir(run_dir)

    write_run_sh(run_dir, command_args)

    git_meta = git_info()
    write_run_config(run_dir, run_id, args, git_meta, images, command_args)

    if args.enable_segnet_cache:
        try:
            from homr_eval_scripts.segnet_cache import enable_segnet_cache

            if enable_segnet_cache():
                eprint("Segnet cache enabled.")
        except Exception as exc:
            eprint(f"Failed to enable Segnet cache: {exc}")

    download_weights()

    per_image_metrics: List[ImageMetrics] = []
    ground_truth_summary: Dict[str, Optional[Path]] = {}
    tuning = {
        "barline_min_height_factor": args.barline_min_height_factor,
        "barline_max_width_factor": args.barline_max_width_factor,
        "barline_staff_overlap_min": args.barline_staff_overlap_min,
        "barline_edge_margin_x": args.barline_edge_margin_x,
        "barline_edge_margin_y": args.barline_edge_margin_y,
        "gen_vertical_run": args.gen_vertical_run,
        "gen_vertical_run_weak": args.gen_vertical_run_weak,
        "gen_barline_cc_relaxed": args.gen_barline_cc_relaxed,
        "gen_barline_cc_dilated": args.gen_barline_cc_dilated,
        "gen_sobel_vertical": args.gen_sobel_vertical,
        "gen_sobel_vertical_weak": args.gen_sobel_vertical_weak,
        "gen_column_sum_staff": args.gen_column_sum_staff,
        "gen_column_sum_weak": args.gen_column_sum_weak,
        "gen_column_sum_no_staff": args.gen_column_sum_no_staff,
        "gen_hough_vertical": args.gen_hough_vertical,
        "gen_hough_vertical_weak": args.gen_hough_vertical_weak,
        "gen_vertical_run_no_staff": args.gen_vertical_run_no_staff,
        "gen_barline_cc_tiny": args.gen_barline_cc_tiny,
        "gen_sobel_no_staff": args.gen_sobel_no_staff,
    }

    persistent_upsampler: Any = None
    working_images: List[Tuple[Path, Path, int]] = []  # (orig_path, working_path, sr_scale)

    # Phase 1: Super-Resolution (All images)
    if args.enable_sr or args.pre_computed_sr is not None:
        eprint("Phase 1: Super-Resolution / Image Preparation...")
        for image_path in images:
            stem = image_path.stem
            image_run_dir = run_dir / stem
            working_image = prepare_working_image(image_path, image_run_dir)
            sr_scale = 1

            if args.pre_computed_sr is not None:
                sr_source = args.pre_computed_sr
                if not sr_source.exists():
                    raise FileNotFoundError(f"Pre-computed SR image not found: {sr_source}")
                original_img = cv2.imread(str(working_image))
                if original_img is not None:
                    original_h, original_w = original_img.shape[:2]
                    sr_img = cv2.imread(str(sr_source))
                    if sr_img is None:
                        raise FileNotFoundError(
                            f"Failed to load pre-computed SR image: {sr_source}"
                        )
                    up_h, up_w = sr_img.shape[:2]
                    inferred_scale = round(up_w / original_w) if original_w else 1
                    if inferred_scale >= 2 and up_w >= original_w * 2 and up_h >= original_h * 2:
                        sr_scale = inferred_scale
                    cv2.imwrite(str(working_image), sr_img)
            elif args.enable_sr:
                requested_sr_scale = args.sr_scale
                model_name = "RealESRGAN_x4plus" if requested_sr_scale == 4 else "RealESRGAN_x2plus"
                img_bgr = cv2.imread(str(working_image))
                if img_bgr is not None:
                    original_h, original_w = img_bgr.shape[:2]
                    upscaled, persistent_upsampler = apply_advanced_sr(
                        img_bgr,
                        model_name=model_name,
                        scale=requested_sr_scale,
                        tile=args.sr_tile,
                        tile_pad=args.sr_tile_pad,
                        fp32=args.sr_fp32,
                        upsampler=persistent_upsampler,
                    )
                    up_h, up_w = upscaled.shape[:2]
                    inferred_scale = round(up_w / original_w) if original_w else 1
                    if inferred_scale >= 2 and up_w >= original_w * 2 and up_h >= original_h * 2:
                        sr_scale = inferred_scale
                    cv2.imwrite(str(working_image), upscaled)

            working_images.append((image_path, working_image, sr_scale))

        # Cleanup SR VRAM
        persistent_upsampler = None
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                eprint("Released SR model VRAM.")
        except ImportError:
            pass
    else:
        # No SR
        for image_path in images:
            stem = image_path.stem
            image_run_dir = run_dir / stem
            working_image = prepare_working_image(image_path, image_run_dir)
            working_images.append((image_path, working_image, 1))

    # Phase 2: Homr Inference & Evaluation
    eprint("Phase 2: Homr Inference & Evaluation...")
    for image_path, working_image, sr_scale in working_images:
        stem = image_path.stem
        image_run_dir = run_dir / stem
        # working_image is already prepared

        # Optimization: Create a downscaled proxy for Homr inference if image is huge (e.g. SR)
        inference_image_path = working_image
        proxy_scale = 1.0

        # Read the current working image (SR or Original) to check dimensions
        img_check = cv2.imread(str(working_image))
        sr_h, sr_w = 0, 0
        proxy_scale_x = 1.0
        proxy_scale_y = 1.0

        if img_check is not None:
            sr_h, sr_w = img_check.shape[:2]
            pixels = sr_h * sr_w
            target_pixels = 3.5 * 1000 * 1000  # Target ~3.5MP for Homr Inference

            if pixels > target_pixels * 1.5:
                proxy_scale = (pixels / target_pixels) ** 0.5
                proxy_w = int(sr_w / proxy_scale)
                proxy_h = int(sr_h / proxy_scale)

                # Re-calculate exact scale based on integer dimensions
                proxy_scale_x = sr_w / proxy_w
                proxy_scale_y = sr_h / proxy_h

                eprint(
                    f"Creating Proxy for Homr Inference: {sr_w}x{sr_h} -> {proxy_w}x{proxy_h} (Scale: {proxy_scale:.2f})"
                )
                proxy_img = cv2.resize(img_check, (proxy_w, proxy_h))

                proxy_path = image_run_dir / f"{stem}_proxy.png"
                cv2.imwrite(str(proxy_path), proxy_img)
                inference_image_path = proxy_path

        config = ProcessingConfig(
            True,
            args.cache,
            args.write_staff_positions,
            False,
            -1,
        )
        xml_args = XmlGeneratorArguments(False, None, None)

        predictions, xml_path, seg_shape, runtime_s, notehead_mask, staff_mask = run_homr_on_image(
            inference_image_path, config, xml_args, args.timeout, tuning
        )
        transform = compute_transform_info(inference_image_path, seg_shape)

        mapped_predictions: List[BarlinePrediction] = []
        for pred in predictions:
            # Map Seg -> Proxy (or Original if no proxy)
            orig_bbox_proxy = map_pred_to_orig(pred.pred_bbox, transform)

            # Map Proxy -> SR (High Res)
            x1, y1, x2, y2 = orig_bbox_proxy
            if inference_image_path != working_image:
                x1 = int(round(x1 * proxy_scale_x))
                y1 = int(round(y1 * proxy_scale_y))
                x2 = int(round(x2 * proxy_scale_x))
                y2 = int(round(y2 * proxy_scale_y))

            mapped_predictions.append(
                BarlinePrediction(
                    pred_bbox=pred.pred_bbox,
                    orig_bbox=(x1, y1, x2, y2),
                    system_index=pred.system_index,
                    staff_index=pred.staff_index,
                )
            )

        # Scale ThinBarlineConfig if SR is enabled
        tb_config = ThinBarlineConfig()
        if sr_scale > 1:
            tb_config = ThinBarlineConfig(
                min_height=tb_config.min_height * sr_scale,
                max_height=tb_config.max_height * sr_scale,
                max_width=tb_config.max_width * sr_scale,
                y_merge_tolerance=tb_config.y_merge_tolerance * sr_scale,
                y_center_tolerance=tb_config.y_center_tolerance * sr_scale,
                x_center_tolerance=tb_config.x_center_tolerance * sr_scale,
                adjacent_relaxed_span=tb_config.adjacent_relaxed_span * sr_scale,
                vertical_gap_fill=tb_config.vertical_gap_fill * sr_scale,
                left_margin_limit=tb_config.left_margin_limit * sr_scale,
                cluster_x_tolerance=tb_config.cluster_x_tolerance * sr_scale,
                cluster_reject_span=tb_config.cluster_reject_span * sr_scale,
                # Intensity / Ratio thresholds remain same
                pixel_threshold=tb_config.pixel_threshold,
                dark_pixel_threshold=tb_config.dark_pixel_threshold,
                adjacent_min_intensity=tb_config.adjacent_min_intensity,
                adjacent_relaxed_dark_ratio=tb_config.adjacent_relaxed_dark_ratio,
                max_intensity_std=tb_config.max_intensity_std,
                max_intensity_std_relaxed=tb_config.max_intensity_std_relaxed,
                notehead_dark_ratio=tb_config.notehead_dark_ratio,
                notehead_std_floor=tb_config.notehead_std_floor,
                allow_single_side_bright=tb_config.allow_single_side_bright,
                single_side_dark_ratio=tb_config.single_side_dark_ratio,
                cluster_reject_count=tb_config.cluster_reject_count,
            )

        extra_barlines = detect_thin_vertical_runs(
            working_image,
            [prediction.orig_bbox for prediction in mapped_predictions],
            config=tb_config,
        )

        def _centre(box: Tuple[int, int, int, int]) -> Tuple[float, float]:
            x1, y1, x2, y2 = box
            return (x1 + x2) / 2.0, (y1 + y2) / 2.0

        def _vertical_overlap_fraction(
            box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]
        ) -> float:
            top = max(box_a[1], box_b[1])
            bottom = min(box_a[3], box_b[3])
            if bottom <= top:
                return 0.0
            overlap = bottom - top
            height_a = max(box_a[3] - box_a[1], 1)
            height_b = max(box_b[3] - box_b[1], 1)
            return overlap / float(max(height_a, height_b))

        for box in extra_barlines:
            cx_extra, cy_extra = _centre(box)
            box_height = max(box[3] - box[1], 1)
            replaced = False
            for idx, pred in enumerate(mapped_predictions):
                existing_box = pred.orig_bbox
                cx_existing, cy_existing = _centre(existing_box)
                if abs(cx_existing - cx_extra) > 2:
                    continue

                existing_height = max(existing_box[3] - existing_box[1], 1)
                centre_gap = abs(cy_existing - cy_extra)
                vertical_overlap = _vertical_overlap_fraction(existing_box, box)

                if vertical_overlap >= 0.6:
                    if box_height > existing_height:
                        mapped_predictions[idx] = BarlinePrediction(
                            pred_bbox=box,
                            orig_bbox=box,
                            system_index=-2,
                            staff_index=-1,
                        )
                    replaced = True
                    break

                max_height = max(box_height, existing_height)
                if centre_gap <= max_height:
                    if box_height >= existing_height:
                        mapped_predictions[idx] = BarlinePrediction(
                            pred_bbox=box,
                            orig_bbox=box,
                            system_index=-2,
                            staff_index=-1,
                        )
                    replaced = True
                    break

                # Same X column but belonging to a different staff system; keep scanning.

            if not replaced:
                mapped_predictions.append(
                    BarlinePrediction(
                        pred_bbox=box,
                        orig_bbox=box,
                        system_index=-2,
                        staff_index=-1,
                    )
                )

        # --- Heuristic 1: Notehead Proximity Rejection ---
        rejected_by_heuristic: List[BarlinePrediction] = []

        eprint(f"DEBUG: notehead_mask shape={notehead_mask.shape} dtype={notehead_mask.dtype}")
        eprint(
            f"DEBUG: notehead_mask min={notehead_mask.min()} max={notehead_mask.max()} unique={np.unique(notehead_mask)[:10]}"
        )
        eprint(f"DEBUG: staff_mask shape={staff_mask.shape} dtype={staff_mask.dtype}")
        eprint(
            f"DEBUG: staff_mask min={staff_mask.min()} max={staff_mask.max()} unique={np.unique(staff_mask)[:10]}"
        )

        # FIX: content is 0/1. Scale to 0/255 for correct bitwise operations and resize interpolation
        notehead_mask_255 = (notehead_mask * 255).astype(np.uint8)
        staff_mask_255 = (staff_mask * 255).astype(np.uint8)

        # Always compute resized masks for diagnostics/stats
        # IMPORTANT: Resize to SR/Working Image dimensions, not Proxy dimensions!
        notehead_mask_resized = cv2.resize(
            notehead_mask_255,
            dsize=(sr_w, sr_h),
            interpolation=cv2.INTER_NEAREST,
        )

        staff_mask_resized = cv2.resize(
            staff_mask_255,
            dsize=(sr_w, sr_h),
            interpolation=cv2.INTER_NEAREST,
        )

        # DIAGNOSTICS: Save mask overlays (ENABLED for data collection)
        save_debug_mask_overlay(
            working_image,
            notehead_mask_resized,
            image_run_dir / f"{stem}_debug_notehead_resized_overlay.png",
        )

        save_debug_staff_overlay(
            working_image,
            staff_mask_resized,
            image_run_dir / f"{stem}_debug_staff_resized_overlay.png",
        )

        # DIAGNOSTICS: Compute and save stats for ALL candidates (ENABLED for data collection)
        compute_candidate_stats(
            mapped_predictions, notehead_mask_resized, staff_mask_resized, stem, image_run_dir
        )

        if STEM_CONTEXT_HEURISTICS["enabled"]:
            # Scale heuristics parameters if SR is enabled
            h_config = STEM_CONTEXT_HEURISTICS.copy()
            if sr_scale > 1:
                h_config["notehead_proximity_threshold_px"] *= sr_scale
                # Area overlap scales quadratically (sr_scale^2)
                h_config["min_overlap_px"] *= sr_scale * sr_scale
                h_config["max_height_px"] *= sr_scale
                h_config["max_width_px"] *= sr_scale
                h_config["cluster_gap_threshold_px"] *= sr_scale

            mapped_predictions, rejected_by_heuristic = filter_detections_by_notehead_proximity(
                mapped_predictions,
                notehead_mask_resized,
                h_config["notehead_proximity_threshold_px"],
                h_config["min_overlap_px"],
                h_config["max_height_px"],
                h_config["max_width_px"],
                staff_mask_resized,
                h_config["min_staff_crossings"],
                h_config["staff_crossing_enabled"],
            )
        # --- End Heuristic 1 ---

        added_end_barlines: List[BarlinePrediction] = []
        if args.enable_end_barline_recovery:
            added_end_barlines = recover_end_barlines(
                working_image, mapped_predictions, staff_mask_resized
            )
            if added_end_barlines:
                mapped_predictions.extend(added_end_barlines)

        # DIAGNOSTICS: Compute gaps (Phase 10)
        compute_and_save_gap_stats(mapped_predictions, stem, image_run_dir)

        # DIAGNOSTICS: Cluster Resolution Dry Run (Phase 11)
        if STEM_CONTEXT_HEURISTICS.get("cluster_resolution_dry_run", False):
            resolve_clusters_dry_run(
                mapped_predictions,
                notehead_mask_resized,
                stem,
                image_run_dir,
                STEM_CONTEXT_HEURISTICS.get("cluster_gap_threshold_px", 15),
            )

        # DIAGNOSTICS: Tight Duplicate Dry Run (Phase 12)
        if STEM_CONTEXT_HEURISTICS.get("tight_duplicate_dry_run", False):
            resolve_tight_duplicates_dry_run(
                mapped_predictions, notehead_mask_resized, stem, image_run_dir
            )

        # DIAGNOSTICS: Measure Grid Export (Phase 13)
        if STEM_CONTEXT_HEURISTICS.get("measure_grid_export", False):
            export_measure_grid_candidates(
                mapped_predictions, notehead_mask_resized, stem, image_run_dir
            )

        ground_truth_path: Optional[Path] = None
        if stem in ground_truth_map:
            ground_truth_path = ground_truth_map[stem]
        elif args.ground_truth_dir:
            candidate = args.ground_truth_dir / f"{stem}.json"
            if candidate.exists():
                ground_truth_path = candidate
        else:
            auto_candidate = REPO_ROOT / "data" / f"ground_truth_{stem}.json"
            if auto_candidate.exists():
                ground_truth_path = auto_candidate

        ground_truth_summary[stem] = ground_truth_path

        metric = ImageMetrics(
            image=stem,
            num_predictions=len(mapped_predictions),
            num_ground_truth=0,
            true_positives=0,
            false_positives=len(mapped_predictions),
            false_negatives=0,
            precision=0.0,
            recall=0.0,
            f1=0.0,
            matches=[],
            soft_matches=[],
        )
        per_image_metrics.append(metric)

        # Scale predictions back to 1x for JSON export and correct metric calculation logic if external tools use it
        # BUT wait: compute_metrics logic (above) assumes pred_boxes are compatible with gt_boxes.
        # If we passed UP-SCALED mapped_predictions to compute_metrics, we would have 0 matches.
        # FIX: We need a separate list for metrics calculation that is scaled down.

        # Retroactive fix: The metric calculation above (lines 1830) used `mapped_predictions` (Upscaled).
        # We must re-do the metric calc with scaled-down predictions.

        metrics_predictions: List[BarlinePrediction] = []
        for pred in mapped_predictions:
            # Scale down bbox to original 1x coords
            orig_1x = tuple(int(c / sr_scale) for c in pred.orig_bbox)
            metrics_predictions.append(
                BarlinePrediction(
                    pred_bbox=pred.pred_bbox,  # This is internal homr bbox
                    orig_bbox=orig_1x,
                    system_index=pred.system_index,
                    staff_index=pred.staff_index,
                )
            )

        # Re-compute metrics with 1x predictions
        metric = ImageMetrics(
            image=stem,
            num_predictions=len(metrics_predictions),
            num_ground_truth=0,
            true_positives=0,
            false_positives=len(metrics_predictions),
            false_negatives=0,
            precision=0.0,
            recall=0.0,
            f1=0.0,
            matches=[],
            soft_matches=[],
        )
        match_result = None
        if ground_truth_path:
            gt_boxes = load_ground_truth_boxes(ground_truth_path)
            metric, match_result = compute_metrics(
                metrics_predictions, gt_boxes, args.iou_threshold
            )
            metric.image = stem
        else:
            metric.image = stem

        # Replace the last appended metric
        per_image_metrics[-1] = metric

        overlay_path = image_run_dir / f"{stem}_barline_overlay.png"
        draw_overlay(
            working_image,
            mapped_predictions,  # Draw on UPSCALED image with UPSCALED preds
            overlay_path,
            matches=match_result.matches if match_result else None,
            soft_matches=match_result.soft_matches if match_result else None,
            rejected_detections=rejected_by_heuristic,
            added_detections=added_end_barlines,
            false_positive_indices=match_result.false_positive_indices if match_result else None,
        )

        detections_path = image_run_dir / f"{stem}_detections.json"
        with detections_path.open("w", encoding="utf-8") as fh:
            json.dump(
                {
                    "image": str(image_path),
                    "predictions": [
                        {
                            "pred_bbox": pred.pred_bbox,
                            "orig_bbox": pred.orig_bbox,
                            "system_index": pred.system_index,
                            "staff_index": pred.staff_index,
                        }
                        for pred in metrics_predictions  # Save 1x predictions
                    ],
                },
                fh,
                indent=2,
            )

    aggregate = aggregate_metrics(per_image_metrics)

    extra = {
        "ground_truth": {
            image: str(path) if path else None for image, path in ground_truth_summary.items()
        },
        "tuning": tuning,
    }
    write_metrics_json(run_dir, run_id, per_image_metrics, aggregate, extra)
    write_metrics_csv(run_dir, per_image_metrics, aggregate)
    write_readme(run_dir, run_id, per_image_metrics, aggregate, args, ground_truth_summary)
    write_compare_md(run_dir, per_image_metrics, aggregate, args.baseline_metrics)
    return run_dir


def main() -> None:
    run_evaluation()


if __name__ == "__main__":
    main()
