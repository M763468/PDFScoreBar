"""Runtime barline geometry shared by detection, numbering and evaluation."""

from __future__ import annotations

from typing import Optional, Tuple

Box = Tuple[int, int, int, int]

BARLINE_DEFAULT_MIN_WIDTH = 12

BARLINE_X_MARGIN = 3

BARLINE_Y_MARGIN = 3

BARLINE_DUPLICATE_IOU_THRESHOLD = 0.3

BARLINE_DUPLICATE_X_TOLERANCE = 12

BARLINE_REPEAT_X_TOLERANCE = 40

BARLINE_VERTICAL_OVERLAP_THRESHOLD = 0.6

BARLINE_REPEAT_OVERLAP_THRESHOLD = 0.8


def _ensure_ordered(box: Box) -> Box:
    x1, y1, x2, y2 = box
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return x1, y1, x2, y2


def expand_barline_box(
    box: Box,
    *,
    min_width: int = BARLINE_DEFAULT_MIN_WIDTH,
    x_margin: int = BARLINE_X_MARGIN,
    y_margin: int = BARLINE_Y_MARGIN,
    bounds: Optional[Tuple[int, int]] = None,
) -> Box:
    """Pad a barline bounding box so IoU is less sensitive to tiny width offsets.

    The padding keeps the box centred while guaranteeing a minimal width and optional
    margins along X/Y. Bounds can be provided as (width, height) to clamp the result.
    """

    if min_width < 1:
        raise ValueError("min_width must be >= 1")
    x1, y1, x2, y2 = _ensure_ordered(box)
    width = max(1, x2 - x1)
    centre_x = (x1 + x2) / 2.0
    half_width = max(width / 2.0, min_width / 2.0)

    padded_x1 = int(round(centre_x - half_width)) - x_margin
    padded_x2 = int(round(centre_x + half_width)) + x_margin
    padded_y1 = y1 - y_margin
    padded_y2 = y2 + y_margin

    padded_x1 = max(0, padded_x1)
    padded_y1 = max(0, padded_y1)

    if bounds is not None:
        max_x, max_y = bounds
        if max_x <= 0 or max_y <= 0:
            raise ValueError("bounds must be positive")
        padded_x1 = min(padded_x1, max_x - 1)
        padded_x2 = min(padded_x2, max_x - 1)
        padded_y1 = min(padded_y1, max_y - 1)
        padded_y2 = min(padded_y2, max_y - 1)

    if padded_x2 <= padded_x1:
        padded_x2 = padded_x1 + 1
    if padded_y2 <= padded_y1:
        padded_y2 = padded_y1 + 1

    return padded_x1, padded_y1, padded_x2, padded_y2


def barline_iou(
    box_a: Box,
    box_b: Box,
    *,
    min_width: int = BARLINE_DEFAULT_MIN_WIDTH,
    x_margin: int = BARLINE_X_MARGIN,
    y_margin: int = BARLINE_Y_MARGIN,
    bounds: Optional[Tuple[int, int]] = None,
) -> float:
    """Compute IoU for slender barline boxes with symmetric padding applied."""

    ax1, ay1, ax2, ay2 = expand_barline_box(
        box_a,
        min_width=min_width,
        x_margin=x_margin,
        y_margin=y_margin,
        bounds=bounds,
    )
    bx1, by1, bx2, by2 = expand_barline_box(
        box_b,
        min_width=min_width,
        x_margin=x_margin,
        y_margin=y_margin,
        bounds=bounds,
    )

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(inter_x2 - inter_x1, 0)
    inter_h = max(inter_y2 - inter_y1, 0)
    inter_area = inter_w * inter_h

    area_a = max(ax2 - ax1, 0) * max(ay2 - ay1, 0)
    area_b = max(bx2 - bx1, 0) * max(by2 - by1, 0)

    union_area = area_a + area_b - inter_area
    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def barline_vertical_overlap(box_a: Box, box_b: Box) -> float:
    """Return vertical overlap ratio between two boxes (range 0..1)."""

    top = max(box_a[1], box_b[1])
    bottom = min(box_a[3], box_b[3])
    if bottom <= top:
        return 0.0

    overlap = bottom - top
    height_a = max(box_a[3] - box_a[1], 1)
    height_b = max(box_b[3] - box_b[1], 1)
    return overlap / max(height_a, height_b)
