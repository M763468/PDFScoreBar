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
    "scan_x_domain_mode",
    "scan_x_domain_pad",
    "scan_x_domain_pad_unit_ratio",
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

PROBE_X_DOMAIN_KWARG_KEYS = (
    "scan_x_domain_mode",
    "scan_x_domain_pad",
    "scan_x_domain_pad_unit_ratio",
)


def get_probe_kwargs(det_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts probe-specific keyword arguments from configuration."""
    return {
        key: det_cfg[key]
        for key in PROBE_SCAN_KWARG_KEYS
        if key in det_cfg and det_cfg.get(key) is not None
    }


def get_probe_x_domain_kwargs(det_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Extract X-domain probe kwargs for detector routes with custom reconstruction."""
    return {
        key: det_cfg[key]
        for key in PROBE_X_DOMAIN_KWARG_KEYS
        if key in det_cfg and det_cfg.get(key) is not None
    }


def get_cnn_apply_nms(det_cfg: Dict[str, Any]) -> bool:
    """Return explicit CNN NMS setting, defaulting to False (opt-in)."""
    return bool(det_cfg.get("cnn_apply_nms", DEFAULT_CNN_APPLY_NMS))


DENSE_ROUTE_NAME = "dense_full_pipeline"
REMOVED_DETECTOR_ROUTES = ("standard",)


def resolve_detector_route(det_cfg: Dict[str, Any] | None) -> str:
    """Return the single supported detector route (#522).

    ``dense_full_pipeline`` is the only route; an omitted key selects it. The former
    ``standard`` route (and any other value) is rejected instead of being reinterpreted.
    """
    route = (det_cfg or {}).get("detector_route", DENSE_ROUTE_NAME)
    if route == DENSE_ROUTE_NAME:
        return DENSE_ROUTE_NAME
    if route in REMOVED_DETECTOR_ROUTES:
        raise ValueError(
            f"detection.detector_route={route!r} was removed in #522; the only detector "
            f"route is {DENSE_ROUTE_NAME!r}. Delete the key or set it to {DENSE_ROUTE_NAME!r}; "
            "reproduce historical standard-route runs from commit 4f1594bc."
        )
    raise ValueError(
        f"Unknown detection.detector_route={route!r}; the only detector route is "
        f"{DENSE_ROUTE_NAME!r}"
    )
