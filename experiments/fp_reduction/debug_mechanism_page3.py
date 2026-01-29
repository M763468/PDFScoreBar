# Script: debug_mechanism_page3.py
# Purpose: Generate detailed visual artifacts and a report explaining WHY Phase 3 heuristic fails (TP 152->24).
# Environment: 'homr_eval_gpu' container.

import argparse
import json
import os
import sys
from datetime import datetime

import cv2
import numpy as np

# Adjust path to import from src
if os.path.exists("/workspace/src"):
    sys.path.insert(0, "/workspace/src")
else:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

try:
    from common.barline_evaluation import greedy_barline_match
except ImportError:
    print("Error: Cannot import homr evaluation logic.")
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def load_data(args):
    # Load Image
    img = cv2.imread(args.image)
    if img is None:
        raise FileNotFoundError(f"Image not found: {args.image}")

    # Load Preds
    with open(args.json) as f:
        data = json.load(f)
    if isinstance(data, dict):
        raw = data["predictions"]
    else:
        raw = data

    preds = []
    for item in raw:
        if isinstance(item, list):
            preds.append(item)
        elif isinstance(item, dict):
            # Prefer orig_bbox
            preds.append(item.get("orig_bbox", item.get("bbox", item.get("pred_bbox"))))

    # Load GT
    with open(args.gt) as f:
        data = json.load(f)
    if isinstance(data, list) and len(data) > 0 and "barline_location" in data[0]:
        gt = [x["barline_location"] for x in data]
    else:
        gt = data

    return img, np.array(preds), np.array(gt)


def run_evaluation(preds, gt):
    # Convert to list of tuples for homr matcher
    p_tuples = [tuple(x) for x in preds]
    g_tuples = [tuple(x) for x in gt]

    result = greedy_barline_match(p_tuples, g_tuples, iou_threshold=0.5)

    tp_indices = set()
    for m in result.matches:
        tp_indices.add(m.pred_index)

    stats = {
        "TP": len(result.matches),
        "FP": len(result.false_positive_indices),
        "FN": len(result.false_negative_indices),
        "tp_indices": tp_indices,  # indices in the input 'preds' list
    }
    return stats


def draw_boxes(img, boxes, indices, color, thickness=2):
    canvas = img.copy()
    for idx_ in indices:
        if idx_ < len(boxes):
            x1, y1, x2, y2 = map(int, boxes[idx_])
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)
    return canvas


