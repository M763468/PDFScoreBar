"""Shared types/config for probe detector modules."""

from __future__ import annotations

from dataclasses import dataclass

from src.common import Box as Box

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
    margin_ratio: float = 0.1


@dataclass(frozen=True)
class BandProjectionConfig:
    band_source: str
    band_scan_pad_ratio: float
    band_scan_pad: int
    band_row_pad_ratio: float
    band_row_pad_staff_mult: float
    staff_space: float
    band_height_mode: str
    band_height_min: int
    band_height_scale: float
    extend_scale: float


@dataclass(frozen=True)
class CandidateScanConfig:
    """Existing options for candidate-local ink measurements; no new defaults."""

    band_scan_line_ratio: float
    band_scan_min_lines: int
    band_scan_width: int
    band_source: str
    extend_scale: float
    save_row_profile: bool
    scan_center_on_peak: bool
    scan_fallback_pred_band: bool
    scan_peak_band_height: int
    scan_x_peak_rescue: bool
    scan_x_peak_segment_height: int
    scan_x_peak_segment_source: str
    scan_x_peak_ignore_staff_peak: bool
    scan_x_peak_ignore_radius: int
    scan_x_peak_window: int
    scan_x_peak_ratio_min: float
