"""Heuristic filters for barline candidates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2  # type: ignore
import numpy as np

logger = logging.getLogger(__name__)


def _box_mask_overlap_ratio(mask: np.ndarray, box: Tuple[int, int, int, int]) -> float:
    h_img, w_img = mask.shape[:2]
    x1, y1, x2, y2 = box
    y_lo, y_hi = max(0, min(y1, y2)), min(h_img, max(y1, y2))
    x_lo, x_hi = max(0, min(x1, x2)), min(w_img, max(x1, x2))
    if y_hi <= y_lo or x_hi <= x_lo:
        return 0.0
    crop = mask[y_lo:y_hi, x_lo:x_hi]
    return float((crop > 0).sum()) / float(max(1, crop.size))


def _center_in_bbox(box: Tuple[int, int, int, int], bbox: Tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = box
    cx = int(round((x1 + x2) / 2.0))
    cy = int(round((y1 + y2) / 2.0))
    bx1, by1, bx2, by2 = bbox
    return bx1 <= cx <= bx2 and by1 <= cy <= by2


def trim_box_ink(
    image: np.ndarray,
    box: Tuple[int, int, int, int],
    ink_threshold: int = 180,
    min_ink_ratio: float = 0.1,
) -> Tuple[int, int, int, int]:
    """Trim box vertically based on ink density."""
    h_img, w_img = image.shape[:2]
    x1, y1, x2, y2 = box
    y_lo, y_hi = max(0, min(y1, y2)), min(h_img, max(y1, y2))
    x_lo, x_hi = max(0, min(x1, x2)), min(w_img, max(x1, x2))
    if y_hi <= y_lo or x_hi <= x_lo:
        return box

    crop = image[y_lo:y_hi, x_lo:x_hi]
    # Vertical projection: count ink pixels in each row
    row_ink = (crop < ink_threshold).sum(axis=1)
    row_ratio = row_ink / float(max(1, x_hi - x_lo))

    active_rows = np.where(row_ratio >= min_ink_ratio)[0]
    if len(active_rows) == 0:
        return box

    new_y1 = y_lo + int(active_rows[0])
    new_y2 = y_lo + int(active_rows[-1]) + 1
    return (int(x1), int(new_y1), int(x2), int(new_y2))


def split_box_vertically(
    image: np.ndarray,
    box: Tuple[int, int, int, int],
    ink_threshold: int = 180,
    unit_size: float = 40.0,
) -> List[Tuple[int, int, int, int]]:
    """Split a box vertically if it contains a large vertical gap (staff line gap)."""
    h_img, w_img = image.shape[:2]
    x1, y1, x2, y2 = box
    y_lo, y_hi = max(0, min(y1, y2)), min(h_img, max(y1, y2))
    x_lo, x_hi = max(0, min(x1, x2)), min(w_img, max(x1, x2))
    if y_hi <= y_lo or x_hi <= x_lo:
        return [box]

    crop = image[y_lo:y_hi, x_lo:x_hi]
    if len(crop.shape) == 3:
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Large gaps should split the box
    # We use unit-based ratios to match the golden 50px/30px at 1x (unit~25)
    min_gap = max(2, int(round(2.0 * unit_size)))
    min_segment_h = max(2, int(round(1.2 * unit_size)))

    row_ink = (crop < ink_threshold).sum(axis=1)
    active = (row_ink > 0).astype(np.uint8)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(active.reshape(-1, 1), 4)
    
    segments = []
    for i in range(1, n_labels):
        y_start = int(stats[i, cv2.CC_STAT_TOP])
        h_seg = int(stats[i, cv2.CC_STAT_HEIGHT])
        if h_seg >= min_segment_h:
            segments.append((y_lo + y_start, y_lo + y_start + h_seg))
            
    if not segments:
        return [box]
        
    merged = []
    curr_y1, curr_y2 = segments[0]
    for i in range(1, len(segments)):
        next_y1, next_y2 = segments[i]
        if next_y1 - curr_y2 < min_gap:
            curr_y2 = next_y2
        else:
            merged.append((curr_y1, curr_y2))
            curr_y1, curr_y2 = next_y1, next_y2
    merged.append((curr_y1, curr_y2))
    
    return [(int(x1), int(s_y1), int(x2), int(s_y2)) for s_y1, s_y2 in merged]


def filter_probe_candidates(
    image: np.ndarray,
    candidates: Sequence[Tuple[float, float, float, float]],
    existing_boxes: Sequence[Tuple[float, float, float, float]] = [],
    staff_mask: Optional[np.ndarray] = None,
    clef_mask: Optional[np.ndarray] = None,
    # Golden baseline defaults from v12/v14 benchmarks
    ink_threshold: int = 180,
    min_ink_ratio: float = 0.18,
    paper_threshold: int = 200,
    min_paper_overlap_ratio: float = 0.6,
    min_staff_overlap_ratio: float = 0.01,
    left_margin_ratio: float = 0.12,
    clef_left_ratio: float = 0.25,
    min_height_median_ratio: float = 0.60,
    max_width_ratio: float = 0.05,
    unit_size: float = 40.0,
) -> Tuple[List[Tuple[int, int, int, int]], List[str]]:
    """Heuristic filtering for probe scan candidates."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    h_img, w_img = gray.shape[:2]
    
    # Calculate global target height
    all_prev = list(existing_boxes) + list(candidates)
    heights = [abs(b[3] - b[1]) for b in all_prev if abs(b[3] - b[1]) > 0]
    target_h = float(np.median(heights)) if heights else unit_size * 5.0
    
    kept = []
    all_reasons = []
    
    for box in candidates:
        reasons = []
        x1, y1, x2, y2 = box
        
        # 1. Height filter
        h = abs(y2 - y1)
        if h < target_h * min_height_median_ratio:
            reasons.append(f"too_short ({h:.1f} < {target_h*min_height_median_ratio:.1f})")
            
        # 2. Width filter
        w = abs(x2 - x1)
        if w > w_img * max_width_ratio:
            reasons.append(f"too_wide ({w:.1f} > {w_img * max_width_ratio:.1f})")
            
        # 3. Left margin filter
        if (x1 + x2) / 2.0 < w_img * left_margin_ratio:
            # Check if it overlaps with an existing box (trusted)
            if not any(_center_in_bbox((x1, y1, x2, y2), eb) for eb in existing_boxes):
                reasons.append("left_margin")
                
        # 4. Clef overlap filter
        if clef_mask is not None:
            clef_overlap = _box_mask_overlap_ratio(clef_mask, (int(x1), int(y1), int(x2), int(y2)))
            if clef_overlap > float(clef_left_ratio):
                reasons.append("clef_overlap")
                
        # 5. Staff overlap filter
        if staff_mask is not None:
            staff_overlap = _box_mask_overlap_ratio(staff_mask, (int(x1), int(y1), int(x2), int(y2)))
            if staff_overlap < min_staff_overlap_ratio:
                reasons.append("no_staff_overlap")
                
        # 6. Ink Density filter
        y_lo, y_hi = int(max(0, min(y1, y2))), int(min(h_img, max(y1, y2)))
        x_lo, x_hi = int(max(0, min(x1, x2))), int(min(w_img, max(x1, x2)))
        if y_hi > y_lo and x_hi > x_lo:
            crop = gray[y_lo:y_hi, x_lo:x_hi]
            ink_ratio = float((crop < ink_threshold).mean())
            if ink_ratio < min_ink_ratio:
                reasons.append(f"low_ink ({ink_ratio:.3f} < {min_ink_ratio})")
                
        if not reasons:
            kept.append((int(x1), int(y1), int(x2), int(y2)))
            all_reasons.append("kept")
        else:
            all_reasons.append("|".join(reasons))
            
    return kept, all_reasons
