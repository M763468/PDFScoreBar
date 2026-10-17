"""HOMR runtime data records and established tuning defaults."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

Box = Tuple[int, int, int, int]


@dataclass
class TransformInfo:
    original_shape: Tuple[int, int]  # width, height
    crop_box: Tuple[int, int, int, int]  # x, y, w, h
    resize_shape: Tuple[int, int]
    seg_shape: Tuple[int, int]
    resize_scale: Tuple[float, float]
    seg_scale: Tuple[float, float]

    @property
    def total_scale(self) -> Tuple[float, float]:
        return (
            self.resize_scale[0] * self.seg_scale[0],
            self.resize_scale[1] * self.seg_scale[1],
        )


@dataclass
class BarlinePrediction:
    pred_bbox: Tuple[int, int, int, int]
    orig_bbox: Tuple[int, int, int, int]
    system_index: int
    staff_index: int


STEM_CONTEXT_HEURISTICS = {
    "enabled": True,
    "notehead_proximity_threshold_px": 5,
    "min_overlap_px": 5,
    "max_height_px": 24,
    "max_width_px": 4,
    "staff_crossing_enabled": False,
    "min_staff_crossings": 3,
    "cluster_resolution_dry_run": False,
    "cluster_gap_threshold_px": 15,
    "tight_duplicate_dry_run": False,
    "measure_grid_export": True,
}


DEFAULT_TUNING = {
    "barline_min_height_factor": 1.0,
    "barline_max_width_factor": 1.0,
    "enable_end_barline_recovery": False,
    "end_barline_max_x_dist_px": 10,
    "end_barline_min_height_px": 30,
}
