import cv2
import numpy as np
import argparse
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))
from src.measure_numbering.pipeline import StaffExtractor
from src.measure_numbering.builder import SystemBuilder
from src.measure_numbering.types import Barline, BBox

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--staff-mask", required=True)
    parser.add_argument("--barlines", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    # 1. Load Image
    img = cv2.imread(args.image)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bin_img = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = img.shape[:2]

    # 2. Extract Staves
    extractor = StaffExtractor()
    staves = extractor.extract(Path(args.staff_mask), (w, h))
    staves.sort(key=lambda s: s.bbox.y1)
    
    # 3. Load Barlines
    with open(args.barlines) as f:
        raw_bars = json.load(f)
    barlines = []
    for b in raw_bars:
        bbox = None
        if isinstance(b, list): bbox = b
        elif "barline_location" in b: bbox = b["barline_location"]
        elif "x1" in b: bbox = [b["x1"], b["y1"], b["x2"], b["y2"]]
        elif "bbox" in b: bbox = b["bbox"]
        if bbox:
            barlines.append(Barline(bbox=BBox(*bbox)))
            
    # Assign barlines using SystemBuilder helper (copy-paste logic or use it if accessible?)
    # SystemBuilder._assign_barlines_to_staves is instance method.
    builder = SystemBuilder()
    builder._assign_barlines_to_staves(staves, barlines)
    
    debug_vis = img.copy()

    print(f"Checking {len(staves)} staves with Aligned Logic...")
    
    ALIGN_TOL = 10
    
    for i in range(len(staves) - 1):
        s1 = staves[i]
        s2 = staves[i+1]
        
        y1_bot = s1.bbox.y2
        y2_top = s2.bbox.y1
        gap_h = y2_top - y1_bot
        
        # Visualize Gap
        cv2.rectangle(debug_vis, (0, y1_bot), (w, y2_top), (200, 200, 200), 1)

        if gap_h <= 0:
            print(f"Pair {i}->{i+1}: OVERLAP. Skipping check (Assume False for test).")
            continue

        valid_connectors = 0
        
        # Iterate Aligned Barlines
        for b1 in s1.barlines:
            c1 = (b1.bbox.x1 + b1.bbox.x2) / 2
            for b2 in s2.barlines:
                c2 = (b2.bbox.x1 + b2.bbox.x2) / 2
                
                if abs(c1 - c2) <= ALIGN_TOL:
                    # Found aligned pair. Check ink in GAP between them.
                    # ROI X range: union of b1/b2 widths or narrow strip around center?
                    # Use center +/- width/2
                    # Actually, assume barline width ~ 5px?
                    # Let's take [min_x, max_x] of the two barlines, expanded slightly.
                    x_start = min(b1.bbox.x1, b2.bbox.x1)
                    x_end = max(b1.bbox.x2, b2.bbox.x2)
                    
                    # Ensure within bounds
                    x_start = max(0, x_start - 2)
                    x_end = min(w, x_end + 2)
                    
                    roi = bin_img[y1_bot:y2_top, x_start:x_end]
                    
                    # Check density or vertical line
                    # Simple check: Pixel density > threshold?
                    # Or Morph Open?
                    # If it's a line, a vertical projection should show a peak.
                    # Or just: count black pixels?
                    # If completely empty -> 0.
                    # If line -> height * width.
                    
                    # Strict Check: Vertical Morph with kernel ~80% gap height
                    if gap_h < 5: 
                         # Tiny gap with aligned barlines -> implicit connection
                         valid_connectors += 1
                         continue
                         
                    v_kernel_size = int(gap_h * 0.8)
                    if v_kernel_size < 1: v_kernel_size = 1
                    
                    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_size))
                    closed = cv2.morphologyEx(roi, cv2.MORPH_OPEN, kernel)
                    
                    if cv2.countNonZero(closed) > 0:
                        valid_connectors += 1
                        # Draw green line at connection
                        cv2.line(debug_vis, (int((x_start+x_end)/2), y1_bot), (int((x_start+x_end)/2), y2_top), (0, 255, 0), 2)
                    else:
                        # Draw red tick (failed connection)
                        cv2.line(debug_vis, (int((x_start+x_end)/2), y1_bot), (int((x_start+x_end)/2), y1_bot+10), (0, 0, 255), 2)

        print(f"Pair {i}->{i+1}: Gap={gap_h}, Aligned Connectors={valid_connectors}")
        label = f"Conn={valid_connectors}"
        color = (0, 200, 0) if valid_connectors > 0 else (0, 0, 0)
        cv2.putText(debug_vis, label, (50, (y1_bot+y2_top)//2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        
    cv2.imwrite(args.output, debug_vis)
    print(f"Saved test output to {args.output}")

if __name__ == "__main__":
    main()
