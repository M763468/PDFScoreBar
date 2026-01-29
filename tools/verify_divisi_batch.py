import argparse
import os
import sys
from pathlib import Path
from typing import List

import cv2

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.measure_numbering.builder import SystemBuilder
from src.measure_numbering.pipeline import StaffExtractor
from src.measure_numbering.types import Barline, BBox


def process_page(image_path: Path, mask_path: Path, output_path: Path):
    # 1. Load Image
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Failed to load image: {image_path}")
        return
    h, w = img.shape[:2]

    # 2. Extract Staves using Pipeline's Extractor
    extractor = StaffExtractor()
    staves = extractor.extract(mask_path, (w, h))

    # 3. Build Systems (using empty barlines to test Connectivity Logic Priority)
    # The logic prioritizes image connectivity. If image is passed, alignment check is skipped if connectivity fails.
    # Since we don't have Barlines, the fallback "Alignment Check" will effectively accept nothing (match_count=0).
    # This isolates the test to ONLY the new Connectivity Logic.
    builder = SystemBuilder()
    systems = builder.build_systems(staves, [], image=img)

    # 4. Visualize
    vis_img = img.copy()

    # Draw Staves (Blue)
    overlay = vis_img.copy()
    for s in staves:
        cv2.rectangle(overlay, (s.bbox.x1, s.bbox.y1), (s.bbox.x2, s.bbox.y2), (255, 0, 0), -1)
    cv2.addWeighted(overlay, 0.2, vis_img, 0.8, 0, vis_img)

    # Draw Systems (Boxes)
    for i, system in enumerate(systems):
        s_list = system.staves
        if not s_list:
            continue

        x1 = min(s.bbox.x1 for s in s_list)
        y1 = min(s.bbox.y1 for s in s_list)
        x2 = max(s.bbox.x2 for s in s_list)
        y2 = max(s.bbox.y2 for s in s_list)

        color = (0, 0, 255)  # Red (Single)
        thickness = 2
        label = f"Sys {i + 1} ({len(s_list)})"

        if len(s_list) > 1:
            color = (0, 255, 0)  # Green (Divisi)
            thickness = 3
            # Draw internal connections
            for j in range(len(s_list) - 1):
                s_curr = s_list[j]
                s_next = s_list[j + 1]
                cx = (s_curr.bbox.x1 + s_curr.bbox.x2) // 2
                cy1 = s_curr.bbox.y2
                cy2 = s_next.bbox.y1
                cv2.line(vis_img, (cx, cy1), (cx, cy2), (255, 0, 255), 2)

        cv2.rectangle(vis_img, (x1 - 10, y1 - 10), (x2 + 10, y2 + 10), color, thickness)
        cv2.putText(vis_img, label, (x1, y1 - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    cv2.imwrite(str(output_path), vis_img)
    print(
        f"Processed {image_path.name} -> {len(systems)} systems (Divisi: {[len(s.staves) for s in systems if len(s.staves) > 1]})"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image-dirs",
        nargs="+",
        required=True,
        help="Directories containing images (e.g., data/evaluation2/images/prokofiev1)",
    )
    parser.add_argument("--mask-root", required=True, help="Root of logs/hybrid_generalization")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Find all images
    images = []
    for d in args.image_dirs:
        images.extend(list(Path(d).glob("*.png")))

    images.sort()

    for img_path in images:
        # Find corresponding mask
        # Pattern: logs/hybrid_generalization/eval2_{corpus}_{page}/baseline/page_{n}/page_{n}/page_{n}_debug_3_staff.png
        # We need to fuzzy match the path based on page name
        page_name = img_path.stem  # e.g. "page_004"
        corpus = img_path.parent.name  # e.g. "prokofiev1"

        # Search for mask in subdirs
        search_pattern = f"eval2_{corpus}_{page_name}/**/{page_name}_debug_3_staff.png"
        matches = list(Path(args.mask_root).glob(search_pattern))

        if not matches:
            print(f"Skipping {img_path.name}: No mask found matching {search_pattern}")
            continue

        # Pick the first one (assuming baseline/sr variants are similar for staff mask)
        mask_path = matches[0]

        # Find Barlines (hybrid_predictions.json)
        # Expected: logs/hybrid_generalization/eval2_{corpus}_{page}/hybrid_predictions.json
        # Parent of mask_path is likely .../page_00X/baseline/page_00X/...
        # We need to go up to the experiment set root
        # Usually: mask_path is logs/hybrid_generalization/eval2_prokofievX_page_00Y/baseline/...
        # We want: logs/hybrid_generalization/eval2_prokofievX_page_00Y/hybrid_predictions.json

        # Robust search: 3 levels up from mask? mask_path.parts...
        # Let's search in mask_root for the predictions file corresponding to this page set
        pred_pattern = f"eval2_{corpus}_{page_name}/hybrid_predictions.json"
        pred_matches = list(Path(args.mask_root).glob(pred_pattern))

        barlines = []
        if pred_matches:
            import json

            try:
                with open(pred_matches[0]) as f:
                    raw = json.load(f)
                # Parse barlines from JSON
                # Format: List of [x1, y1, x2, y2] usually
                for b in raw:
                    bbox = None
                    if isinstance(b, list):
                        bbox = b
                    elif "x1" in b:
                        bbox = [b["x1"], b["y1"], b["x2"], b["y2"]]
                    if bbox:
                        barlines.append(Barline(bbox=BBox(*bbox)))
            except Exception as e:
                print(f"Error loading barlines for {page_name}: {e}")
        else:
            print(
                f"Warning: No hybrid_predictions.json found for {page_name}. Connectivity check will fail."
            )

        output_path = Path(args.output_dir) / f"{corpus}_{img_path.name}"
        process_page(img_path, mask_path, output_path, barlines)


def process_page(image_path: Path, mask_path: Path, output_path: Path, barlines: List[Barline]):
    # 1. Load Image
    img = cv2.imread(str(image_path))
    if img is None:
        return
    h, w = img.shape[:2]

    # 2. Extract Staves
    extractor = StaffExtractor()
    staves = extractor.extract(mask_path, (w, h))

    # 3. Build Systems
    builder = SystemBuilder()
    systems = builder.build_systems(staves, barlines, image=img)

    # 4. Visualize
    vis_img = img.copy()

    # Draw Staves (Blue)
    overlay = vis_img.copy()
    for s in staves:
        cv2.rectangle(overlay, (s.bbox.x1, s.bbox.y1), (s.bbox.x2, s.bbox.y2), (255, 0, 0), -1)
    cv2.addWeighted(overlay, 0.2, vis_img, 0.8, 0, vis_img)

    # Draw Systems (Boxes)
    for i, system in enumerate(systems):
        s_list = system.staves
        if not s_list:
            continue

        x1 = min(s.bbox.x1 for s in s_list)
        y1 = min(s.bbox.y1 for s in s_list)
        x2 = max(s.bbox.x2 for s in s_list)
        y2 = max(s.bbox.y2 for s in s_list)

        color = (0, 0, 255)  # Red (Single)
        thickness = 2
        label = f"Sys {i + 1} ({len(s_list)})"

        if len(s_list) > 1:
            color = (0, 255, 0)  # Green (Divisi)
            thickness = 3
            # Draw internal connections
            for j in range(len(s_list) - 1):
                s_curr = s_list[j]
                s_next = s_list[j + 1]
                cx = (s_curr.bbox.x1 + s_curr.bbox.x2) // 2
                cy1 = s_curr.bbox.y2
                cy2 = s_next.bbox.y1
                cv2.line(vis_img, (cx, cy1), (cx, cy2), (255, 0, 255), 2)

        cv2.rectangle(vis_img, (x1 - 10, y1 - 10), (x2 + 10, y2 + 10), color, thickness)
        cv2.putText(vis_img, label, (x1, y1 - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    cv2.imwrite(str(output_path), vis_img)
    print(
        f"Processed {image_path.name} -> {len(systems)} systems (Divisi: {[len(s.staves) for s in systems if len(s.staves) > 1]})"
    )


if __name__ == "__main__":
    main()
