
import argparse
import json
import cv2
import numpy as np
from pathlib import Path
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--numbering-json", type=Path, required=True)
    parser.add_argument("--notehead-mask", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--target-measures", type=int, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--vertical-margin", type=int, default=80)
    
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.numbering_json, 'r') as f:
        data = json.load(f)
    
    mask = cv2.imread(str(args.notehead_mask), cv2.IMREAD_GRAYSCALE)
    image = cv2.imread(str(args.image)) # Load original for context
    
    h_img, w_img = image.shape[:2]
    h_mask, w_mask = mask.shape[:2]
    scale_x = w_mask / w_img
    scale_y = h_mask / h_img
    
    _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    
    # Test Erosion
    kernel = np.ones((3,3), np.uint8)
    eroded_mask = cv2.erode(bin_mask, kernel, iterations=1)

    for page in data["pages"]:
        for system in page["systems"]:
            for measure in system["measures"]:
                if measure["number"] in args.target_measures:
                    x1, y1, x2, y2 = measure["bbox"]
                    
                    print(f"--- Measure {measure['number']} ---")
                    print(f"BBox: {x1}, {y1}, {x2}, {y2}")
                    
                    # 1. No Margin
                    mx1 = int(x1 * scale_x); my1 = int(y1 * scale_y)
                    mx2 = int(x2 * scale_x); my2 = int(y2 * scale_y)
                    roi_no_margin = bin_mask[my1:my2, mx1:mx2]
                    count_no_margin = cv2.countNonZero(roi_no_margin)
                    print(f"Pixel Count (No Margin): {count_no_margin}")
                    
                    # 2. With Margin
                    margin_y = int(args.vertical_margin * scale_y)
                    my1_m = max(0, my1 - margin_y)
                    my2_m = min(h_mask, my2 + margin_y)
                    roi_margin = bin_mask[my1_m:my2_m, mx1:mx2]
                    count_margin = cv2.countNonZero(roi_margin)
                    print(f"Pixel Count (Margin {args.vertical_margin}): {count_margin}")

                    # Eroded Count
                    roi_eroded = eroded_mask[my1_m:my2_m, mx1:mx2]
                    count_eroded = cv2.countNonZero(roi_eroded)
                    print(f"Pixel Count (Eroded, Margin {args.vertical_margin}): {count_eroded}")
                    
                    # Save Debug Images
                    # Crop from original mask (scaled up for visibility?) No, save as is.
                    out_path = args.output_dir / f"debug_M{measure['number']}_mask.png"
                    cv2.imwrite(str(out_path), roi_margin)
                    
                    # Crop from original image with mask overlay
                    roi_img = image[max(0, y1-args.vertical_margin):min(h_img, y2+args.vertical_margin), x1:x2].copy()
                    
                    # Create mask overlay on ROI
                    # We need to extract the corresponding mask region and resize it to ROI size
                    # ROI coords in mask space:
                    mask_crop = bin_mask[my1_m:my2_m, mx1:mx2]
                    if mask_crop.size > 0:
                        mask_resized = cv2.resize(mask_crop, (roi_img.shape[1], roi_img.shape[0]), interpolation=cv2.INTER_NEAREST)
                        # Paint green
                        roi_img[mask_resized > 0] = [0, 255, 0]
                        
                    cv2.imwrite(str(args.output_dir / f"debug_M{measure['number']}_overlay.png"), roi_img)

if __name__ == "__main__":
    main()
