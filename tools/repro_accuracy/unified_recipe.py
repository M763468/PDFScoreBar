import json
import cv2
import numpy as np
from pathlib import Path
import logging
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.steps.probe_scan import run_probe_scan_batch
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from src.common.barline_evaluation import greedy_barline_match

logging.basicConfig(level=logging.INFO)

def main():
    score_name = "Va__Prokofiev_Symphony5"
    page_stem = "page_001"
    image_p = PROJECT_ROOT / "data/evaluation2/images" / score_name / f"{page_stem}.png"
    
    # Identify a source run for seeds
    hybrid_run_root = PROJECT_ROOT / "logs/hybrid_generalization/verify_fixed_v10/20260330_095914"
    baseline_json = hybrid_run_root / "baseline" / "batch" / page_stem / f"{page_stem}_detections.json"
    sr_json = hybrid_run_root / "sr" / "batch" / page_stem / f"{page_stem}_detections.json"
    omr_json = hybrid_run_root / "omr_sr" / page_stem / "predictions.json"
    
    # 1. UNION SEED (to maximize row coverage)
    union = load_json_boxes(baseline_json) + load_json_boxes(sr_json) + load_json_boxes(omr_json)
    out_dir = PROJECT_ROOT / "logs/unified_recipe_verified"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"{page_stem}.json", "w") as f: json.dump(union, f)
    
    # 2. PROBE SCAN (includes vertical split)
    run_probe_scan_batch(
        images=[image_p],
        output_root=out_dir,
        bands_from=out_dir,
        staff_mask_dir=None,
        clef_mask_dir=None,
        score_name=score_name,
        ink_threshold=180,
        min_ratio=0.85,
        input_image_scale=1.0,
        detect_probe_kwargs={
            "scan_gap_rescue": True,
            "probe_width": 4,
            "band_source": "row_stats",
            "scan_disable_existing_suppression": True, # CRITICAL
        },
        enable_heuristic_filters=True,
        candidate_filter_kwargs={"min_staff_overlap_ratio": 0.02, "min_ink_ratio": 0.18}
    )
    
    # 3. CNN SCORING (includes X-dist NMS)
    run_cnn_scoring_batch(
        probe_output_root=out_dir,
        images=[image_p],
        model_path=PROJECT_ROOT / "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth",
        threshold=0.1,
        batch_size=64,
        bands_from=out_dir,
        staff_vov_threshold=0.5,
        crop_recenter_on_bbox_ink=True,
        input_image_scale=1.0,
        candidate_rescale_factor=1.0,
    )
    
    # 4. EVALUATE
    scored_file = out_dir / f"eval2_{score_name}_{page_stem}" / "pipeline2_no_peak_scored.json"
    preds = [tuple(c["bbox"]) for c in json.load(open(scored_file)) if c["score"] >= 0.1]
    
    gt_file = PROJECT_ROOT / "data/evaluation2/annotations" / score_name / page_stem / "boxes_sorted.json"
    gts = []
    for item in json.load(open(gt_file)):
        if isinstance(item, list): gts.append(tuple(item[:4]))
        elif "barline_location" in item: gts.append(tuple(item["barline_location"]))
        
    res = greedy_barline_match(preds, gts, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=12.0)
    print(f"VERIFIED Result: TP: {len(res.matches)} | FP: {len(res.false_positive_indices)} | FN: {len(res.false_negative_indices)}")

if __name__ == "__main__":
    main()
