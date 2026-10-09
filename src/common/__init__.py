"""Shared runtime geometry; evaluation exports load only on development use."""

from .barline_geometry import (
    BARLINE_DEFAULT_MIN_WIDTH,
    BARLINE_DUPLICATE_IOU_THRESHOLD,
    BARLINE_DUPLICATE_X_TOLERANCE,
    BARLINE_REPEAT_X_TOLERANCE,
    BARLINE_VERTICAL_OVERLAP_THRESHOLD,
    BARLINE_X_MARGIN,
    BARLINE_Y_MARGIN,
    Box,
    barline_iou,
    expand_barline_box,
)

__all__ = [
    "BARLINE_DEFAULT_MIN_WIDTH",
    "BARLINE_DUPLICATE_IOU_THRESHOLD",
    "BARLINE_DUPLICATE_X_TOLERANCE",
    "BARLINE_REPEAT_X_TOLERANCE",
    "BARLINE_VERTICAL_OVERLAP_THRESHOLD",
    "BARLINE_X_MARGIN",
    "BARLINE_Y_MARGIN",
    "CENTER_ANCHOR_XDIST_UNIT_RATIO",
    "BarlineMatch",
    "BarlineSoftMatch",
    "BarlineMatchResult",
    "Box",
    "apply_left_margin_exclusion",
    "expand_barline_box",
    "barline_iou",
    "center_anchor_xdist_limit",
    "greedy_barline_match",
]


def __getattr__(name):
    if name in {
        "BarlineMatchResult",
        "CENTER_ANCHOR_XDIST_UNIT_RATIO",
        "apply_left_margin_exclusion",
        "greedy_barline_match",
        "BarlineMatch",
        "center_anchor_xdist_limit",
        "BarlineSoftMatch",
    }:
        from . import barline_evaluation

        return getattr(barline_evaluation, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
