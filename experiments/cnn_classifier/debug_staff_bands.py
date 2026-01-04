
import cv2
import numpy as np
from pathlib import Path
import sys
import argparse

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from tools.run_gt_rebuild_hybrid_eval import staff_bands_from_mask

def debug_page(image_path, mask_path):
    print(f"Image: {image_path}")
    print(f"Mask: {mask_path}")
    
    img = cv2.imread(str(image_path))
    mask_img = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    
    if mask_img is None:
        print("Failed to load mask")
        return
        
    _, bin_mask = cv2.threshold(mask_img, 1, 255, cv2.THRESH_BINARY)
    
    if img.shape[:2] != bin_mask.shape[:2]:
        print(f"Resizing mask from {bin_mask.shape} to {img.shape}")
        h, w = img.shape[:2]
        bin_mask = cv2.resize(bin_mask, (w, h), interpolation=cv2.INTER_NEAREST)
        
    bands = staff_bands_from_mask(bin_mask)
    print(f"Found {len(bands)} bands: {bands}")
    
    # Draw bands
    vis = img.copy()
    for y1, y2 in bands:
        cv2.rectangle(vis, (0, y1), (vis.shape[1], y2), (0, 0, 255), 2)
        
    out_path = "debug_bands.png"
    cv2.imwrite(out_path, vis)
    print(f"Saved visualization to {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image_path")
    parser.add_argument("mask_path")
    args = parser.parse_args()
    
    debug_page(args.image_path, args.mask_path)
