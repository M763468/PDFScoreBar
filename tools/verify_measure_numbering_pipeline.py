# [EXPERIMENTAL] Logic verification pipeline used for real-data proof of concept.
# Created on 2026-01-04. Refers to Page 10 specific paths.
# See src/measure_numbering/pipeline.py for the integrated version.

import json
import sys
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

# Add src to path
sys.path.append(".")

from src.measure_numbering.builder import SystemBuilder
from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import Barline, BBox, Page, Score, Staff


def extract_staff_bands(
    mask_path: Path, target_size: Tuple[int, int], min_height: int = 10
) -> List[Tuple[int, int, int, int]]:
    """
    Extract staff bands from a binary mask and scale to target size (W, H).
    Returns list of (y1, y2, x1, x2) tuples in target coordinates.
    """
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Mask not found: {mask_path}")

    h_mask, w_mask = mask.shape[:2]
    target_w, target_h = target_size

    scale_x = target_w / w_mask
    scale_y = target_h / h_mask

    # Binarize
    _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    # Merge staff lines into blocks using vertical dilation
    # Staff lines are thin, we want a block.
    # Estimated staff height is roughly 20-50px?
    kernel = np.ones((20, 1), np.uint8)
    dilated = cv2.dilate(bin_mask, kernel, iterations=1)

    # Find contours or use projection?
    # Using horizontal projection to find bands seems safer if lines are broken,
    # but connected components is standard for "staff blocks".
    # Assuming homr's debug_3_staff is a clean block mask?
    # Let's use connected components on the mask.

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)

    bands = []
    for i in range(1, num_labels):  # Skip background
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]

        # Filter: Must be wide enough to be a staff (e.g., > 1/3 of image width)
        # Image width is ~1660, so > 500px seems safe.
        if h >= min_height and w > 400:
            # Scale coordinates
            y1 = int(y * scale_y)
            y2 = int((y + h) * scale_y)
            x1 = int(x * scale_x)
            x2 = int((x + w) * scale_x)
            bands.append((y1, y2, x1, x2))

    # Sort by Y
    bands.sort(key=lambda b: b[0])
    return bands


def run_verification():
    # Paths
    barlines_json = Path(
        "logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10/end_recovered.json"
    )
    staff_mask_path = Path(
        "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_3_staff.png"
    )
    original_image_path = Path("data/training/images/page_10.png")

    # Get original size
    img = cv2.imread(str(original_image_path))
    if img is None:
        # Fallback if image not found (e.g. strict environment), hardcode
        print("Warning: Could not read original image, using hardcoded 2700x3600")
        target_size = (2700, 3600)
    else:
        h, w = img.shape[:2]
        target_size = (w, h)
        print(f"Original image size: {w}x{h}")

    print(f"Loading barlines from: {barlines_json}")
    with open(barlines_json, "r") as f:
        barline_data = json.load(f)

    print(f"Loading staff mask from: {staff_mask_path}")
    if not staff_mask_path.exists():
        print(f"ERROR: Staff mask path does not exist: {staff_mask_path}")

    bands = extract_staff_bands(staff_mask_path, target_size)
    print(f"Found {len(bands)} staff bands.")

    # Create Staff objects
    staves = []
    for i, (y1, y2, x1, x2) in enumerate(bands):
        # Infer systems:
        # For this test, let's assume 1 Staff = 1 System (common for parts).
        # This will test the numbering continuity across systems.
        staff = Staff(bbox=BBox(x1, y1, x2, y2), system_index=i)
        staves.append(staff)
        print(f"Staff {i}: {staff.bbox} -> System {i}")

    # Create Barline objects
    barlines = []
    for box in barline_data:
        x1, y1, x2, y2 = box
        barlines.append(Barline(bbox=BBox(x1, y1, x2, y2)))
    print(f"Loaded {len(barlines)} barlines.")

    # Build Systems
    builder = SystemBuilder()
    score = Score()
    page = Page(page_number=10, width=0, height=0)  # Dims not strictly needed for this test
    score.pages.append(page)

    # This will group staves into systems (default 1 system per page if no info)
    # And assign barlines to staves
    systems = builder.build_systems(staves, barlines)
    page.systems = systems

    print(f"Built {len(systems)} systems.")
    for i, sys in enumerate(systems):
        print(f"  System {i}: {len(sys.staves)} staves")
        for j, staff in enumerate(sys.staves):
            print(f"    Staff {j}: {len(staff.barlines)} barlines assigned")

    # Number Measures
    numberer = MeasureNumberer()
    numberer.number_score(score)

    print("\n--- Measure Numbering Results ---")
    total_measures = 0
    for sys_idx, system in enumerate(page.systems):
        print(f"System {sys_idx}:")
        # Print measures of the first staff (as representative)
        if system.measures:
            first_staff_measures = system.measures
            print(f"  Measures: {len(first_staff_measures)}")
            for m in first_staff_measures:
                print(f"    Measure {m.number}: {m.bbox}")
            total_measures += len(first_staff_measures)
        else:
            print("  No measures found.")

    print(f"Total measures generated: {total_measures}")


if __name__ == "__main__":
    run_verification()
