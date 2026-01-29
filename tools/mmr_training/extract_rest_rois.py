import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description="Extract ROIs for multi-measure rests from numbering JSON and notehead mask."
    )
    parser.add_argument("--numbering-json", type=Path, required=True, help="Path to numbering JSON")
    parser.add_argument(
        "--notehead-mask", type=Path, required=True, help="Path to notehead mask PNG"
    )
    parser.add_argument("--image", type=Path, required=True, help="Path to original image")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Directory to save ROI crops"
    )
    parser.add_argument(
        "--threshold", type=int, default=50, help="Max pixels of notehead to consider 'empty'"
    )
    parser.add_argument(
        "--vertical-margin",
        type=int,
        default=80,
        help="Vertical margin (px) to check above/below staff",
    )
    parser.add_argument(
        "--erode-iter", type=int, default=1, help="Iterations of erosion to remove noise"
    )

    args = parser.parse_args()
    ensure_dir(args.output_dir)

    # Load data
    with open(args.numbering_json, "r") as f:
        data = json.load(f)

    mask = cv2.imread(str(args.notehead_mask), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        print(f"Error: Could not read mask: {args.notehead_mask}")
        sys.exit(1)

    image = cv2.imread(str(args.image))
    if image is None:
        print(f"Error: Could not read image: {args.image}")
        sys.exit(1)

    # Ensure mask and image sizes match (or scale mask to image)
    h_img, w_img = image.shape[:2]
    h_mask, w_mask = mask.shape[:2]

    scale_x = w_mask / w_img
    scale_y = h_mask / h_img

    # Binarize mask just in case
    _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    # Erode mask
    if args.erode_iter > 0:
        kernel = np.ones((3, 3), np.uint8)
        proc_mask = cv2.erode(bin_mask, kernel, iterations=args.erode_iter)
    else:
        proc_mask = bin_mask

    count_empty = 0
    count_total = 0

    for page in data["pages"]:
        for system in page["systems"]:
            for measure in system["measures"]:
                count_total += 1
                m_num = measure["number"]
                bbox = measure["bbox"]  # [x1, y1, x2, y2]

                x1, y1, x2, y2 = bbox

                # Scale to mask coordinates
                margin_y_scaled = int(args.vertical_margin * scale_y)
                mx1 = max(0, int(x1 * scale_x))
                my1 = max(0, int(y1 * scale_y) - margin_y_scaled)
                mx2 = min(w_mask, int(x2 * scale_x))
                my2 = min(h_mask, int(y2 * scale_y) + margin_y_scaled)

                # Clamp
                mx1 = max(0, mx1)
                my1 = max(0, my1)
                mx2 = min(w_mask, mx2)
                my2 = min(h_mask, my2)

                roi_mask = proc_mask[my1:my2, mx1:mx2]
                pixel_count = cv2.countNonZero(roi_mask)

                if pixel_count <= args.threshold:
                    count_empty += 1
                    # It's a candidate! Extract ROI from Original Image.
                    roi_y1 = max(0, y1 - 30)
                    roi_y2 = min(h_img, y1 + (y2 - y1) // 2 + 30)  # Capture top half + margin

                    roi_img = image[roi_y1:roi_y2, x1:x2]

                    out_name = f"measure_{m_num}_page_{page['page_number']}.png"
                    cv2.imwrite(str(args.output_dir / out_name), roi_img)
                    print(f"Extracted ROI for Measure {m_num}: {pixel_count} pixels")

    print(f"Total Measures: {count_total}")
    print(f"Empty Candidates: {count_empty}")


if __name__ == "__main__":
    main()
