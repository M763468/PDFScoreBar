
import json
import logging
import os
import sys
from pathlib import Path
import shutil

# Add project roots
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.pipeline.probe_scan import run_probe_scan_batch
from tools.cnn_classifier.score_candidates_batch import run_scoring_batch
from src.common.barline_evaluation import greedy_barline_match
from homr_eval_scripts.homr_evaluator import load_ground_truth_boxes

logging.basicConfig(level=logging.INFO)

def main():
    # 1. Setup paths for Sibelius page 1
    image_path = PROJECT_ROOT / "data/evaluation2/images/Sibelius-Violin_Concerto-Viola/page_001.png"
    gt_path = PROJECT_ROOT / "data/evaluation2/annotations/Sibelius-Violin_Concerto-Viola/page_001/boxes_sorted.json"
    
    # Starting bands for Issue 44 eval was scoring_input_eval2_v12
    bands_from = PROJECT_ROOT / "logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12"
    
    output_root = PROJECT_ROOT / "artifacts/reproduce_issue44"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    # 2. Probe Scan with Issue 44 parameters (Gap Rescue enabled)
    print("\n--- Step 1: Probe Scan (Issue 44 Params) ---")
    detect_probe_kwargs = {
        "scan_gap_rescue": True,
        "scan_gap_threshold_ratio": 1.5,
        "scan_gap_rescue_min_ratio": 0.3,
        "scan_x_peak_rescue": True,
        "scan_rightmost_rescue": True,
        "divisi_rescue": True,
        "scan_center_on_peak": True,
        "max_per_band": 100,
    }

    run_probe_scan_batch(
        images=[image_path],
        output_root=output_root,
        bands_from=bands_from,
        staff_mask_dir=None,
        ink_threshold=180,
        min_ratio=0.85,
        min_height_ratio=0.012,
        detect_probe_kwargs=detect_probe_kwargs,
        score_name="Sibelius-Violin_Concerto-Viola"
    )

    # 3. CNN Scoring with Issue 44 parameters (Crop Recenter enabled)
    print("\n--- Step 2: CNN Scoring (Issue 44 Params) ---")
    model_path = PROJECT_ROOT / "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
    
    run_scoring_batch(
        model=model_path,
        images_root=PROJECT_ROOT / "data/evaluation2/images",
        logs=output_root,
        threshold=0.1,
        crop_recenter_on_bbox_ink=True,
        crop_recenter_max_shift_unit_ratio=0.5,
        bands_from=bands_from,
        staff_vov_threshold=0.5,
        overwrite=True,
    )

    # 4. Evaluate Results with center_anchor rule
    print("\n--- Step 3: Final Evaluation (center_anchor) ---")
    # Result folder is <score_name>/<page_stem>
    result_json = output_root / "eval2_Sibelius-Violin_Concerto-Viola_page_001/pipeline2_no_peak_scored.json"
    with open(result_json) as f:
        scored_data = json.load(f)
    
    # Filter by threshold 0.1
    preds = [tuple(item["bbox"]) for item in scored_data if item["score"] >= 0.1]
    gt_boxes = load_ground_truth_boxes(gt_path)
    
    match_result = greedy_barline_match(
        preds, gt_boxes, 
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0
    )
    
    tp = len(match_result.matches)
    fp = len(match_result.false_positive_indices)
    fn = len(match_result.false_negative_indices)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"\nRESULT (Reproduced Issue 44 conditions):")
    print(f"  P: {precision:.4f}")
    print(f"  R: {recall:.4f}")
    print(f"  F1: {f1:.4f}")
    print(f"  TP: {tp}, FP: {fp}, FN: {fn}")

if __name__ == "__main__":
    main()
