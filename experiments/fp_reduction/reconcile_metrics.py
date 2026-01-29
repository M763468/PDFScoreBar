# Script: reconcile_metrics.py
# Purpose: Deep dive into TP=6 vs TP=152 mismatch.
# Environment: 'homr_eval_gpu' container.

import argparse
import json
import os

import cv2
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=str, required=True, help="Predictions JSON")
    parser.add_argument("--gt", type=str, required=True, help="GT JSON")
    parser.add_argument("--image", type=str, required=True, help="Image Path")
    parser.add_argument("--output", type=str, required=True, help="Output Dir")
    return parser.parse_args()


def load_boxes(path, name):
    print(f"Loading {name} from {path}")
    with open(path, "r") as f:
        data = json.load(f)

    boxes = []
    # Generic parser
    raw = data
    if isinstance(data, dict):
        if "predictions" in data:
            raw = data["predictions"]
        elif "annotations" in data:
            raw = data["annotations"]  # COCO style?
        elif "boxes" in data:
            raw = data["boxes"]

    for item in raw:
        if isinstance(item, list):
            boxes.append(item)
        elif isinstance(item, dict):
            # Try various keys
            if "barline_location" in item:
                boxes.append(item["barline_location"])
            elif "orig_bbox" in item:
                boxes.append(item["orig_bbox"])
            elif "bbox" in item:
                boxes.append(item["bbox"])
            elif "pred_bbox" in item:
                boxes.append(item["pred_bbox"])

    arr = np.array(boxes).astype(float)
    if len(arr) > 0:
        print(f"  {name}: {len(arr)} boxes. Sample: {arr[0]}")
        print(
            f"  {name} Range: X[{arr[:, 0].min():.1f}, {arr[:, 2].max():.1f}] Y[{arr[:, 1].min():.1f}, {arr[:, 3].max():.1f}]"
        )
    else:
        print(f"  {name}: 0 boxes found.")
    return arr


def compute_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

    iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
    return iou


def main():
    args = parse_args()
    os.makedirs(args.output, exist_ok=True)

    preds = load_boxes(args.json, "Preds")
    gt = load_boxes(args.gt, "GT")
    img = cv2.imread(args.image)
    if img is None:
        print(f"Failed to load image: {args.image}")
        return
    print(f"Image Shape: {img.shape}")

    # Task B: Explain why overlaps are not counted
    # For each GT, find best Pred IoU
    best_ious = []
    example_failures = []  # (GT, BestPred, IoU)

    for i, g in enumerate(gt):
        best_iou = 0
        best_p_idx = -1
        for j, p in enumerate(preds):
            iou = compute_iou(g, p)
            if iou > best_iou:
                best_iou = iou
                best_p_idx = j

        best_ious.append(best_iou)

        # Check standard match
        if best_iou >= 0.5:
            # Check strictly if pred already used in standard greedy?
            # Simplified for per-GT analysis: just count if *any* good match exists
            # Actual metric logic usually enforces unique match.
            # Let's verify unique matching logic from previous script
            pass

        # Save failure examples (Visible overlap but IoU < 0.5)
        if 0.1 < best_iou < 0.5:
            if len(example_failures) < 10:
                example_failures.append(
                    {"gt": g.tolist(), "pred": preds[best_p_idx].tolist(), "iou": best_iou}
                )

    best_ious = np.array(best_ious)
    print("\n--- Best IoU per GT Stats ---")
    print(f"Min: {best_ious.min():.3f}")
    print(f"Median: {np.median(best_ious):.3f}")
    print(f"Max: {best_ious.max():.3f}")
    print(f"GT with IoU >= 0.5: {np.sum(best_ious >= 0.5)}")
    print(f"GT with IoU >= 0.3: {np.sum(best_ious >= 0.3)}")
    print(f"GT with IoU >= 0.1: {np.sum(best_ious >= 0.1)}")

    # Simple Greedy Evaluation (Standard)
    # Sort by IoU to prioritize best fit? Standard is often greedy by conf, or Hungarian.
    # Here we just iterate GT.

    # Let's restart matching for strict metric
    ious = np.zeros((len(gt), len(preds)))
    for i, g in enumerate(gt):
        for j, p in enumerate(preds):
            ious[i, j] = compute_iou(g, p)

    matches_strict = 0
    while True:
        if ious.size == 0:
            break
        idx = np.unravel_index(np.argmax(ious), ious.shape)
        if ious[idx] < 0.5:
            break
        matches_strict += 1
        ious[idx[0], :] = -1  # GT used
        ious[:, idx[1]] = -1  # Pred used

    print(f"\nStrict TP (IoU>=0.5): {matches_strict}")
    print(f"FP: {len(preds) - matches_strict}")
    print(f"FN: {len(gt) - matches_strict}")

    # Generate Thumbnails for failures
    if example_failures:
        print(f"\nSaving {len(example_failures)} example failures to {args.output}")
        for idx, item in enumerate(example_failures):
            g = item["gt"]
            p = item["pred"]
            # Crop canvas
            pad = 20
            x1 = int(max(0, min(g[0], p[0]) - pad))
            y1 = int(max(0, min(g[1], p[1]) - pad))
            x2 = int(min(img.shape[1], max(g[2], p[2]) + pad))
            y2 = int(min(img.shape[0], max(g[3], p[3]) + pad))

            crop = img[y1:y2, x1:x2].copy()
            # Draw (translated)
            cv2.rectangle(
                crop,
                (int(g[0] - x1), int(g[1] - y1)),
                (int(g[2] - x1), int(g[3] - y1)),
                (0, 255, 0),
                1,
            )  # GT
            cv2.rectangle(
                crop,
                (int(p[0] - x1), int(p[1] - y1)),
                (int(p[2] - x1), int(p[3] - y1)),
                (0, 0, 255),
                1,
            )  # Pred

            cv2.putText(
                crop,
                f"IoU={item['iou']:.2f}",
                (5, 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                2,
            )
            cv2.putText(
                crop, f"IoU={item['iou']:.2f}", (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1
            )

            cv2.imwrite(os.path.join(args.output, f"fail_{idx}_iou_{item['iou']:.2f}.jpg"), crop)


if __name__ == "__main__":
    main()
