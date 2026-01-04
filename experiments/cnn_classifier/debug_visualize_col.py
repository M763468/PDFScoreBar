import argparse
import cv2
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--band-y1", type=int, required=True)
    parser.add_argument("--band-y2", type=int, required=True)
    parser.add_argument("--x-cols", type=str, required=True, help="Comma separated x values")
    args = parser.parse_args()
    
    img = cv2.imread(args.image_path)
    if img is None:
        print("Image not found")
        return
        
    x_vals = [int(x) for x in args.x_cols.split(",")]
    y1 = args.band_y1
    y2 = args.band_y2
    
    # Draw Band
    cv2.rectangle(img, (0, y1), (img.shape[1], y2), (0, 255, 255), 2) # Yellow Box
    
    # Draw Lines
    for x in x_vals:
        # Red Line, thickness 2
        cv2.line(img, (x, y1), (x, y2), (0, 0, 255), 2)
        # Label
        cv2.putText(img, str(x), (x, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        
    cv2.imwrite(args.output_path, img)
    print(f"Saved to {args.output_path}")

if __name__ == "__main__":
    main()
