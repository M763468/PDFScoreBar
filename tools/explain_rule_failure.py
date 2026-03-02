import json
from pathlib import Path
import cv2
import numpy as np
import sys

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.pipeline.probe_detector.bands import build_row_stats

def visualize_staff_misdetection(score_name, page_name):
    img_path = Path(f"data/evaluation2/images/{score_name}/{page_name}.png")
    # Source candidates used for row stats
    source_path = Path(f"logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12/{score_name}/{page_name}/pipeline2_no_peak_candidates.json")
    # Ground Truth
    gt_dir = Path(f"data/evaluation2/annotations/{score_name}/{page_name}")
    gt_file = sorted(list(gt_dir.glob("boxes_sorted*.json")), reverse=True)[0]

    img = cv2.imread(str(img_path))
    if img is None: return
    
    with open(source_path, "r") as f:
        source_boxes = json.load(f)
    with open(gt_file, "r") as f:
        gt_data = json.load(f)
        gt_boxes = [tuple(b["barline_location"]) for b in gt_data if "barline_location" in b]

    # Calculate row stats (estimated staff regions)
    row_stats = build_row_stats(source_boxes, cluster_max_dist=img.shape[0]*0.05, min_row_count=3)
    staff_bands = [(int(r["top"]), int(r["bottom"])) for r in row_stats]

    # Overlay
    overlay = img.copy()
    
    # 1. Draw estimated staff bands (Green highlight)
    for y1, y2 in staff_bands:
        cv2.rectangle(overlay, (0, y1), (img.shape[1], y2), (0, 255, 0), -1)
    
    img = cv2.addWeighted(overlay, 0.2, img, 0.8, 0)

    # 2. Check which GTs are "outside" these bands (The ones that would be deleted)
    for i, (gx1, gy1, gx2, gy2) in enumerate(gt_boxes):
        h = gy2 - gy1
        max_vov = 0.0
        for by1, by2 in staff_bands:
            vov = max(0, min(gy2, by2) - max(gy1, by1)) / float(h)
            max_vov = max(max_vov, vov)
        
        color = (0, 255, 0) if max_vov >= 0.5 else (0, 0, 255) # Red if it would be deleted
        cv2.rectangle(img, (gx1, gy1), (gx2, gy2), color, 3)
        if max_vov < 0.5:
            cv2.putText(img, "WILL BE DELETED", (gx1, gy1-10), 0, 0.8, (0,0,255), 2)

    out_path = Path(f"debug_outputs/rule_failure_explanation_{page_name}.png")
    cv2.imwrite(str(out_path), img)
    print(f"Explanation image saved to {out_path}")

if __name__ == "__main__":
    # Sibelius page 004 was the worst hit (Recall dropped from 99.9% to 93.7%)
    visualize_staff_misdetection("Sibelius-Violin_Concerto-Viola", "page_004")
