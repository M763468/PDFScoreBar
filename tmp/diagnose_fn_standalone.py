import json
from pathlib import Path
from typing import Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
Box = Tuple[int, int, int, int]

# --- Inlined functions from src.common.barline_evaluation ---

BARLINE_DEFAULT_MIN_WIDTH = 12
BARLINE_X_MARGIN = 3
BARLINE_Y_MARGIN = 3


def _ensure_ordered(box: Box) -> Box:
    x1, y1, x2, y2 = box
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return x1, y1, x2, y2


def expand_barline_box(
    box: Box,
    *,
    min_width: int = BARLINE_DEFAULT_MIN_WIDTH,
    x_margin: int = BARLINE_X_MARGIN,
    y_margin: int = BARLINE_Y_MARGIN,
    bounds: Optional[Tuple[int, int]] = None,
) -> Box:
    if min_width < 1:
        raise ValueError("min_width must be >= 1")
    x1, y1, x2, y2 = _ensure_ordered(box)
    width = max(1, x2 - x1)
    centre_x = (x1 + x2) / 2.0
    half_width = max(width / 2.0, min_width / 2.0)

    padded_x1 = int(round(centre_x - half_width)) - x_margin
    padded_x2 = int(round(centre_x + half_width)) + x_margin
    padded_y1 = y1 - y_margin
    padded_y2 = y2 + y_margin

    padded_x1 = max(0, padded_x1)
    padded_y1 = max(0, padded_y1)

    if bounds is not None:
        max_x, max_y = bounds
        if max_x <= 0 or max_y <= 0:
            raise ValueError("bounds must be positive")
        padded_x1 = min(padded_x1, max_x - 1)
        padded_x2 = min(padded_x2, max_x - 1)
        padded_y1 = min(padded_y1, max_y - 1)
        padded_y2 = min(padded_y2, max_y - 1)

    if padded_x2 <= padded_x1:
        padded_x2 = padded_x1 + 1
    if padded_y2 <= padded_y1:
        padded_y2 = padded_y1 + 1

    return padded_x1, padded_y1, padded_x2, padded_y2


def barline_iou(
    box_a: Box,
    box_b: Box,
    *,
    min_width: int = BARLINE_DEFAULT_MIN_WIDTH,
    x_margin: int = BARLINE_X_MARGIN,
    y_margin: int = BARLINE_Y_MARGIN,
    bounds: Optional[Tuple[int, int]] = None,
) -> float:
    ax1, ay1, ax2, ay2 = expand_barline_box(
        box_a, min_width=min_width, x_margin=x_margin, y_margin=y_margin, bounds=bounds
    )
    bx1, by1, bx2, by2 = expand_barline_box(
        box_b, min_width=min_width, x_margin=x_margin, y_margin=y_margin, bounds=bounds
    )

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(inter_x2 - inter_x1, 0)
    inter_h = max(inter_y2 - inter_y1, 0)
    inter_area = inter_w * inter_h

    area_a = max(ax2 - ax1, 0) * max(ay2 - ay1, 0)
    area_b = max(bx2 - bx1, 0) * max(by2 - by1, 0)

    union_area = area_a + area_b - inter_area
    if union_area <= 0:
        return 0.0
    return inter_area / union_area


# --- End of inlined functions ---

import subprocess


def load_json_boxes(path):
    try:
        content = subprocess.check_output(f"cat {path}", shell=True)
        data = json.loads(content)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print(f"ERROR: File not found at {path}")
        return None

    if not data:
        return []

    boxes = []
    # Handle different JSON structures
    if isinstance(data, dict) and "predictions" in data:
        # homr format
        boxes = [tuple(item["orig_bbox"]) for item in data["predictions"]]
    elif data and isinstance(data[0], list):
        # OMR-DLN format
        boxes = [tuple(item) for item in data]
    elif data and isinstance(data[0], dict) and "barline_location" in data[0]:
        # GT format
        boxes = [tuple(item["barline_location"]) for item in data]
    else:
        boxes = [tuple(item) for item in data]

    return boxes


def find_matches_for_gt(gt_boxes, pred_boxes, iou_thresh=0.5):
    matches = {}
    if not gt_boxes or not pred_boxes:
        return matches

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

    baseline_final_path = REPO_ROOT / "logs/phase4_baseline_repro/filtered_barlines.json"

    s2_merged_path = REPO_ROOT / "logs/phase5b_promiscuous_union_eval/page_3_hybrid_preds.json"
    s2_final_path = (
        REPO_ROOT
        / "logs/phase5b_promiscuous_union_eval/page_3_filtered_output/filtered_barlines.json"
    )

    # --- Load Data ---
    gt_boxes = load_json_boxes(gt_path)
    baseline_final_boxes = load_json_boxes(baseline_final_path)
    s2_merged_boxes = load_json_boxes(s2_merged_path)
    s2_final_boxes = load_json_boxes(s2_final_path)

    if any(b is None for b in [gt_boxes, baseline_final_boxes, s2_merged_boxes, s2_final_boxes]):
        print("Aborting due to missing files.")
        return

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
        f"{'GT Index':<10} | {'In Merge?':<10} | {'Merge IoU':<10} | {'GT Bbox':<30} | {'Merge Bbox'}"
    )
    print("-" * 90)
    for row in results:
        print(
            f"{row['gt_index']:<10} | {row['in_s2_merge_output']:<10} | {row['s2_merge_iou']:<10} | {str(row['gt_box']):<30} | {row['s2_merge_box']}"
        )

    # --- Deeper dive for dropped boxes ---
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
