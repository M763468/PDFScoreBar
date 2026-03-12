"""Shared utilities for evaluation and processing across detectors."""

from .barline_evaluation import (
    BARLINE_DEFAULT_MIN_WIDTH,
    BARLINE_DUPLICATE_IOU_THRESHOLD,
    BARLINE_DUPLICATE_X_TOLERANCE,
    BARLINE_REPEAT_X_TOLERANCE,
    BARLINE_VERTICAL_OVERLAP_THRESHOLD,
    BARLINE_X_MARGIN,
    BARLINE_Y_MARGIN,
    BarlineMatch,
    BarlineMatchResult,
    BarlineSoftMatch,
    Box,
    apply_left_margin_exclusion,
    barline_iou,
    expand_barline_box,
    greedy_barline_match,
)

__all__ = [
    "BARLINE_DEFAULT_MIN_WIDTH",
    "BARLINE_DUPLICATE_IOU_THRESHOLD",
    "BARLINE_DUPLICATE_X_TOLERANCE",
    "BARLINE_REPEAT_X_TOLERANCE",
    "BARLINE_VERTICAL_OVERLAP_THRESHOLD",
    "BARLINE_X_MARGIN",
    "BARLINE_Y_MARGIN",
    "BarlineMatch",
    "BarlineSoftMatch",
    "BarlineMatchResult",
    "Box",
    "apply_left_margin_exclusion",
    "expand_barline_box",
    "barline_iou",
    "greedy_barline_match",
]
