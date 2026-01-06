
import json
import cv2
import numpy as np
from pathlib import Path
import argparse

def analyze_box(image, box, label):
    x1, y1, x2, y2 = box
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        print(f"Empty crop for {label}")
        return

    # Invert to get ink as positive
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
    ink = 255 - gray
    
    # Horizontal projection (sum vertical ink)
    proj = np.sum(ink, axis=0)
    
    # Normalize
    proj = proj / np.max(proj) if np.max(proj) > 0 else proj
    
    # Simple peak detection
    peaks = []
    threshold = 0.5
    in_peak = False
    for i, val in enumerate(proj):
        if val > threshold and not in_peak:
            in_peak = True
            peaks.append(i)
        elif val < threshold and in_peak:
            in_peak = False
            
    print(f"Measure {label}: Box width {x2-x1}px. Found {len(peaks)} ink peaks in projection.")
    return len(peaks)

def main():
    # Page 006 of Prokofiev 1
    img_path = Path("data/evaluation2/images/Va_Prokofiev_Symphony1/page_006.png")
    gt_path = Path("data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_006/boxes_sorted_v20260106.json")
    
    if not img_path.exists():
        print(f"Image not found: {img_path}")
        return

    print(f"Loading {img_path}...")
    image = cv2.imread(str(img_path))
    
    with open(gt_path) as f:
        gt = json.load(f)
        
    print("\n--- Analyzing Double Barlines on Page 006 ---")
    for item in gt:
        if item.get("barline_type") == "double_barline":
            analyze_box(image, item["barline_location"], str(item["measure_number"]))

if __name__ == "__main__":
    main()
