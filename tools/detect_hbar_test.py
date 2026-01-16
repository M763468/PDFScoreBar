import cv2
import numpy as np
import argparse
from pathlib import Path

def detect_hbar(image_path):
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Error reading {image_path}")
        return False

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    h, w = binary.shape
    
    # Define H-bar kernel
    # Long horizontal kernel
    k_width = max(15, int(w * 0.3)) # At least 15px or 30% of width
    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_width, 1))
    
    # Detect horizontal lines
    detected_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horiz_kernel, iterations=1)
    
    # Filter for thickness?
    # H-bars are usually thick (heavy beams). Staff lines are thin.
    # If we erode vertically, staff lines should disappear.
    
    thick_kernel = np.ones((3, 1), np.uint8) # 3px high
    thick_lines = cv2.erode(detected_lines, thick_kernel, iterations=1)
    
    # Check if anything remains
    count = cv2.countNonZero(thick_lines)
    
    vis = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    vis[thick_lines > 0] = (0, 0, 255) # Red for detection
    
    cv2.imwrite(str(image_path).replace(".png", "_hbar_debug.png"), vis)
    
    print(f"{image_path}: Px={count} (Threshold usually > 50?)")
    return count > 20

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs='+')
    args = parser.parse_args()
    
    for img in args.images:
        detect_hbar(img)
