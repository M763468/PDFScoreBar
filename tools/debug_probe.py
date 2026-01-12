
import cv2
import numpy as np
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--x", type=int, required=True)
    parser.add_argument("--y1", type=int, required=True)
    parser.add_argument("--y2", type=int, required=True)
    parser.add_argument("--width", type=int, default=4)
    args = parser.parse_args()
    
    img = cv2.imread(args.image)
    if img is None:
        print("Failed to load image")
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    x_center = args.x
    y1 = args.y1
    y2 = args.y2
    w_half = args.width // 2
    
    x1 = max(0, x_center - w_half)
    x2 = min(gray.shape[1]-1, x_center + w_half) # probe_width window (e.g. 4px usually implies index to index+width or center +/- width/2? detect_probe_scan usually uses x-w/2 to x+w/2)
    
    # Extract strip
    strip = gray[y1:y2+1, x1:x2+1]
    
    print(f"Inspecting strip at x[{x1}:{x2+1}], y[{y1}:{y2+1}]")
    print(f"Strip shape: {strip.shape}")
    print(f"Min pixel: {strip.min()}, Max pixel: {strip.max()}, Mean: {strip.mean()}")
    
    # Check Ratios for various thresholds
    thresholds = [150, 180, 200, 210, 220, 230, 240, 250]
    for thr in thresholds:
        ink = (strip < thr).astype(np.uint8)
        print(f"Threshold {thr}: Ratio={ink.mean():.4f}")
        
    # Check per-column ratio
    print("\nPer-column ratios at Threshold 230:")
    ink230 = (strip < 230).astype(np.uint8)
    col_ratios = ink230.mean(axis=0)
    for i, r in enumerate(col_ratios):
        print(f"Col {x1+i}: {r:.4f}")

if __name__ == "__main__":
    main()
