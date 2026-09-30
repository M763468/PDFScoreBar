import argparse
import json
from typing import List, Tuple

import cv2

from src.measure_numbering.builder import SystemBuilder
from src.measure_numbering.types import Barline, BBox, Staff


def load_local_gt(json_path: str) -> Tuple[List[Staff], List[Barline]]:
    """
    Loads staff and barline data from detection JSON.
    Auto-detects format (list of boxes OR dictionary with 'predictions').
    """
    with open(json_path, "r") as f:
        data = json.load(f)

    staves = []
    barlines = []

    # Format A: homr evaluator detections.json
    # {"image": "...", "predictions": [{"pred_bbox": ..., "system_index": ...}]}
    if isinstance(data, dict) and "predictions" in data:
        predictions = data["predictions"]
        for pred in predictions:
            # Differentiate Staff vs Barline
            # homr detections.json typically ONLY contains BARLINES.
            # Staves are NOT in that JSON usually, unless we added them.
            # HOWEVER, we can INFER staves from system_index? No.
            # We strictly need STAVES to run SystemBuilder.

            # If we don't have staves, we create dummy staves based on barline vertical extents?
            # Or we look for a separate staff json?
            # Let's assume for this specific test file, it might contain only barlines.

            bbox = pred.get("orig_bbox") or pred.get("pred_bbox")
            x1, y1, x2, y2 = bbox
            pred.get("system_index")

            # Treat everything as barline first
            barlines.append(Barline(bbox=BBox(x1, y1, x2, y2)))

        # Mock Staves for visualization if missing
        # We need Staves input to test System Inference.
        # If input is just barlines, we can't really test "Group Staves".
        # We need a file that has STAVES.
        pass

    # Format B: List of objects (DeepScores or custom GT)
    elif isinstance(data, list):
        for item in data:
            bbox = item.get("bbox") or item.get("barline_location") or item.get("box")
            if not bbox:
                continue
            x1, y1, x2, y2 = bbox

            label = item.get("label", "barline")
            if label == "staff":
                staves.append(Staff(bbox=BBox(x1, y1, x2, y2)))
            else:
                barlines.append(Barline(bbox=BBox(x1, y1, x2, y2)))

    return staves, barlines


def visualize_systems(image_path: str, json_path: str, output_path: str):
    print(f"Processing {image_path} with {json_path}...")

    # Load Image
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load image {image_path}")
        return

    # Load Data
    staves, barlines = load_local_gt(json_path)

    # If we lack staves in GT (likely), use a dummy generator from image?
    # Or better: Use homr output which definitely has staves.
    # For this visualization, let's try to load from a homr detection json if available.

    if not staves:
        print("Warning: No staves found in JSON. Visualization might be empty.")

    # Run System Builder
    builder = SystemBuilder()
    systems = builder.build_systems(staves, barlines)

    print(f"Detected {len(systems)} systems.")

    # Visualize
    # Colors for systems
    colors = [
        (255, 0, 0),  # Blue
        (0, 255, 0),  # Green
        (0, 0, 255),  # Red
        (255, 255, 0),  # Cyan
        (255, 0, 255),  # Magenta
        (0, 255, 255),  # Yellow
    ]

    overlay = img.copy()
    alpha = 0.4

    for i, system in enumerate(systems):
        color = colors[i % len(colors)]

        # Draw bounding box for the whole system (union of staves)
        # and color individual staves

        sys_x1, sys_y1, sys_x2, sys_y2 = 99999, 99999, 0, 0

        for staff in system.staves:
            s_bbox = staff.bbox
            # Draw filled rect for staff
            cv2.rectangle(
                overlay,
                (int(s_bbox.x1), int(s_bbox.y1)),
                (int(s_bbox.x2), int(s_bbox.y2)),
                color,
                -1,
            )

            sys_x1 = min(sys_x1, s_bbox.x1)
            sys_y1 = min(sys_y1, s_bbox.y1)
            sys_x2 = max(sys_x2, s_bbox.x2)
            sys_y2 = max(sys_y2, s_bbox.y2)

        # Draw system bounding box
        if system.staves:
            cv2.rectangle(img, (int(sys_x1), int(sys_y1)), (int(sys_x2), int(sys_y2)), color, 2)
            cv2.putText(
                img,
                f"Sys {i + 1}",
                (int(sys_x1), int(sys_y1) - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
            )

    # Blend overlay
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

    # Save
    cv2.imwrite(output_path, img)
    print(f"Saved visualization to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    visualize_systems(args.image, args.json, args.output)
