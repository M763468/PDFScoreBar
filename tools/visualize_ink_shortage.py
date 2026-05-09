#!/usr/bin/env python3
"""Archived Issue 120 ink-shortage visualization helper.

This script was added after the main Issue 120 probe-scan experiment to preserve
the visual inspection step for residuals classified as
``seed_miss_or_probe_reject``. It reads the archived residual trace CSV and
writes illustrative crops under ``logs/issue120_final_residuals/ink_analysis``.
It is not part of the primary evaluation pipeline.
"""

import ast
import csv
from pathlib import Path

import cv2
import numpy as np

csv_path = Path("logs/issue120_final_residuals/residual_trace.csv")
out_dir = Path("logs/issue120_final_residuals/ink_analysis")
out_dir.mkdir(exist_ok=True, parents=True)

with open(csv_path, newline="") as f:
    reader = csv.DictReader(f)
    rows = [r for r in reader if r["type"] == "FN" and r["reason"] == "seed_miss_or_probe_reject"]

# Pick a few distinct examples
examples = []
scores_seen = set()
for row in rows:
    if row["score"] not in scores_seen:
        examples.append(row)
        scores_seen.add(row["score"])
        if len(examples) >= 5:
            break

for row in examples:
    score = row["score"]
    page = row["page"]
    bbox = ast.literal_eval(row["bbox"])
    gt_id = row["id"]

    img_path = f"data/evaluation2/images/{score}/{page}.png"
    img = cv2.imread(img_path)
    if img is None:
        continue

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ink = (gray < 180).astype(np.uint8) * 255  # 255 for ink, 0 for bg

    # Calculate ink ratio inside GT box
    # GT box format: [x1, y1, x2, y2]
    x1, y1, x2, y2 = bbox
    # Ensure coordinates are within image bounds
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img.shape[1] - 1, x2), min(img.shape[0] - 1, y2)

    box_w = max(1, x2 - x1)
    box_h = max(1, y2 - y1)
    area = box_w * box_h

    # Sum of ink inside box (ink is 255 where true)
    ink_pixels = np.sum(ink[y1:y2, x1:x2] == 255)
    ink_ratio = ink_pixels / area

    # Crop with padding
    pad = 20
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    crop_w, crop_h = box_w + pad * 2, box_h + pad * 2
    cx1 = max(0, cx - crop_w // 2)
    cx2 = min(img.shape[1] - 1, cx + crop_w // 2)
    cy1 = max(0, cy - crop_h // 2)
    cy2 = min(img.shape[0] - 1, cy + crop_h // 2)

    crop_orig = img[cy1:cy2, cx1:cx2].copy()
    crop_ink = cv2.cvtColor(ink[cy1:cy2, cx1:cx2], cv2.COLOR_GRAY2BGR)

    # Draw GT box on both
    bx1, by1 = x1 - cx1, y1 - cy1
    bx2, by2 = x2 - cx1, y2 - cy1

    cv2.rectangle(crop_orig, (bx1, by1), (bx2, by2), (0, 0, 255), 1)
    cv2.rectangle(crop_ink, (bx1, by1), (bx2, by2), (0, 0, 255), 1)

    # Add text
    text = f"Ink Ratio: {ink_ratio:.2f}"
    cv2.putText(crop_orig, text, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    cv2.putText(crop_ink, text, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

    # Combine side by side
    combined = np.hstack((crop_orig, crop_ink))

    out_name = out_dir / f"{score}_{page}_gt{gt_id}.png"
    cv2.imwrite(str(out_name), combined)
    print(f"Saved {out_name} - Ink Ratio: {ink_ratio:.2f}")

print(f"Check {out_dir} for visualization images.")