def main():
    args = parse_args()
    os.makedirs(args.output, exist_ok=True)

    img, preds, gt = load_data(args)

    # --- 1. Baseline Evaluation ---
    base_stats = run_evaluation(preds, gt)
    print(f"Baseline: TP={base_stats['TP']}, FP={base_stats['FP']}")

    # A) Original Overlay
    vis_a = img.copy()
    # Draw GT Green
    for g in gt:
        x1, y1, x2, y2 = map(int, g)
        cv2.rectangle(vis_a, (x1, y1), (x2, y2), (0, 255, 0), 2)
    # Draw Preds Red (All)
    for p in preds:
        x1, y1, x2, y2 = map(int, p)
        cv2.rectangle(vis_a, (x1, y1), (x2, y2), (0, 0, 255), 2)
    cv2.imwrite(os.path.join(args.output, "A_Original_Overlay.jpg"), vis_a)

    # --- 2. Clustering Logic ---
    # Replicating analyze_staff_consistency.py logic EXACTLY
    y_centers = [(b[1] + b[3]) / 2 for b in preds]
    indices_y = sorted(zip(range(len(preds)), y_centers), key=lambda x: x[1])
    sorted_indices = [x[0] for x in indices_y]
    sorted_ys = [x[1] for x in indices_y]

    systems = []
    current_system = []

    gap_log = []

    if len(sorted_ys) > 0:
        current_system.append(sorted_indices[0])
        for i in range(1, len(sorted_ys)):
            prev_y = sorted_ys[i - 1]
            curr_y = sorted_ys[i]
            gap = curr_y - prev_y

            if gap > 50:  # The threshold used
                systems.append(current_system)
                current_system = []
                gap_log.append(f"SPLIT at Gap={gap:.1f} (Y={curr_y:.1f})")

            current_system.append(sorted_indices[i])
        systems.append(current_system)

    valid_systems = [s for s in systems if len(s) >= 3]

    # B1) Clusters Visualization
    # Color code systems
    vis_b1 = img.copy()
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255)]
    for i, sys_indices in enumerate(valid_systems):
        col = colors[i % len(colors)]
        for idx in sys_indices:
            x1, y1, x2, y2 = map(int, preds[idx])
            cv2.rectangle(vis_b1, (x1, y1), (x2, y2), col, 2)
            # Label system ID
            if idx == sys_indices[0]:  # Label first one
                cv2.putText(
                    vis_b1,
                    f"Sys {i}",
                    (x1 - 30, int((y1 + y2) / 2)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    col,
                    2,
                )

    cv2.imwrite(os.path.join(args.output, "B1_Clusters.jpg"), vis_b1)

    # --- 3. Consistency Filter ---
    accepted_indices = set()
    rejection_reasons = []  # (idx, reason)

    for sys_id, indices in enumerate(valid_systems):
        tops = [preds[i][1] for i in indices]
        bottoms = [preds[i][3] for i in indices]

        med_top = np.median(tops)
        med_bot = np.median(bottoms)

        for idx in indices:
            box = preds[idx]
            top_dev = abs(box[1] - med_top)
            bot_dev = abs(box[3] - med_bot)

            if top_dev < 15 and bot_dev < 15:
                accepted_indices.add(idx)
            else:
                rejection_reasons.append(
                    {
                        "idx": idx,
                        "sys_id": sys_id,
                        "top_dev": top_dev,
                        "bot_dev": bot_dev,
                        "med_top": med_top,
                    }
                )

    accepted_preds = [preds[i] for i in sorted(list(accepted_indices))]

    # B2) Filter Result
    vis_b2 = img.copy()
    # Draw Rejected Red
    for i in range(len(preds)):
        if i not in accepted_indices:
            x1, y1, x2, y2 = map(int, preds[i])
            cv2.rectangle(vis_b2, (x1, y1), (x2, y2), (0, 0, 255), 2)
    # Draw Kept Green
    for i in accepted_indices:
        x1, y1, x2, y2 = map(int, preds[i])
        cv2.rectangle(vis_b2, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.imwrite(os.path.join(args.output, "B2_Filter_Result.jpg"), vis_b2)

    # --- 4. Diff Analysis ---
    filt_stats = run_evaluation(accepted_preds, gt)  # Note: accepted_preds is a subset list
    # We need to map accepted_preds back to original indices to know which TPs were lost.
    # Actually, base_stats['tp_indices'] tells us which ORIGINAL indices were TPs.
    # If an index in base_stats['tp_indices'] is NOT in accepted_indices, it was LOST.

    lost_tp_indices = []
    for idx in base_stats["tp_indices"]:
        if idx not in accepted_indices:
            lost_tp_indices.append(idx)

    print(f"Lost TPs: {len(lost_tp_indices)}")

    # C) Diff Visualization
    vis_c = img.copy()
    # Draw Lost TPs in BLUE (Critical errors)
    for idx in lost_tp_indices:
        x1, y1, x2, y2 = map(int, preds[idx])
        cv2.rectangle(vis_c, (x1, y1), (x2, y2), (255, 0, 0), 2)
        cv2.putText(vis_c, "LOST", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

    # Draw Kept TPs in Green
    for idx in base_stats["tp_indices"]:
        if idx in accepted_indices:
            x1, y1, x2, y2 = map(int, preds[idx])
            cv2.rectangle(vis_c, (x1, y1), (x2, y2), (0, 255, 0), 2)

    cv2.imwrite(os.path.join(args.output, "C_Diff_MissingTP.jpg"), vis_c)

    # --- Report Generation ---
    report_path = os.path.join(args.output, "mechanism_report.md")
    with open(report_path, "w") as f:
        f.write("# Phase 3 Mechanism Debug Report\n\n")
        f.write(f"**Date**: {datetime.now().isoformat()}\n")
        f.write(f"**Image**: `{args.image}`\n")
        f.write(f"**Input Detections**: `{args.json}` (N={len(preds)})\n\n")

        f.write("## 1. Baseline Metrics (homr unified)\n")
        f.write(f"- **TP**: {base_stats['TP']}\n")
        f.write(f"- **FP**: {base_stats['FP']}\n")
        f.write(f"- **FN**: {base_stats['FN']}\n\n")

        f.write("## 2. Clustering Step\n")
        f.write("- **Method**: Vertical Gap Splitting (Threshold = 50px)\n")
        f.write(f"- **Result**: Found {len(valid_systems)} valid systems.\n")
        for i, s in enumerate(valid_systems):
            f.write(f"  - **System {i}**: N={len(s)} items.\n")
        f.write("\n**Logs**:\n")
        for log in gap_log:
            f.write(f"- {log}\n")

        f.write("\n## 3. Consistency Filter Step\n")
        f.write(
            "- **Logic**: Reject if `abs(y_top - median_top) > 15` OR `abs(y_bot - median_bot) > 15`.\n"
        )
        f.write(f"- **Kept**: {len(accepted_indices)}\n")
        f.write(f"- **Rejected**: {len(preds) - len(accepted_indices)}\n")

        f.write("\n## 4. Impact on True Positives\n")
        f.write(f"- **Original TPs**: {base_stats['TP']}\n")
        f.write(f"- **Lost TPs**: {len(lost_tp_indices)} (Became FN)\n")
        f.write(f"- **Final TPs**: {base_stats['TP'] - len(lost_tp_indices)}\n\n")

        f.write("## 5. Visual Artifacts\n")
        f.write("- **[A] Original**: `A_Original_Overlay.jpg`\n")
        f.write("- **[B1] Clusters**: `B1_Clusters.jpg` (Shows why systems merged)\n")
        f.write("- **[B2] Filter**: `B2_Filter_Result.jpg` (Red = Rejected)\n")
        f.write("- **[C] TP Loss**: `C_Diff_MissingTP.jpg` (Blue = Lost TP)\n")


if __name__ == "__main__":
    main()
