# [EXPERIMENTAL] Visualization script for measure numbering overlays.
# Used for qualitative review of the numbering logic on 2026-01-04.
# This logic is now integrated into tools/add_measure_numbers.py.

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
    kernel = np.ones((20, 1), np.uint8)
    dilated = cv2.dilate(bin_mask, kernel, iterations=1)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)

    bands = []
    for i in range(1, num_labels):  # Skip background
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]

        # Filter: Must be wide enough to be a staff
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


def run_visualization():
    # Paths
    barlines_json = Path(
        "logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10/final_predictions.json"
    )
    staff_mask_path = Path(
        "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_3_staff.png"
    )
    original_image_path = Path("data/training/images/page_10.png")
    output_path = Path(
        "logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10/measure_numbering_overlay_final.png"
    )

    # Load Image
    img = cv2.imread(str(original_image_path))
    if img is None:
        print(f"Error: Could not read image {original_image_path}")
        return
    h, w = img.shape[:2]
    print(f"Original image size: {w}x{h}")

    # Load Data
    with open(barlines_json, "r") as f:
        barline_data = json.load(f)
    print(f"Loaded {len(barline_data)} barlines.")

    bands = extract_staff_bands(staff_mask_path, (w, h))

    # Create Objects
    staves = []
    for i, (y1, y2, x1, x2) in enumerate(bands):
        # Assumption: 1 Staff = 1 System
        staff = Staff(bbox=BBox(x1, y1, x2, y2), system_index=i)
        staves.append(staff)

    barlines = []
    for box in barline_data:
        bx1, by1, bx2, by2 = box
        barlines.append(Barline(bbox=BBox(bx1, by1, bx2, by2)))

    # Build & Number
    builder = SystemBuilder()
    score = Score()
    page = Page(page_number=10, width=w, height=h)
    score.pages.append(page)

    # Use the builder to build systems and assign barlines correctly
    systems = builder.build_systems(staves, barlines)
    page.systems = systems

    numberer = MeasureNumberer()
    # Increase deduplication threshold for this noisy data if needed,
    # but let's try the default 15 first.
    numberer.number_score(score)

    # --- Visualization ---
    overlay = img.copy()

    # 1. Draw Staves (Blue boxes) - Transparent
    overlay_temp = overlay.copy()
    for staff in staves:
        cv2.rectangle(
            overlay_temp,
            (staff.bbox.x1, staff.bbox.y1),
            (staff.bbox.x2, staff.bbox.y2),
            (255, 0, 0),
            -1,
        )  # Blue fill
    cv2.addWeighted(overlay_temp, 0.15, overlay, 0.85, 0, overlay)

    # 2. Draw Barlines
    # Collect all barlines that ended up in systems (including ghosts)
    all_processed_barlines = set()
    for sys_obj in page.systems:
        for staff in sys_obj.staves:
            all_processed_barlines.update(staff.barlines)
        # Also include ghosts from measures
        for m in sys.measures:
            if m.start_bar:
                all_processed_barlines.add(m.start_bar)
            if m.end_bar:
                all_processed_barlines.add(m.end_bar)

    for bar in all_processed_barlines:
        color = (0, 0, 255)  # Red
        thickness = 2
        if getattr(bar, "is_ghost", False):
            color = (255, 0, 255)  # Magenta for ghost
            thickness = 1

        cv2.rectangle(
            overlay, (bar.bbox.x1, bar.bbox.y1), (bar.bbox.x2, bar.bbox.y2), color, thickness
        )

    # 3. Draw Measure Numbers (Green Text) - CENTERED in measure
    for system in page.systems:
        if not system.measures:
            continue

        # Determine Y pos for text (above the top staff of the system)
        top_staff = min(system.staves, key=lambda s: s.bbox.y1)
        text_y_base = top_staff.bbox.y1 - 10

        for measure in system.measures:
            # CENTER X in measure bbox
            center_x = int((measure.bbox.x1 + measure.bbox.x2) / 2)

            text = str(measure.number)
            font_scale = 1.2
            thickness = 2

            # Get text size to center it exactly
            (text_w, text_h), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
            )

            draw_x = center_x - text_w // 2
            draw_y = text_y_base

            # Draw number
            cv2.putText(
                overlay,
                text,
                (draw_x, draw_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (0, 150, 0),
                thickness,
                cv2.LINE_AA,
            )

            # Draw faint measure boundary for debug
            cv2.line(
                overlay,
                (measure.bbox.x1, text_y_base),
                (measure.bbox.x1, text_y_base + 5),
                (0, 255, 0),
                1,
            )
            cv2.line(
                overlay,
                (measure.bbox.x2, text_y_base),
                (measure.bbox.x2, text_y_base + 5),
                (0, 255, 0),
                1,
            )

    # Save
    print(f"Saving overlay to: {output_path}")
    cv2.imwrite(str(output_path), overlay)


if __name__ == "__main__":
    run_visualization()
