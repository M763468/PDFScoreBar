"""Configuration constants and helpers for detection."""

from typing import Any, Dict

DEFAULT_CNN_APPLY_NMS = False

PROBE_SCAN_KWARG_KEYS = (
    "probe_width",
    "use_peak_relative_ratio",
    "peak_ratio_min",
    "extend_scale",
    "extend_max_ratio",
    "extend_top_max_ratio",
    "extend_bottom_max_ratio",
    "min_peak_distance",
    "min_peak_distance_unit_ratio",
    "refine_window",
    "max_per_band",
    "band_height_mode",
    "band_height_scale",
    "band_source",
    "band_height_min",
    "band_row_pad_ratio",
    "band_row_pad_staff_mult",
    "x_merge_tol",
    "x_merge_tol_unit_ratio",
    "post_emit_unit_normalized_box",
    "post_norm_width_unit_ratio",
    "post_norm_height_unit_ratio",
    "post_apply_if_width_gt_unit_ratio",
    "post_apply_if_height_gt_unit_ratio",
    "post_vertical_min_height_unit_ratio",
    "post_vertical_min_aspect_ratio",
    "post_split_wide_candidates",
    "post_split_min_width_unit_ratio",
    "post_split_box_width_unit_ratio",
    "post_split_peak_distance_unit_ratio",
    "post_split_peak_prominence_ratio",
    "scan_fallback_pred_band",
    "scan_disable_non_scan_extend",
    "scan_disable_existing_suppression",
    "scan_existing_min_vertical_iou",
    "scan_peak_band_height",
    "scan_center_on_peak",
    "scan_x_peak_rescue",
    "scan_x_peak_window",
    "scan_x_peak_ratio_min",
    "scan_x_peak_max_overhang",
    "scan_x_peak_rescue_mode",
    "scan_x_peak_segment_height",
    "scan_x_peak_segment_pass_ratio",
    "scan_x_peak_segment_source",
    "scan_x_peak_ignore_staff_peak",
    "scan_x_peak_ignore_radius",
    "scan_rightmost_rescue",
    "scan_rightmost_tolerance",
    "scan_rightmost_min_rows",
    "scan_rightmost_min_ratio",
    "scan_gap_rescue",
    "scan_gap_threshold_ratio",
    "scan_gap_rescue_min_ratio",
    "scan_gap_margin_ratio",
    "scan_ratio_rel_rescue",
    "scan_ratio_rel_rescue_min",
    "scan_ratio_rel_rescue_xpeak_min",
    "scan_ratio_rel_rescue_max_overhang",
    "divisi_rescue",
    "divisi_dist_ratio",
    "divisi_align_tol",
    "divisi_align_min_count",
)


def get_probe_kwargs(det_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts probe-specific keyword arguments from configuration."""
    return {
        key: det_cfg[key]
        for key in PROBE_SCAN_KWARG_KEYS
        if key in det_cfg and det_cfg.get(key) is not None
    }


def get_cnn_apply_nms(det_cfg: Dict[str, Any]) -> bool:
    """Return explicit CNN NMS setting, defaulting to opt-out."""
    return bool(det_cfg.get("cnn_apply_nms", DEFAULT_CNN_APPLY_NMS))
