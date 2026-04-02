import cv2
import numpy as np
import sys
from pathlib import Path

def _box_mask_overlap_ratio(mask, box):
    h_img, w_img = mask.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    y_lo, y_hi = max(0, min(y1, y2)), min(h_img, max(y1, y2))
    x_lo, x_hi = max(0, min(x1, x2)), min(w_img, max(x1, x2))
    if y_hi <= y_lo or x_hi <= x_lo:
        return 0.0
    crop = mask[y_lo:y_hi, x_lo:x_hi]
    return float((crop > 0).sum()) / float(max(1, crop.size))

def main():
    # Box from Prokofiev 5 P1 FP
    box = (280.0, 3517.0, 281.0, 3588.0)
    image_path = Path("data/evaluation2/images/Va__Prokofiev_Symphony5/page_001.png")
    mask_path = Path("logs/hybrid_generalization/verify_fixed_v10/hybrid_results/page_001_staff_mask.png")
    
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        print(f"Mask not found: {mask_path}")
        return
        
    overlap = _box_mask_overlap_ratio(mask, box)
    print(f"Overlap with staff_mask: {overlap:.4f}")

if __name__ == "__main__":
    main()
