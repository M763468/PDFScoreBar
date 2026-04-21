"""Heuristic filters to remove false positive candidates."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]


def _median(vals: list[int]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _build_page_mask(gray: np.ndarray, *, paper_threshold: int) -> np.ndarray:
    """Return binary mask of the paper area (largest bright connected component)."""
    _, bright = cv2.threshold(gray, paper_threshold, 255, cv2.THRESH_BINARY)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bright, 8)
    if n_labels <= 1:
        return bright

    best_label = 1
    best_area = int(stats[1, cv2.CC_STAT_AREA])
    for i in range(2, n_labels):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area > best_area:
            best_area = area
            best_label = i
    page_mask = (labels == best_label).astype("uint8") * 255
    return page_mask


def _page_bbox_from_mask(mask: np.ndarray) -> Tuple[int, int, int, int]:
    ys, xs = (mask > 0).nonzero()
    if len(xs) == 0 or len(ys) == 0:
        h, w = mask.shape[:2]
        return (0, 0, w - 1, h - 1)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


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


def trim_box_to_ink(
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
    if len(crop.shape) == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop

    # Vertical projection: count ink pixels in each row
    row_ink = (gray < ink_threshold).sum(axis=1)
    row_ratio = row_ink / float(max(1, x_hi - x_lo))

    active_rows = np.where(row_ratio >= min_ink_ratio)[0]
    if len(active_rows) == 0:
        return box

    new_y1 = y_lo + int(active_rows[0])
    new_y2 = y_lo + int(active_rows[-1]) + 1
    return (x1, new_y1, x2, new_y2)


def split_box_vertically(
    image: np.ndarray,
    box: Tuple[int, int, int, int],
    ink_threshold: int = 180,
    min_gap: int = 50,
    min_segment_h: int = 30,
) -> List[Tuple[int, int, int, int]]:
    """Split a box vertically into segments where ink is present, separated by gaps."""
    h_img, w_img = image.shape[:2]
    x1, y1, x2, y2 = box
    y_lo, y_hi = max(0, min(y1, y2)), min(h_img, max(y1, y2))
    x_lo, x_hi = max(0, min(x1, x2)), min(w_img, max(x1, x2))
    if y_hi <= y_lo or x_hi <= x_lo:
        return [box]
    crop = image[y_lo:y_hi, x_lo:x_hi]
    if len(crop.shape) == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop
    row_ink = (gray < ink_threshold).sum(axis=1)
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
    return [(x1, s_y1, x2, s_y2) for s_y1, s_y2 in merged]


def filter_probe_candidates(
    candidates: List[Tuple[int, int, int, int]],
    image: np.ndarray,
    existing_boxes: List[Tuple[int, int, int, int]],
    staff_mask: np.ndarray | None = None,
    clef_mask: np.ndarray | None = None,
    *,
    left_margin_ratio: float = 0.12,
    clef_left_ratio: float = 0.25,
    min_height_median_ratio: float = 0.6,
    ink_threshold: int = 180,
    min_ink_ratio: float = 0.18,
    paper_threshold: int = 200,
    min_paper_overlap_ratio: float = 0.6,
    min_staff_overlap_ratio: float = 0.01,
    max_width_ratio: float | None = None,
) -> Tuple[List[Tuple[int, int, int, int]], List[Dict[str, Any]]]:
    """
    Apply heuristic filters to remove false positive candidates.
    Returns:
        A tuple of (filtered_candidates, dropped_info)
    """
    if not candidates:
        return [], []

    if cv2 is None or np is None:
        raise ImportError("filter_probe_candidates requires opencv-python and numpy.")

    h_img, w_img = image.shape[:2]
    left_margin_px = int(w_img * left_margin_ratio)
    clef_left_px = int(w_img * clef_left_ratio)
    max_w_px = int(w_img * max_width_ratio) if max_width_ratio is not None else w_img

    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    page_mask = _build_page_mask(gray, paper_threshold=paper_threshold)
    page_bbox = _page_bbox_from_mask(page_mask)

    if staff_mask is not None and staff_mask.shape[:2] != image.shape[:2]:
        staff_mask = cv2.resize(staff_mask, (w_img, h_img), interpolation=cv2.INTER_NEAREST)

    if clef_mask is not None and clef_mask.shape[:2] != image.shape[:2]:
        clef_mask = cv2.resize(clef_mask, (w_img, h_img), interpolation=cv2.INTER_NEAREST)

    existing_heights = [abs(b[3] - b[1]) for b in existing_boxes]
    median_h = _median(existing_heights)
    min_h_px = int(median_h * min_height_median_ratio) if median_h > 0 else 0

    keep: List[Tuple[int, int, int, int]] = []
    dropped: List[Dict[str, Any]] = []

    for b in candidates:
        x1, y1, x2, y2 = b
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        reasons: List[str] = []

        if w > max_w_px:
            reasons.append("too_wide")

        if max(x1, x2) <= left_margin_px:
            reasons.append("left_margin_zone")
        if clef_mask is not None and max(x1, x2) <= clef_left_px:
            clef_overlap = _box_mask_overlap_ratio(clef_mask, (x1, y1, x2, y2))
            if clef_overlap > 0.01:
                reasons.append("clef_mask_overlap")

        if min_h_px > 0 and h < min_h_px:
            reasons.append("too_short_vs_existing_median")

        center_in_page = _center_in_bbox((x1, y1, x2, y2), page_bbox)
        if not center_in_page:
            reasons.append("outside_page_region")

        page_overlap = _box_mask_overlap_ratio(page_mask, (x1, y1, x2, y2))
        if page_overlap < min_paper_overlap_ratio:
            reasons.append("low_paper_overlap")

        if staff_mask is not None:
            staff_overlap = _box_mask_overlap_ratio(staff_mask, (x1, y1, x2, y2))
            if staff_overlap < min_staff_overlap_ratio:
                reasons.append("no_staff_overlap")

        y_lo, y_hi = max(0, min(y1, y2)), min(h_img, max(y1, y2))
        x_lo, x_hi = max(0, min(x1, x2)), min(w_img, max(x1, x2))
        if y_hi > y_lo and x_hi > x_lo:
            crop = gray[y_lo:y_hi, x_lo:x_hi]
            ink_ratio = float((crop < ink_threshold).sum()) / float(max(1, crop.size))
            if ink_ratio < min_ink_ratio:
                reasons.append("low_ink_ratio")

        if reasons:
            dropped.append({"bbox": b, "reasons": reasons})
            if len(reasons) > 0:
                # Log drops that are NOT the obvious left margin ones, to keep noise down
                if "left_margin_zone" not in reasons:
                    logger.debug(f"--- [DEBUG_DROP] Candidate {b} dropped. Reasons: {reasons}")
        else:
            keep.append(b)

    return keep, dropped
