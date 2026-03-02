import json
from pathlib import Path
import cv2
import numpy as np
import sys

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.pipeline.probe_detector.bands import build_row_stats

def check_regression(score_name, page_name):
    img_path = Path(f"data/evaluation2/images/{score_name}/{page_name}.png")
    source_path = Path(f"logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12/{score_name}/{page_name}/pipeline2_no_peak_candidates.json")
    
    if not source_path.exists():
        return None

    img = cv2.imread(str(img_path))
    if img is None: return None
    
    with open(source_path, "r") as f:
        source_boxes = json.load(f)

    # 1. Old Method (img_h * 0.05)
    old_max_dist = img.shape[0] * 0.05
    old_row_stats = build_row_stats(source_boxes, cluster_max_dist=old_max_dist, min_row_count=3)
    
    # 2. New Method (bbox_h * 0.5)
    heights = [abs(b[3] - b[1]) for b in source_boxes if abs(b[3] - b[1]) > 0]
    avg_h = np.median(heights) if heights else 100
    new_max_dist = avg_h * 0.5
    new_row_stats = build_row_stats(source_boxes, cluster_max_dist=new_max_dist, min_row_count=3)

    return {
        "old_count": len(old_row_stats),
        "new_count": len(new_row_stats),
        "old_dist": old_max_dist,
        "new_dist": new_max_dist,
        "avg_h": avg_h
    }

def visualize_staff(score_name, page_name, out_name):
    img_path = Path(f"data/evaluation2/images/{score_name}/{page_name}.png")
    source_path = Path(f"logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12/{score_name}/{page_name}/pipeline2_no_peak_candidates.json")
    img = cv2.imread(str(img_path))
    with open(source_path, "r") as f:
        source_boxes = json.load(f)
    heights = [abs(b[3] - b[1]) for b in source_boxes if abs(b[3] - b[1]) > 0]
    avg_h = np.median(heights) if heights else 100
    new_max_dist = avg_h * 0.5
    row_stats = build_row_stats(source_boxes, cluster_max_dist=new_max_dist, min_row_count=3)
    staff_bands = [(int(r["top"]), int(r["bottom"])) for r in row_stats]
    overlay = img.copy()
    for y1, y2 in staff_bands:
        cv2.rectangle(overlay, (0, y1), (img.shape[1], y2), (0, 255, 0), -1)
    img = cv2.addWeighted(overlay, 0.2, img, 0.8, 0)
    cv2.imwrite(f"debug_outputs/regression_check_{out_name}.png", img)

if __name__ == "__main__":
    targets = [
        ("Shostakovich-Sym5-Va", "page_003"),
        ("Va_Prokofiev_Symphony1", "page_005"),
        ("Va__Prokofiev_Symphony5", "page_021"),
        ("Va__Prokofiev_Symphony5", "page_003"),
        ("Va__Prokofiev_Symphony5", "page_023"),
        ("Va_Prokofiev_Symphony1", "page_006")
    ]
    
    print(f"{'Page':<40} | Old | New | MaxDist(O) | MaxDist(N)")
    print("-" * 80)
    for score, page in targets:
        res = check_regression(score, page)
        if res:
            print(f"{score+'/'+page:<40} | {res['old_count']:<3} | {res['new_count']:<3} | {res['old_dist']:<10.1f} | {res['new_dist']:<10.1f}")
            if res['old_count'] != res['new_count']:
                visualize_staff(score, page, page)
                print(f"  [!] Count changed. Generated debug_outputs/regression_check_{page}.png")
