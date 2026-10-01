"""Alias runtime patch points while retaining historical diagnostic exports."""

import sys

from src.homr_runtime import heuristics as _runtime
from src.homr_runtime.end_barlines import _cluster_by_y_centers, _scan_vertical_line
from src.homr_runtime.types import BarlinePrediction, Box, TransformInfo

from . import diagnostics as _diagnostics

# Only legacy imports attach evaluation helpers. Maintained workers never import
# this adapter, so their package has no dependency on evaluation diagnostics.
for _name in (
    "resolve_clusters_dry_run",
    "resolve_tight_duplicates_dry_run",
    "export_measure_grid_candidates",
    "compute_candidate_stats",
    "compute_and_save_gap_stats",
):
    setattr(_runtime, _name, getattr(_diagnostics, _name))
_runtime._cluster_by_y_centers = _cluster_by_y_centers
_runtime._scan_vertical_line = _scan_vertical_line
_runtime.BarlinePrediction = BarlinePrediction
_runtime.Box = Box
_runtime.TransformInfo = TransformInfo
sys.modules[__name__] = _runtime
