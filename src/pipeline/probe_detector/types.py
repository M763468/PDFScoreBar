"""Shared types/config for probe detector modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

Box = Tuple[int, int, int, int]

_RIGHTMOST_RESCUE_DEBUG_KEYS = [
    "band",
    "staff_band",
    "pred_band",
    "ext_band",
    "top_h",
    "bottom_h",
    "scan_band",
    "scan_ext_band",
    "scan_base_band",
    "scan_row_ratio_mean",
    "scan_row_ratio_max",
    "scan_row_ratio_lines",
    "scan_top_h",
    "scan_bottom_h",
    "scan_row_profile",
    "scan_peak_ratio",
    "scan_peak_row",
    "scan_peak_ratio_local",
    "scan_x_peak_ratio",
    "scan_x_peak_neighbor_median",
    "scan_x_peak_segment_min",
    "scan_x_peak_segment_pass",
    "scan_x_peak_ignored_rows",
]


@dataclass(frozen=True)
class BandSelectionConfig:
    band_source: str
    band_cluster_max_dist: float
    band_min_row_count: int


@dataclass(frozen=True)
class DivisiRescueConfig:
    enabled: bool
    dist_ratio: float
    align_tol: int
    align_min_count: int
    min_ratio: float
    band_source: str
    band_height_mode: str


@dataclass(frozen=True)
class RightmostRescueConfig:
    enabled: bool
    tolerance: int
    min_rows: int
    min_ratio: float


@dataclass(frozen=True)
class GapRescueConfig:
    enabled: bool
    threshold_ratio: float
    min_ratio: float
