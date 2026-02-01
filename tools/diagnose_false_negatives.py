import json
import sys
from pathlib import Path

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import barline_iou


def load_json_boxes(path):
    with open(path, "r") as f:
        data = json.load(f)
    if not data:
        return []

    boxes = []
    if isinstance(data[0], dict) and "barline_location" in data[0]:
        boxes = [tuple(item["barline_location"]) for item in data]
    else:
        boxes = [tuple(item) for item in data]
    return boxes


def find_matches_for_gt(gt_boxes, pred_boxes, iou_thresh=0.5):
    matches = {}
    for i, gt_box in enumerate(gt_boxes):
        best_iou = 0
        best_pred_idx = -1
        for j, pred_box in enumerate(pred_boxes):
            iou = barline_iou(gt_box, pred_box)
            if iou > best_iou:
                best_iou = iou
                best_pred_idx = j

        if best_iou > iou_thresh:
            matches[i] = {
                "pred_idx": best_pred_idx,
                "iou": best_iou,
                "pred_box": pred_boxes[best_pred_idx],
            }
    return matches


def main():
    # --- Paths ---
    gt_path = REPO_ROOT / "data/evaluation/annotations/page_003/boxes_sorted.json"

    # Phase 4 baseline final output (This is the ideal output)
    # The script that generated this is in the dev log. Let's assume the output is in a similar path structure.
    # From the dev log: logs/phase4_notehead_geom/20251218_page3_hybrid_tol5_geom
    # The output of analyze_staff_consistency is a directory. Let's check for filtered_barlines.json
    baseline_final_path = (
        REPO_ROOT
        / "logs/phase4_notehead_geom/20251218_page3_hybrid_tol5_geom/filtered_barlines.json"
    )

    # Strategy 2 outputs
    s2_merged_path = REPO_ROOT / "logs/phase5b_promiscuous_union_eval/page_3_hybrid_preds.json"
    s2_final_path = (
        REPO_ROOT
        / "logs/phase5b_promiscuous_union_eval/page_3_filtered_output/filtered_barlines.json"
    )
    # The row-filter only output is not saved by default. The script prints the metrics though.
    # "After Row Filter: TP=150, FP=2, FN=2" -> this means the 2 FNs are already present after the row filter.

    # --- Load Data ---
    gt_boxes = load_json_boxes(gt_path)
    baseline_final_boxes = load_json_boxes(baseline_final_path)
    s2_merged_boxes = load_json_boxes(s2_merged_path)
    s2_final_boxes = load_json_boxes(s2_final_path)

    # --- Find matches ---
    baseline_matches = find_matches_for_gt(gt_boxes, baseline_final_boxes)
    s2_final_matches = find_matches_for_gt(gt_boxes, s2_final_boxes)

    # --- Identify the 2 FNs ---
    fn_gt_indices = []
    for i in range(len(gt_boxes)):
        if i in baseline_matches and i not in s2_final_matches:
            fn_gt_indices.append(i)

    print(f"Found {len(fn_gt_indices)} False Negatives. GT Indices: {fn_gt_indices}")

    # --- Trace the FNs ---
    results = []
    for gt_idx in fn_gt_indices:
        gt_box = gt_boxes[gt_idx]
        result_row = {"gt_index": gt_idx, "gt_box": gt_box}

        # Check merge stage
        merge_match = find_matches_for_gt([gt_box], s2_merged_boxes)
        if 0 in merge_match:
            result_row["in_s2_merge_output"] = "Yes"
            result_row["s2_merge_iou"] = f"{merge_match[0]['iou']:.3f}"
            result_row["s2_merge_box"] = merge_match[0]["pred_box"]
        else:
            result_row["in_s2_merge_output"] = "No"
            result_row["s2_merge_iou"] = "N/A"
            result_row["s2_merge_box"] = "N/A"

        results.append(result_row)

    # --- Print results table ---
    print("\n--- FN Root Cause Analysis ---")
    print(
        f"{'GT Index':<10} | {'In Merge?':<10} | {'Merge IoU':<10} | {'GT Bbox':<25} | {'Merge Bbox'}"
    )
    print("-" * 80)
    for row in results:
        print(
            f"{row['gt_index']:<10} | {row['in_s2_merge_output']:<10} | {row['s2_merge_iou']:<10} | {str(row['gt_box']):<25} | {row['s2_merge_box']}"
        )

    # --- Deeper analysis for dropped boxes ---
    print("\n--- Deeper Dive on Dropped Barlines ---")

    raw_baseline_path = (
        REPO_ROOT
        / "logs/hybrid_generalization/sr_eval_smoke_page3/baseline/page_3/page_3/page_3_detections.json"
    )
    raw_sr_path = (
        REPO_ROOT
        / "logs/hybrid_generalization/sr_eval_smoke_page3/sr/page_3/page_3/page_3_detections.json"
    )
    raw_omr_path = (
        REPO_ROOT / "logs/hybrid_generalization/sr_eval_smoke_page3/omr_sr/predictions.json"
    )

    raw_baseline_boxes = load_json_boxes(raw_baseline_path)
    raw_sr_boxes = load_json_boxes(raw_sr_path)
    raw_omr_boxes = load_json_boxes(raw_omr_path)

    for row in results:
        if row["in_s2_merge_output"] == "No":
            gt_idx = row["gt_index"]
            gt_box = row["gt_box"]

            baseline_support = find_matches_for_gt([gt_box], raw_baseline_boxes)
            sr_support = find_matches_for_gt([gt_box], raw_sr_boxes)
            omr_support = find_matches_for_gt([gt_box], raw_omr_boxes)

            support_count = 0
            sources = []
            if 0 in baseline_support:
                support_count += 1
                sources.append("baseline")
            if 0 in sr_support:
                support_count += 1
                sources.append("sr")
            if 0 in omr_support:
                support_count += 1
                sources.append("omr")

            print(f"GT Index {gt_idx}:")
            print(f"  - Support from {support_count} detectors: {sources}")
            if support_count < 2:
                print(
                    "  - CONCLUSION: Dropped at merge because cluster had < 2 detectors (Cause A)."
                )


if __name__ == "__main__":
    main()
