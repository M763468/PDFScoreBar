# Script: validate_metrics.py
# Purpose: Compute TP/FP metrics for Original vs Aligned predictions and generate overlays.
# Environment: 'homr_eval_gpu' container.

import argparse
import json
import os

import cv2
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=str, required=True)
    parser.add_argument("--gt", type=str, required=True)
    parser.add_argument("--image", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
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
            boxes = data
    else:
        # Prediction
        raw_list = []
        if isinstance(data, dict) and "predictions" in data:
            raw_list = data["predictions"]
        elif isinstance(data, list):
            raw_list = data

        for item in raw_list:
            if isinstance(item, list):
                boxes.append(item)
            elif isinstance(item, dict):
                if "orig_bbox" in item:
                    boxes.append(item["orig_bbox"])
                elif "bbox" in item:
                    boxes.append(item["bbox"])
                elif "pred_bbox" in item:
                    boxes.append(item["pred_bbox"])
    return np.array(boxes).astype(float) if len(boxes) > 0 else np.empty((0, 4))


def compute_iou(boxA, boxB):
    # box: [x1, y1, x2, y2]
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

    iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
    return iou


def evaluate(preds, gt_boxes, iou_thresh=0.5):
    # Greedy matching
    # 1. Compute IoU matrix
    # 2. Match
    if len(preds) == 0:
        return {"TP": 0, "FP": 0, "FN": len(gt_boxes)}
    if len(gt_boxes) == 0:
        return {"TP": 0, "FP": len(preds), "FN": 0}

    # Iterate over GTs and find matches
    # Note: Ideally we want 1-to-1 matching.
    # Simple approach: For each GT, find best matching Pred. If > thresh, and Pred not already used?
    # Let's use simple list tracking.

    tp = 0
    matched_preds = set()
    matched_gts = set()

    # Sort GTs? Or just iterate.
    # We iterate Preds to match simple OMR eval practice?
    # Actually, standard Pascall VOC: sort Preds by confidence (we don't have it here, assume random order).
    # Then match to GT.

    # Let's iterate GTs and see if covered. (Recall focused)
    # But for Precision (FP), we need to know which Preds are unused.

    # Better: Pairwise IoU
    # Rows: GT, Cols: Pred
    ious = np.zeros((len(gt_boxes), len(preds)))
    for i, g in enumerate(gt_boxes):
        for j, p in enumerate(preds):
            ious[i, j] = compute_iou(g, p)

    # Greedy assignment
    # Find max IoU in matrix
    while True:
        if ious.size == 0:
            break
        idx = np.unravel_index(np.argmax(ious), ious.shape)
        max_iou = ious[idx]
        if max_iou < iou_thresh:
            break

        gt_idx, pred_idx = idx
        # Match!
        if gt_idx not in matched_gts and pred_idx not in matched_preds:
            tp += 1
            matched_gts.add(gt_idx)
            matched_preds.add(pred_idx)
            # Nullify usage
            ious[gt_idx, :] = -1
            ious[:, pred_idx] = -1
        else:
            # Should not happen with nullify logic
            ious[gt_idx, pred_idx] = -1

    fp = len(preds) - len(matched_preds)
    fn = len(gt_boxes) - len(matched_gts)

    return {"TP": tp, "FP": fp, "FN": fn}


def draw_overlay(img, preds, gt, output_path, title):
    canvas = img.copy()
    # GT = Green
    for box in gt:
        cv2.rectangle(
            canvas, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (0, 255, 0), 2
        )
    # Preds = Red
    for box in preds:
        cv2.rectangle(
            canvas, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (0, 0, 255), 2
        )
    cv2.imwrite(output_path, canvas)


def main():
    args = parse_args()
    os.makedirs(args.output, exist_ok=True)

    # Load
    preds_orig = load_boxes(args.json, is_gt=False)
    gt = load_boxes(args.gt, is_gt=True)
    img = cv2.imread(args.image)

    print(f"Loaded: Preds={len(preds_orig)}, GT={len(gt)}")
    if len(preds_orig) > 0:
        print(f"Sample Pred: {preds_orig[0]}")
    if len(gt) > 0:
        print(f"Sample GT: {gt[0]}")

    # (A) Original Metrics
    metrics_orig = evaluate(preds_orig, gt, iou_thresh=0.5)
    print("\n--- (A) Original Metrics (IoU=0.5) ---")
    print(json.dumps(metrics_orig, indent=2))

    # (B) Aligned Metrics (User requested comparisons)
    # Re-calculate shift as done before
    if len(preds_orig) > 0 and len(gt) > 0:
        med_pred_y = np.median(preds_orig[:, 1])
        med_gt_y = np.median(gt[:, 1])
        diff = med_gt_y - med_pred_y
        print(f"\nShift calculated: {diff}")

        preds_aligned = preds_orig.copy()
        preds_aligned[:, [1, 3]] += diff  # Add diff

        metrics_aligned = evaluate(preds_aligned, gt, iou_thresh=0.5)
        print(f"--- (B) Aligned Metrics (Shift={diff:.1f}) ---")
        print(json.dumps(metrics_aligned, indent=2))

    # Overlays
    # 1. GT + Original Preds
    draw_overlay(
        img, preds_orig, gt, os.path.join(args.output, "OVERLAY_GT_OriginalPreds.jpg"), "Original"
    )

    # Save Report
    with open(os.path.join(args.output, "validation_results.json"), "w") as f:
        json.dump(
            {
                "original": metrics_orig,
                "aligned": metrics_aligned if "metrics_aligned" in locals() else None,
                "shift_y": diff if "diff" in locals() else 0,
            },
            f,
            indent=2,
        )


if __name__ == "__main__":
    main()
