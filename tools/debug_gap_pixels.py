import cv2
import numpy as np
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))
from src.measure_numbering.pipeline import StaffExtractor

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--staff-mask", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    # 1. Load Image
    img = cv2.imread(args.image)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bin_img = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = img.shape[:2]

    # 2. Extract Steps
    extractor = StaffExtractor()
    staves = extractor.extract(Path(args.staff_mask), (w, h))
    staves.sort(key=lambda s: s.bbox.y1)
    
    debug_vis = img.copy()

    print(f"Checking {len(staves)} staves...")
    
    for i in range(len(staves) - 1):
        s1 = staves[i]
        s2 = staves[i+1]
        
        y1_bot = s1.bbox.y2
        y2_top = s2.bbox.y1
        gap_h = y2_top - y1_bot
        
        print(f"Pair {i}->{i+1}: y1_bot={y1_bot}, y2_top={y2_top}, Gap={gap_h}")
        
        # Color Code:
        # Red Box = Gap Region
        # Blue Text = Logic Decision
        
        # 1. Check Overlap
        if gap_h <= 0:
            print("  -> OVERLAP/TOUCH (Currently treated as True)")
            cv2.line(debug_vis, (0, y1_bot), (w, y1_bot), (0, 0, 255), 2)
            cv2.putText(debug_vis, f"OVERLAP Gap={gap_h}", (100, y1_bot), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            continue
            
        # 2. Check Pixels
        # Draw Gap Region
        cv2.rectangle(debug_vis, (0, y1_bot), (w, y2_top), (0, 255, 255), 1) # Yellow
        
        gap_roi = bin_img[y1_bot:y2_top, :]
        v_kernel_size = max(3, int(gap_h * 0.5)) 
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_size))
        gap_verticals = cv2.morphologyEx(gap_roi, cv2.MORPH_OPEN, v_kernel)
        
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(gap_verticals)
        
        connected_count = 0
        for j in range(1, num_labels):
            gw = stats[j, cv2.CC_STAT_WIDTH]
            gh = stats[j, cv2.CC_STAT_HEIGHT]
            gx = stats[j, cv2.CC_STAT_LEFT]
            gy = stats[j, cv2.CC_STAT_TOP]
            
            if gh > gap_h * 0.8:
                connected_count += 1
                # Draw detected vertical in Green
                cv2.rectangle(debug_vis, (gx, y1_bot + gy), (gx + gw, y1_bot + gy + gh), (0, 255, 0), 2)
        
        print(f"  -> Detected {connected_count} connections")
        
        label = f"Gap={gap_h}, Conn={connected_count}"
        color = (0, 255, 0) if connected_count > 0 else (0, 0, 0)
        cv2.putText(debug_vis, label, (50, (y1_bot+y2_top)//2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        
    cv2.imwrite(args.output, debug_vis)
    print(f"Saved debug view to {args.output}")

if __name__ == "__main__":
    main()
