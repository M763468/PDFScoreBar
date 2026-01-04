
# [EXPERIMENTAL] Statistical analysis of barline gaps and overlaps.
# Used to diagnose duplication issues in detector output on 2026-01-04.

import json
import numpy as np
from pathlib import Path
from typing import List, Tuple
import cv2
import sys

# Add src to path
sys.path.append(".")
from src.measure_numbering.types import BBox, Staff, Barline

def load_json(path: Path):
    with open(path, 'r') as f:
        return json.load(f)

def extract_staff_bands(mask_path: Path, target_size: Tuple[int, int], min_height: int = 10):
    # Reusing logic for consistency
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    h_mask, w_mask = mask.shape[:2]
    target_w, target_h = target_size
    scale_y = target_h / h_mask
    
    _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    kernel = np.ones((20, 1), np.uint8)
    dilated = cv2.dilate(bin_mask, kernel, iterations=1)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)
    
    bands = []
    for i in range(1, num_labels):
        y = stats[i, cv2.CC_STAT_TOP]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        w = stats[i, cv2.CC_STAT_WIDTH]
        if h >= min_height and w > 400:
            y1 = int(y * scale_y)
            y2 = int((y + h) * scale_y)
            bands.append((y1, y2))
    bands.sort(key=lambda b: b[0])
    return bands

def analyze():
    # Paths
    barlines_json = Path("logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10/final_predictions.json")
    staff_mask_path = Path("logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_3_staff.png")
    
    # Image size hardcoded from previous check
    W, H = 2700, 3600
    
    barlines_data = load_json(barlines_json)
    staff_bands = extract_staff_bands(staff_mask_path, (W, H))
    
    print(f"Loaded {len(barlines_data)} barlines.")
    print(f"Found {len(staff_bands)} staves.")
    
    # Assign barlines to staves
    # Use the relaxed logic from visualization
    staves_barlines = {i: [] for i in range(len(staff_bands))}
    
    for idx, box in enumerate(barlines_data):
        bx1, by1, bx2, by2 = box
        b_mid_y = (by1 + by2) / 2
        b_h = by2 - by1
        
        assigned = False
        for i, (sy1, sy2) in enumerate(staff_bands):
            # Check overlap
            inter_y1 = max(sy1, by1)
            inter_y2 = min(sy2, by2)
            
            if inter_y2 > inter_y1:
                overlap = inter_y2 - inter_y1
                staff_h = sy2 - sy1
                
                # Relaxed threshold
                if overlap > staff_h * 0.2 or overlap > 10:
                    staves_barlines[i].append(box)
                    assigned = True
                    # Don't break if we want to support multi-staff assignment (e.g. grand staff barline)
                    # But for analysis, let's just see.
        
        if not assigned:
            # print(f"Barline {idx} at y={by1}-{by2} not assigned to any staff.")
            pass

    # Analyze per staff
    for i in range(len(staff_bands)):
        bars = staves_barlines[i]
        # Sort by X
        bars.sort(key=lambda b: b[0])
        
        print(f"\nStaff {i} (y={staff_bands[i][0]}-{staff_bands[i][1]}): {len(bars)} barlines")
        
        if len(bars) == 0:
            continue
            
        # Check gaps
        prev_x2 = -1
        prev_idx = -1
        
        for j, b in enumerate(bars):
            x1, y1, x2, y2 = b
            center_x = (x1 + x2) / 2
            
            if j > 0:
                gap = x1 - prev_x2
                dist_center = center_x - prev_center_x
                
                if dist_center < 15: # Very close!
                    print(f"  [WARNING] Overlap/Duplicate? Idx {j-1} & {j}: Center Dist {dist_center:.1f}px (Gap {gap}px)")
                    print(f"    Box 1: {bars[j-1]}")
                    print(f"    Box 2: {b}")
            
            prev_x2 = x2
            prev_center_x = center_x
            
        # Check rightmost
        last_bar = bars[-1]
        print(f"  Rightmost Barline: x={last_bar[0]}-{last_bar[2]}")
        
        if last_bar[0] < W * 0.8:
            print(f"  [WARNING] Rightmost barline seems far from edge (Image W={W})")

if __name__ == "__main__":
    analyze()
