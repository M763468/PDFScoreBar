import cv2
import numpy as np
import argparse
import json
from pathlib import Path
from typing import List, Tuple

import sys

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))
from src.measure_numbering.pipeline import StaffExtractor

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--staff-mask", required=True, help="Path to staff mask")
    parser.add_argument("--barlines", required=True, help="GT Barlines JSON")
    parser.add_argument("--output-img", required=True)
    args = parser.parse_args()

    # 1. Load Image & Binarize
    img = cv2.imread(args.image)
    if img is None:
        print(f"Failed to load image: {args.image}")
        sys.exit(1)
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, ink_bin = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = img.shape[:2]

    # 2. Extract Staff Bands using Pipeline's Extractor
    extractor = StaffExtractor()
    # Note: StaffExtractor expects target_size to scale mask to image.
    # We pass the image size (w, h).
    staves = extractor.extract(Path(args.staff_mask), (w, h))
    
    # Sort just in case
    staves.sort(key=lambda s: s.bbox.y1)
    
    # Convert to bands format (y1, y2)
    bands = [(s.bbox.y1, s.bbox.y2) for s in staves]
    
    print(f"Detected {len(bands)} staff bands using StaffExtractor.")

    # 3. Load Barlines
    with open(args.barlines) as f:
        raw_bars = json.load(f)
    
    # Normalize barlines
    barlines = []
    for b in raw_bars:
        # Handle various formats
        bbox = None
        if isinstance(b, list): bbox = b
        elif "barline_location" in b: bbox = b["barline_location"]
        elif "bbox" in b: bbox = b["bbox"]
        
        if bbox:
            barlines.append(bbox)

    # 4. Check Connectivity for adjacent pairs
    results = []
    
    debug_img = img.copy()

    for i in range(len(bands) - 1):
        y1_bot = bands[i][1]
        y2_top = bands[i+1][0]
        
        # Verify gap
        gap_h = y2_top - y1_bot
        
        if gap_h <= 0:
            print(f"Pair {i}-{i+1}: Overlap or touch? Gap={gap_h}. Skipping.")
            continue

        # Find barlines that might bridge this gap
        # We look for barlines that exist in Staff i AND Staff i+1 ?
        # Or simply check "Is there a vertical line in the gap at X positions where we see barlines nearby?"
        
        # Strategy:
        # 1. Gather all barline X-centers that roughly intersect the vertical range of Staff i OR Staff i+1.
        #    Actually, we care about barlines that might be drawn *through* the gap.
        #    Usually, a system barline is a single long vertical line.
        #    Or it's segments that align.
        
        # Let's inspect the GAP region for vertical ink.
        gap_roi = ink_bin[y1_bot:y2_top, :]
        
        # Find vertical lines in gap
        # Morphological opening with vertical kernel to isolate vertical structure
        v_kernel_size = max(3, int(gap_h * 0.5)) # Kernel half the gap height
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_size))
        gap_verticals = cv2.morphologyEx(gap_roi, cv2.MORPH_OPEN, v_kernel)
        
        # Count detected verticals
        # We can analyze connected components in the gap
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(gap_verticals)
        
        connected_barlines = 0
        
        for j in range(1, num_labels):
            gw = stats[j, cv2.CC_STAT_WIDTH]
            gh = stats[j, cv2.CC_STAT_HEIGHT]
            gx = stats[j, cv2.CC_STAT_LEFT]
            gy = stats[j, cv2.CC_STAT_TOP]
            
            # Filter: Must span most of the gap?
            # User said "black line connecting the staves".
            # So height should be close to gap_h.
            if gh > gap_h * 0.8:
                connected_barlines += 1
                # Draw on debug
                cv2.rectangle(debug_img, (gx, y1_bot + gy), (gx + gw, y1_bot + gy + gh), (0, 0, 255), 2)
        
        print(f"Pair {i}({y1_bot}) -> {i+1}({y2_top}): Gap={gap_h}px. Detected Connectors={connected_barlines}")
        
        # Draw Gap box
        color = (0, 255, 0) if connected_barlines > 0 else (200, 200, 200)
        cv2.rectangle(debug_img, (0, y1_bot), (gray.shape[1], y2_top), color, 1)
        cv2.putText(debug_img, f"Gap {gap_h}px, Conn={connected_barlines}", (50, (y1_bot+y2_top)//2), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)

    cv2.imwrite(args.output_img, debug_img)
    print(f"Saved debug overlay to {args.output_img}")

if __name__ == "__main__":
    main()
