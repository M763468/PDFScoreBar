import json
import logging
import shutil
import sys
from pathlib import Path

# Add project roots
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from homr_eval_scripts.core.metrics import load_ground_truth_boxes
from src.common.barline_evaluation import greedy_barline_match
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.steps.probe_scan import run_probe_scan_batch

logging.basicConfig(level=logging.INFO)


def main():
    # 1. Setup paths for Prokofiev page 1
    image_path = PROJECT_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png"
    gt_path = (
        PROJECT_ROOT
        / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/boxes_sorted.json"
    )

    # We use the baseline results from the bypass_sr_test_v2 run (360 DPI)
    baseline_run_root = (
        PROJECT_ROOT
        / "logs/hybrid_generalization/bypass_sr_test/eval2_bypass_sr_test_v2/baseline/batch/page_001"
    )

    output_root = PROJECT_ROOT / "artifacts/verify_sr_bypass_split"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    # 2. Run Probe Scan starting from baseline bands + SPLIT ENABLED
    print("\n--- Step 1: Probe Scan (Baseline + SPLIT ENABLED) ---")
    temp_bands = output_root / "temp_bands/Va_Prokofiev_Symphony1/page_001"
    temp_bands.mkdir(parents=True)
    shutil.copy(
        baseline_run_root / "page_001_detections.json",
        temp_bands / "pipeline2_no_peak_candidates.json",
    )
    shutil.copy(
        baseline_run_root / "page_001_proxy_debug_3_staff.png",
        output_root / "temp_bands/page_001_debug_3_staff.png",
    )

    detect_probe_kwargs = {
        "post_split_wide_candidates": True,
        "post_split_min_width_unit_ratio": 0.5,
        "post_split_box_width_unit_ratio": 0.4,
        "post_split_peak_distance_unit_ratio": 0.2,
        "post_split_peak_prominence_ratio": 0.1,
    }

    run_probe_scan_batch(
        images=[image_path],
        output_root=output_root / "probe_scan",
        bands_from=output_root / "temp_bands",
        staff_mask_dir=output_root / "temp_bands",
        ink_threshold=230,
        min_ratio=0.70,
        min_height_ratio=0.012,
        score_name="Va_Prokofiev_Symphony1",
        detect_probe_kwargs=detect_probe_kwargs,
    )

    # 3. Run CNN Scoring
    print("\n--- Step 2: CNN Scoring ---")
    cnn_model_path = (
        PROJECT_ROOT
        / "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
    )

    run_cnn_scoring_batch(
        probe_output_root=output_root / "probe_scan",
        images=[image_path],
        model_path=cnn_model_path,
        threshold=0.1,
        score_name="Va_Prokofiev_Symphony1",
        crop_recenter_on_bbox_ink=True,
    )

    # 4. Evaluate Results
    print("\n--- Step 3: Final Evaluation (center_anchor) ---")
    result_json = (
        output_root
        / "probe_scan/eval2_Va_Prokofiev_Symphony1_page_001/pipeline2_no_peak_filtered_cnn.json"
    )
    with open(result_json) as f:
        preds_list = json.load(f)

    preds = [tuple(b) for b in preds_list]
    gt_boxes = load_ground_truth_boxes(gt_path)

    match_result = greedy_barline_match(
        preds, gt_boxes, rule_name="center_anchor", vov_threshold=0.5, xdist_threshold=12.0
    )

    tp = len(match_result.matches)
    fp = len(match_result.false_positive_indices)
    fn = len(match_result.false_negative_indices)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print("\nRESULT (SR Bypass + Probe + SPLIT + CNN):")
    print(f"  P: {precision:.4f}")
    print(f"  R: {recall:.4f}")
    print(f"  F1: {f1:.4f}")
    print(f"  TP: {tp}, FP: {fp}, FN: {fn}")

    print("\nREFERENCE (Previous #44 result with SR):")
    print("  P: 1.0000, R: 1.0000, F1: 1.0000 (TP: 85, FP: 0, FN: 0)")


if __name__ == "__main__":
    main()
