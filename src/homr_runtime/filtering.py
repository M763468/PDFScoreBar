"""Filter predicted barlines using notehead proximity and staff crossings."""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from .types import BarlinePrediction


def filter_detections_by_notehead_proximity(
    detections: List[BarlinePrediction],
    notehead_mask: np.ndarray,
    proximity_threshold_px: int,
    min_overlap_px: int,
    max_height_px: int,
    max_width_px: int,
    staff_mask: Optional[np.ndarray] = None,
    min_staff_crossings: int = 0,
    check_staff_crossing: bool = False,
) -> Tuple[List[BarlinePrediction], List[BarlinePrediction]]:
    """
    Filters barline detections that are horizontally close to noteheads, which
    are likely to be stems.

    This heuristic is designed to be conservative to avoid creating False Negatives.
    It only rejects a candidate if it matches ALL of the following:
      1. Within `proximity_threshold_px` of a notehead.
      2. Pixel overlap with notehead mask >= `min_overlap_px`.
      3. Height < `max_height_px` (short stems).
      4. Width < `max_width_px` (thin stems).

    Args:
        detections: List of detected barline boxes in original image coordinates.
        notehead_mask: Binary (0/255) or (0/1) mask of notehead locations in original image coordinates.
        proximity_threshold_px: The horizontal distance in pixels to check for noteheads.
        min_overlap_px: Minimum intersection area to consider a rejection.
        max_height_px: Maximum height to consider a rejection.
        max_width_px: Maximum width to consider a rejection.

        check_staff_crossing: If True, `staff_mask` and `min_staff_crossings` are used to reject low-crossing candidates.
        staff_mask: Binary (0/255) mask of staff lines. Required if `check_staff_crossing` is True.
        min_staff_crossings: Minimum crossings required to KEEP a candidate IF overlap is low.

    Returns:
        A tuple containing (kept_detections, rejected_detections).
    """
    kept_detections = []
    rejected_detections = []
    mask_h, mask_w = notehead_mask.shape

    for pred in detections:
        x1, y1, x2, y2 = pred.orig_bbox
        width = x2 - x1
        height = y2 - y1

        # Check dimensions first (fastest)
        # Note: These criteria are for REJECTION.
        # Original Heuristic 1 ("Safe Filter"):
        # REJECT if (Dist < 5) AND (Height < 24) AND (Width < 4) AND (Overlap >= 5)

        # Dimensions check allows us to skip Heuristic 1 if dimensions don't match FP profile
        is_small_candidate = (height < max_height_px) and (width < max_width_px)

        # Define a horizontal search window around the detection
        search_x1 = max(0, x1 - proximity_threshold_px)
        search_x2 = min(mask_w, x2 + proximity_threshold_px)

        # Clamp vertical coordinates to mask boundaries
        y1_clamped = max(0, min(mask_h, y1))
        y2_clamped = max(0, min(mask_h, y2))

        if y1_clamped >= y2_clamped or search_x1 >= search_x2:
            kept_detections.append(pred)
            continue

        # Extract regions
        box_x1 = max(0, min(mask_w, x1))
        box_x2 = max(0, min(mask_w, x2))

        # Proximity check window
        search_window = notehead_mask[y1_clamped:y2_clamped, search_x1:search_x2]
        is_proximal = np.any(search_window)

        if not is_proximal:
            kept_detections.append(pred)
            continue

        # Overlap check
        if box_x1 >= box_x2:
            overlap_area = 0
        else:
            box_window = notehead_mask[y1_clamped:y2_clamped, box_x1:box_x2]
            overlap_area = np.count_nonzero(box_window)

        # --- Heuristic 1: Safe Filter (Small + High Overlap) ---
        if is_small_candidate and overlap_area >= min_overlap_px:
            rejected_detections.append(pred)
            continue

        # --- Heuristic 2: Staff-Crossing Validation (Low Overlap + Low Crossing) ---
        # Only check if it wasn't already rejected by Heuristic 1, and heuristic 2 IS enabled.
        # Note: We are currently inside a block where is_proximal is True.
        # Heuristic 2 targets candidates that have LOW overlap (< min_overlap_px) but ARE proximal.

        if check_staff_crossing and staff_mask is not None and overlap_area < min_overlap_px:
            num_crossings = count_staff_crossings(pred.orig_bbox, staff_mask)
            if num_crossings < min_staff_crossings:
                rejected_detections.append(pred)
                continue

        kept_detections.append(pred)

    return kept_detections, rejected_detections


def count_staff_crossings(
    bbox: Tuple[int, int, int, int],
    staff_mask: np.ndarray,
) -> int:
    """
    Counts the number of staff line crossings for a vertical barline candidate.

    A "crossing" is defined as a transition from background -> staff -> background
    along the vertical slice at the candidate's x-coordinate.

    Args:
        bbox: Bounding box (x1, y1, x2, y2) in original image coordinates.
        staff_mask: Binary (0/255) staff mask in original image coordinates.

    Returns:
        Number of distinct staff line crossings.
    """
    x1, y1, x2, y2 = bbox
    mask_h, mask_w = staff_mask.shape

    # Use center x-coordinate
    cx = (x1 + x2) // 2
    if cx < 0 or cx >= mask_w:
        return 0

    # Clamp y range
    y1_clamped = max(0, min(mask_h, y1))
    y2_clamped = max(0, min(mask_h, y2))

    if y1_clamped >= y2_clamped:
        return 0

    # Extract vertical slice
    vertical_slice = staff_mask[y1_clamped:y2_clamped, cx]

    # Binarize (in case it's 0/1 instead of 0/255)
    binary_slice = (vertical_slice > 0).astype(np.uint8)

    # Count transitions: 0->1 (entering staff line)
    # A crossing is a contiguous run of 1s
    crossings = 0
    in_staff = False

    for val in binary_slice:
        if val == 1 and not in_staff:
            crossings += 1
            in_staff = True
        elif val == 0:
            in_staff = False

    return crossings

    return crossings
