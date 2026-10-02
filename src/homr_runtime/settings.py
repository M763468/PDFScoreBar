"""Existing HOMR runtime defaults; changing these is a separate tuning experiment."""

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
