
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
from src.pipeline.cnn_scoring import run_cnn_scoring_batch
from src.common.barline_evaluation import greedy_barline_match
from homr_eval_scripts.homr_evaluator import load_ground_truth_boxes

logging.basicConfig(level=logging.INFO)

def main():
    # 1. Setup paths for Sibelius page 1
    image_path = PROJECT_ROOT / "data/evaluation2/images/Sibelius-Violin_Concerto-Viola/page_001.png"
    gt_path = PROJECT_ROOT / "data/evaluation2/annotations/Sibelius-Violin_Concerto-Viola/page_001/boxes_sorted.json"
    
    # We use the existing baseline results as the starting point (FPs included)
    baseline_root = PROJECT_ROOT / "logs/hybrid_pipeline_bench/eval2_Sibelius-Violin_Concerto-Viola_page_001_20260131_094551/baseline"
    
    output_root = PROJECT_ROOT / "artifacts/verify_sr_bypass"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    # 2. Run Probe Scan starting from baseline bands
    print("\n--- Step 1: Probe Scan (Starting from Baseline FPs) ---")
    # We need to simulate the expected directory structure for bands_from
    # run_probe_scan_batch looks for {score_name}/{stem}/...
    temp_bands = output_root / "temp_bands/Sibelius-Violin_Concerto-Viola/page_001"
    temp_bands.mkdir(parents=True)
    # Copy baseline detections to pretend they are the consensus result
    shutil.copy(
        baseline_root / "page_001/page_001/page_001_detections.json",
        temp_bands / "pipeline2_no_peak_candidates.json"
    )
    
    # We also need the staff mask from baseline
    temp_mask = output_root / "temp_bands/page_001_debug_3_staff.png"
    shutil.copy(
        baseline_root / "page_001/page_001/page_001_proxy_debug_3_staff.png",
        temp_mask
    )

    run_probe_scan_batch(
        images=[image_path],
        output_root=output_root / "probe_scan",
        bands_from=output_root / "temp_bands",
        staff_mask_dir=output_root / "temp_bands",
        ink_threshold=230,
        min_ratio=0.70,
        min_height_ratio=0.012,
        score_name="test_run"
    )

    # 3. Run CNN Scoring
    print("\n--- Step 2: CNN Scoring ---")
    cnn_model_path = PROJECT_ROOT / "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
    
    run_cnn_scoring_batch(
        probe_output_root=output_root / "probe_scan",
        images=[image_path],
        model_path=cnn_model_path,
        threshold=0.1,
        score_name="test_run"
    )

    # 4. Evaluate Results
    print("\n--- Step 3: Final Evaluation ---")
    result_json = output_root / "probe_scan/eval2_test_run_page_001/pipeline2_no_peak_filtered_cnn.json"
    with open(result_json) as f:
        preds_list = json.load(f)
    
    preds = [tuple(b) for b in preds_list]
    gt_boxes = load_ground_truth_boxes(gt_path)
    
    match_result = greedy_barline_match(preds, gt_boxes, iou_threshold=0.5)
    
    tp = len(match_result.matches)
    fp = len(match_result.false_positive_indices)
    fn = len(match_result.false_negative_indices)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"\nRESULT (SR Bypass + Probe + CNN):")
    print(f"  P: {precision:.4f}")
    print(f"  R: {recall:.4f}")
    print(f"  F1: {f1:.4f}")
    print(f"  TP: {tp}, FP: {fp}, FN: {fn}")
    
    print("\nREFERENCE (Previous SR result):")
    print("  P: 0.9348, R: 0.8776, F1: 0.9053 (TP: 43, FP: 3, FN: 6)")

if __name__ == "__main__":
    main()
