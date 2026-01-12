
import cv2
import numpy as np
import argparse
from pathlib import Path

def test():
    img_path = "data/evaluation2/images/Sibelius-Violin_Concerto-Viola/page_004.png"
    if not Path(img_path).exists():
        print(f"Image not found: {img_path}")
        return

    img = cv2.imread(img_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    ink_threshold = 230
    ink = (gray < ink_threshold).astype(np.uint8)
    
    # FN coordinates (from filename)
    # Sibelius-Violin_Concerto-Viola_page_004_FN_2715_3167.png
    # Sibelius-Violin_Concerto-Viola_page_004_FN_2725_3168.png
    # Crop images were labeled X_Y
    targets = [(2715, 3167), (2725, 3168)]
    
    # Assume global_height ~ 240 (roughly for this score)
    # Let's check a small region
    h_ext = 120
    w_ext = 2
    
    print(f"Testing ink ratios at targets (threshold {ink_threshold}):")
    for tx, ty in targets:
        # Before closing
        y1, y2 = ty - h_ext, ty + h_ext
        x1, x2 = tx - w_ext, tx + w_ext
        
        strip = ink[y1:y2+1, x1:x2+1]
        ratio_orig = strip.sum() / float(strip.size)
        
        print(f"Target ({tx}, {ty}):")
        print(f"  Ratio (Orig):   {ratio_orig:.4f}")
        
        for k_size in [5, 9, 13, 21]:
            kernel = np.ones((k_size, 1), np.uint8)
            ink_closed = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel)
            strip_closed = ink_closed[y1:y2+1, x1:x2+1]
            ratio_closed = strip_closed.sum() / float(strip_closed.size)
            print(f"  Ratio (K={k_size}): {ratio_closed:.4f}")

if __name__ == "__main__":
    test()
