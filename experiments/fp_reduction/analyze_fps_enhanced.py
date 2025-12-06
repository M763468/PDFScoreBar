# NOTE (2025-12 repo restructure): This script may still assume pre-restructure paths (src/tools, tools/fp_reduction). Adjust imports if reusing.
#!/usr/bin/env python3
"""Enhanced FP analysis with spatial context."""

import json
import csv
from pathlib import Path

def enhanced_analysis(metrics_path, stats_path, detections_path, image_path):
    # Load data
    with open(metrics_path, 'r') as f:
        metrics = json.load(f)
    
    page_metrics = metrics["images"][0]
    tp_indices = set(m["pred_index"] for m in page_metrics["matches"])
    soft_indices = set(m["pred_index"] for m in page_metrics["soft_matches"])
    total_preds = page_metrics["num_predictions"]
    fp_indices = [i for i in range(total_preds) if i not in tp_indices and i not in soft_indices]
    
    stats_by_idx = {}
    with open(stats_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["pred_index"])
            stats_by_idx[idx] = {
                "x1": int(row["x1"]),
                "y1": int(row["y1"]),
                "x2": int(row["x2"]),
                "y2": int(row["y2"]),
                "width": int(row["width"]),
                "height": int(row["height"]),
                "dist": float(row["min_dist_to_notehead"]),
                "overlap": float(row["overlap_area"]),
            }
    
    # Get image dimensions (from a TP for reference)
    import cv2
    img = cv2.imread(str(image_path))
    img_h, img_w = img.shape[:2]
    
    print(f"Image dimensions: {img_w} x {img_h}")
    print(f"\nAnalyzing {len(fp_indices)} FPs with spatial context:\n")
    
    # Define margin zones
    LEFT_MARGIN = 100
    RIGHT_MARGIN = img_w - 100
    
    # Categorize by spatial location
    left_margin_fps = []
    right_margin_fps = []
    center_fps = []
    
    for idx in fp_indices:
        s = stats_by_idx[idx]
        cx = (s["x1"] + s["x2"]) / 2
        cy = (s["y1"] + s["y2"]) / 2
        
        location = "CENTER"
        if cx < LEFT_MARGIN:
            location = "LEFT_MARGIN"
            left_margin_fps.append(idx)
        elif cx > RIGHT_MARGIN:
            location = "RIGHT_MARGIN"
            right_margin_fps.append(idx)
        else:
            center_fps.append(idx)
        
        y_pct = (cy / img_h) * 100
        
        print(f"FP #{idx:3d}: x={cx:5.1f} y={cy:5.1f} ({y_pct:4.1f}%) "
              f"W={s['width']:2d} H={s['height']:2d} "
              f"Dist={s['dist']:5.1f} Overlap={s['overlap']:4.1f} "
              f"→ {location}")
    
    print(f"\n{'='*80}")
    print("SPATIAL DISTRIBUTION")
    print(f"{'='*80}")
    print(f"Left Margin (x < {LEFT_MARGIN}): {len(left_margin_fps)} FPs")
    print(f"Right Margin (x > {RIGHT_MARGIN}): {len(right_margin_fps)} FPs")
    print(f"Center: {len(center_fps)} FPs")
    
    # Focus on the 2 UNKNOWN cases
    print(f"\n{'='*80}")
    print("UNKNOWN FPs (meet all Safe Filter criteria)")
    print(f"{'='*80}")
    for idx in [126, 217]:
        if idx in stats_by_idx:
            s = stats_by_idx[idx]
            print(f"FP #{idx}: ({s['x1']},{s['y1']})-({s['x2']},{s['y2']}) "
                  f"W={s['width']} H={s['height']} Dist={s['dist']:.1f} Overlap={s['overlap']:.1f}")
            print(f"  → This has Dist < 5, H < 24, W < 4, Overlap >= 5")
            print(f"  → Yet it's still a FP. Likely a stem that happens to meet all criteria.")
            print(f"  → Need additional discriminator (e.g., staff-crossing, vertical extent)")

if __name__ == "__main__":
    enhanced_analysis(
        "logs/homr_eval/20251206T_homr_heuristic_final/metrics.json",
        "logs/homr_eval/20251206T_homr_diagnosis/page_3/page_3_candidate_stats.csv",
        "logs/homr_eval/20251206T_homr_heuristic_final/page_3/page_3_detections.json",
        "data/evaluation/images/page_3.png"
    )
