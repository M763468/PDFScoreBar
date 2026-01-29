# Script: diagnose_alignment.py
# Purpose: Produce visual evidence of coordinate mismatch between Predictions and GT.
# Environment: Must be run inside 'homr_eval_gpu' container via 'poetry run python'.
# Dependencies: opencv-python-headless (cv2), numpy, json.

import argparse
import json
import os

import cv2
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Diagnose Alignment Mismatch")
    parser.add_argument("--json", type=str, required=True, help="Path to detection JSON")
    parser.add_argument("--gt", type=str, required=True, help="Path to GT JSON")
    parser.add_argument("--image", type=str, required=True, help="Path to input image")
    parser.add_argument("--output", type=str, required=True, help="Output directory")
    return parser.parse_args()


def load_boxes(path, is_gt=False):
    with open(path, "r") as f:
        data = json.load(f)

    boxes = []
    if is_gt:
        if (
            isinstance(data, list)
            and len(data) > 0
            and isinstance(data[0], dict)
            and "barline_location" in data[0]
        ):
            boxes = [item["barline_location"] for item in data]
        else:
            boxes = data  # Assume list
    else:
        # Prediction format logic
        raw_list = []
        if isinstance(data, dict) and "predictions" in data:
            raw_list = data["predictions"]
        elif isinstance(data, list):
            raw_list = data

        for item in raw_list:
            if isinstance(item, list):
                boxes.append(item)
            elif isinstance(item, dict):
                # Prefer orig_bbox
                if "orig_bbox" in item:
                    boxes.append(item["orig_bbox"])
                elif "bbox" in item:
                    boxes.append(item["bbox"])
                elif "pred_bbox" in item:
                    boxes.append(item["pred_bbox"])
    return np.array(boxes) if len(boxes) > 0 else np.empty((0, 4))


def draw_boxes(img, boxes, color, thickness=2):
    for box in boxes:
        x1, y1, x2, y2 = map(int, box)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)


def main():
    args = parse_args()
    os.makedirs(args.output, exist_ok=True)

    # Load Data
    preds = load_boxes(args.json, is_gt=False)
    gt = load_boxes(args.gt, is_gt=True)

    print(f"Loaded {len(preds)} predictions")
    print(f"Loaded {len(gt)} GT boxes")

    if len(preds) == 0:
        print("Fatal: No predictions found.")
        return

    # Compute Stats
    pred_y_med = np.median(preds[:, 1]) if len(preds) > 0 else 0
    gt_y_med = np.median(gt[:, 1]) if len(gt) > 0 else 0
    diff_y = gt_y_med - pred_y_med

    print(f"Stats: Median Pred Y={pred_y_med:.1f}, Median GT Y={gt_y_med:.1f}, Diff={diff_y:.1f}")

    # Align
    aligned_preds = preds.astype(float).copy()
    aligned_preds[:, [1, 3]] += diff_y

    # Load Image
    base_img = cv2.imread(args.image)
    if base_img is None:
        print(f"Error: Could not load image {args.image}")
        return

    # (A) GT Boxes Overlay
    img_A = base_img.copy()
    draw_boxes(img_A, gt, (0, 255, 0), 2)  # Green
    cv2.imwrite(os.path.join(args.output, "A_GT_Overlay.jpg"), img_A)

    # (B) Original Predictions Overlay
    img_B = base_img.copy()
    draw_boxes(img_B, preds, (0, 0, 255), 2)  # Red
    cv2.imwrite(os.path.join(args.output, "B_Original_Preds.jpg"), img_B)

    # (C) Aligned Predictions Overlay
    img_C = base_img.copy()
    draw_boxes(img_C, aligned_preds, (255, 0, 0), 2)  # Blue
    cv2.imwrite(os.path.join(args.output, "C_Aligned_Preds.jpg"), img_C)

    # (D) Combined (GT + Aligned)
    img_D = base_img.copy()
    draw_boxes(img_D, gt, (0, 255, 0), 2)  # Green GT
    draw_boxes(img_D, aligned_preds, (255, 0, 0), 2)  # Blue Aligned Preds
    cv2.imwrite(os.path.join(args.output, "D_Combined_Aligned.jpg"), img_D)

    # Write Report Stats
    report_path = os.path.join(args.output, "run_stats.json")
    stats = {
        "pred_count": len(preds),
        "gt_count": len(gt),
        "median_pred_y": float(pred_y_med),
        "median_gt_y": float(gt_y_med),
        "shift_y": float(diff_y),
        "pred_x_range": [float(preds[:, 0].min()), float(preds[:, 2].max())]
        if len(preds) > 0
        else [],
        "gt_x_range": [float(gt[:, 0].min()), float(gt[:, 2].max())] if len(gt) > 0 else [],
    }
    with open(report_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Diagnostics saved to {args.output}")


if __name__ == "__main__":
    main()
