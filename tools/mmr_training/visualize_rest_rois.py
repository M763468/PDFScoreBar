import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(
        description="Visualize extracted ROIs for multi-measure rests with notehead context."
    )
    parser.add_argument("--numbering-json", type=Path, required=True, help="Path to numbering JSON")
    parser.add_argument(
        "--notehead-mask", type=Path, required=True, help="Path to notehead mask PNG"
    )
    parser.add_argument("--image", type=Path, required=True, help="Path to original image")
    parser.add_argument(
        "--output-image", type=Path, required=True, help="Path to save overlay image"
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

    # Load data
    with open(args.numbering_json, "r") as f:
        data = json.load(f)

    mask = cv2.imread(str(args.notehead_mask), cv2.IMREAD_GRAYSCALE)
    image = cv2.imread(str(args.image))

    if mask is None or image is None:
        print("Error: Could not read input images.")
        sys.exit(1)

    h_img, w_img = image.shape[:2]
    h_mask, w_mask = mask.shape[:2]
    scale_x = w_mask / w_img
    scale_y = h_mask / h_img

    _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    # Erode mask to remove noise (text, thin lines)
    if args.erode_iter > 0:
        kernel = np.ones((3, 3), np.uint8)
        proc_mask = cv2.erode(bin_mask, kernel, iterations=args.erode_iter)
    else:
        proc_mask = bin_mask

    # Create a visible notehead layer (Green areas) using PROCESSED mask
    notehead_vis = np.zeros_like(image)
    # Scale mask if necessary to match image size for visualization
    mask_resized = cv2.resize(proc_mask, (w_img, h_img), interpolation=cv2.INTER_NEAREST)
    notehead_vis[mask_resized > 0] = [0, 255, 0]  # Bright Green

    # Alpha blend noteheads onto original score
    overlay = cv2.addWeighted(image, 0.7, notehead_vis, 0.3, 0)

    count = 0
    for page in data["pages"]:
        for system in page["systems"]:
            for measure in system["measures"]:
                x1, y1, x2, y2 = measure["bbox"]

                # Check density with margin (logic remains on the mask space)
                margin_y_scaled = int(args.vertical_margin * scale_y)
                mx1 = max(0, int(x1 * scale_x))
                my1 = max(0, int(y1 * scale_y) - margin_y_scaled)
                mx2 = min(w_mask, int(x2 * scale_x))
                my2 = min(h_mask, int(y2 * scale_y) + margin_y_scaled)

                roi_mask = proc_mask[my1:my2, mx1:mx2]
                pixel_count = cv2.countNonZero(roi_mask)

                # Draw ALL measures faintly in Blue for context
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 100, 0), 1)

                if pixel_count <= args.threshold:
                    count += 1
                    # Draw ROI rectangle for candidates (Bold Red)
                    # Heuristic ROI for rest number
                    roi_y1 = max(0, y1 - 30)
                    roi_y2 = min(h_img, y1 + (y2 - y1) // 2 + 30)

                    cv2.rectangle(overlay, (x1, roi_y1), (x2, roi_y2), (0, 0, 255), 3)
                    cv2.putText(
                        overlay,
                        f"REST M{measure['number']}",
                        (x1, roi_y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.0,
                        (0, 0, 255),
                        2,
                    )

    cv2.imwrite(str(args.output_image), overlay)
    print(f"Detailed overlay saved to {args.output_image}")
    print(f"Candidates: {count}")


if __name__ == "__main__":
    main()
