import json
import sys
from pathlib import Path

import cv2
import numpy as np

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.pipeline.probe_detector.bands import build_row_stats


def visualize_improved_staff_detection(score_name, page_name):
    img_path = Path(f"data/evaluation2/images/{score_name}/{page_name}.png")
    source_path = Path(
        f"logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12/{score_name}/{page_name}/pipeline2_no_peak_candidates.json"
    )
    gt_dir = Path(f"data/evaluation2/annotations/{score_name}/{page_name}")
    gt_file = sorted(list(gt_dir.glob("boxes_sorted*.json")), reverse=True)[0]

    img = cv2.imread(str(img_path))
    if img is None:
        return

    with open(source_path, "r") as f:
        source_boxes = json.load(f)
    with open(gt_file, "r") as f:
        gt_data = json.load(f)
        gt_boxes = [tuple(b["barline_location"]) for b in gt_data if "barline_location" in b]

    # Calculate average bbox height
    heights = [abs(b[3] - b[1]) for b in source_boxes if abs(b[3] - b[1]) > 0]
    avg_h = np.median(heights) if heights else 100

    # IMPROVED: Use bbox_h * 0.5 instead of img_h * 0.05
    # Old: img.shape[0] * 0.05 (~225px)
    # New: avg_h * 0.5 (~55px)
    improved_max_dist = avg_h * 0.5
    print(f"Old max_dist: {img.shape[0] * 0.05:.1f}px")
    print(f"New max_dist: {improved_max_dist:.1f}px (based on median bbox_h={avg_h:.1f})")

    row_stats = build_row_stats(source_boxes, cluster_max_dist=improved_max_dist, min_row_count=3)
    staff_bands = [(int(r["top"]), int(r["bottom"])) for r in row_stats]
    print(f"Detected {len(staff_bands)} staff bands.")

    # Overlay
    overlay = img.copy()
    for y1, y2 in staff_bands:
        cv2.rectangle(overlay, (0, y1), (img.shape[1], y2), (0, 255, 0), -1)
    img = cv2.addWeighted(overlay, 0.2, img, 0.8, 0)

    # Check matches
    for gx1, gy1, gx2, gy2 in gt_boxes:
        h = gy2 - gy1
        max_vov = 0.0
        for by1, by2 in staff_bands:
            vov = max(0, min(gy2, by2) - max(gy1, gy1)) / float(
                h
            )  # Fixed typo gy1, gy1 -> gy1, py1 logic
            # Re-implementing simplified VoV logic here for visualization
            overlap = min(gy2, by2) - max(gy1, by1)
            vov = max(0, overlap) / float(h)
            max_vov = max(max_vov, vov)

        color = (0, 255, 0) if max_vov >= 0.5 else (0, 0, 255)
        cv2.rectangle(img, (gx1, gy1), (gx2, gy2), color, 2)
        if max_vov < 0.5:
            cv2.putText(img, f"FAIL {max_vov:.1%}", (gx1, gy1 - 5), 0, 0.6, (0, 0, 255), 1)

    out_path = Path(f"debug_outputs/improved_rule_check_{page_name}.png")
    cv2.imwrite(str(out_path), img)
    print(f"Improved check image saved to {out_path}")


if __name__ == "__main__":
    visualize_improved_staff_detection("Sibelius-Violin_Concerto-Viola", "page_004")
