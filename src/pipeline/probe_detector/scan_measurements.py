"""Measure ink around one candidate without deciding whether to accept it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .bands import scan_staff_band_from_ink
from .projections import BandProjection
from .types import CandidateScanConfig


@dataclass(frozen=True)
class CandidateScanMeasurement:
    scan_ratio: float | None
    scan_ext_ratio: float | None
    scan_top_ratio: float | None
    scan_bottom_ratio: float | None
    scan_peak_ratio_local: float | None
    scan_x_peak_ratio: float | None
    scan_x_peak_segment_pass: float | None
    record_base: dict


def measure_candidate_scan(
    ink: np.ndarray,
    *,
    local_idx: int,
    pred_band: tuple[int, int] | None,
    staff_band: tuple[int, int],
    x_domain: tuple[int, int],
    projection: BandProjection,
    width: int,
    kernel: np.ndarray,
    config: CandidateScanConfig,
) -> CandidateScanMeasurement:
    h, w = ink.shape[:2]
    y1, y2 = staff_band
    domain_x1, domain_x2 = x_domain
    scan_base_y1 = projection.scan_base_y1
    scan_base_y2 = projection.scan_base_y2
    band_y1 = projection.band_y1
    band_y2 = projection.band_y2
    band_h = projection.band_h
    ext_y1 = projection.ext_y1
    ext_y2 = projection.ext_y2
    top_h = projection.top_h
    bottom_h = projection.bottom_h
    scan_band = None
    scan_row_ratio_mean = None
    scan_row_ratio_max = None
    scan_row_ratio_lines = None
    scan_top_h = None
    scan_bottom_h = None
    scan_row_profile = None
    scan_peak_ratio = None
    scan_peak_row = None
    scan_x_peak_ratio = None
    scan_x_peak_neighbor_median = None
    scan_x_peak_segment_min = None
    scan_x_peak_segment_pass = None
    scan_peak_ratio_local = None
    scan_x_peak_ignored_rows = 0
    if config.band_source == "horiz_scan":
        scan_band = scan_staff_band_from_ink(
            ink,
            int(local_idx),
            scan_base_y1,
            scan_base_y2,
            config.band_scan_width,
            config.band_scan_line_ratio,
            config.band_scan_min_lines,
        )
    if config.band_source in ("horiz_scan", "row_stats") and scan_base_y2 > scan_base_y1:
        full_strip = ink[scan_base_y1 : scan_base_y2 + 1, :]
        if full_strip.size > 0 and full_strip.shape[1] > 0:
            row_ratio_full = full_strip.sum(axis=1) / float(full_strip.shape[1])
            scan_row_ratio_mean = float(row_ratio_full.mean())
            scan_row_ratio_max = float(row_ratio_full.max())
            scan_row_ratio_lines = int((row_ratio_full >= config.band_scan_line_ratio).sum())
            scan_peak_ratio = scan_row_ratio_max
            if scan_peak_ratio is not None:
                peak_idx = int(np.argmax(row_ratio_full))
                scan_peak_row = int(scan_base_y1 + peak_idx)
            if config.save_row_profile:
                scan_row_profile = [float(v) for v in row_ratio_full.tolist()]
    if scan_band is not None:
        scan_y1, scan_y2 = scan_band
    elif config.scan_fallback_pred_band and pred_band is not None:
        scan_y1, scan_y2 = pred_band
    else:
        scan_y1, scan_y2 = band_y1, band_y2
    if (
        config.band_source == "horiz_scan"
        and config.scan_center_on_peak
        and scan_peak_row is not None
    ):
        peak_h = config.scan_peak_band_height if config.scan_peak_band_height > 0 else band_h
        peak_h = max(1, int(peak_h))
        scan_y1 = max(0, int(scan_peak_row - peak_h // 2))
        scan_y2 = min(h - 1, int(scan_y1 + peak_h - 1))
    scan_h = max(1, scan_y2 - scan_y1 + 1)
    scan_ratio = None
    scan_ext_ratio = None
    scan_top_ratio = None
    scan_bottom_ratio = None
    scan_ext_y1 = None
    scan_ext_y2 = None
    if config.band_source == "horiz_scan":
        sx1 = max(0, int(round(local_idx - width / 2)))
        sx2 = min(w - 1, int(round(local_idx + width / 2)))
        scan_ratio = float(ink[scan_y1 : scan_y2 + 1, sx1 : sx2 + 1].sum()) / float(
            scan_h * max(1, sx2 - sx1 + 1)
        )
        if config.scan_x_peak_rescue:

            def compute_xpeak(band_y1: int, band_y2: int) -> tuple[Optional[float], int]:
                ignored_rows = 0
                if band_y2 < band_y1:
                    return None, ignored_rows
                scan_strip = ink[band_y1 : band_y2 + 1, :]
                if scan_strip.size == 0:
                    return None, ignored_rows
                if config.scan_x_peak_ignore_staff_peak and scan_peak_row is not None:
                    rel_peak = int(scan_peak_row - band_y1)
                    radius = max(0, int(config.scan_x_peak_ignore_radius))
                    y_start = max(0, rel_peak - radius)
                    y_end = min(scan_strip.shape[0] - 1, rel_peak + radius)
                    if y_start <= y_end:
                        scan_strip = scan_strip.copy()
                        scan_strip[y_start : y_end + 1, :] = 0
                        ignored_rows += y_end - y_start + 1
                scan_col_sums = scan_strip.sum(axis=0)
                scan_stripe_sums = np.convolve(scan_col_sums, kernel, mode="same")
                band_h = max(1, band_y2 - band_y1 + 1)
                scan_ratios_full = scan_stripe_sums / float(band_h * width)
                wsize = max(1, int(config.scan_x_peak_window))
                left = max(0, int(local_idx - wsize))
                right = min(len(scan_ratios_full) - 1, int(local_idx + wsize))
                if right < left:
                    return None, ignored_rows
                neighbor_vals = [
                    scan_ratios_full[i] for i in range(left, right + 1) if i != local_idx
                ]
                if not neighbor_vals:
                    return None, ignored_rows
                neighbor_median = float(np.median(neighbor_vals))
                if neighbor_median <= 0:
                    return None, ignored_rows
                return float(scan_ratios_full[local_idx]) / neighbor_median, ignored_rows

            scan_x_peak_ratio, ignored_rows = compute_xpeak(scan_y1, scan_y2)
            scan_x_peak_ignored_rows += ignored_rows
            if scan_x_peak_ratio is not None:
                scan_x_peak_neighbor_median = scan_x_peak_ratio
            if config.scan_x_peak_segment_height > 0:
                seg_source_y1 = scan_y1
                seg_source_y2 = scan_y2
                if (
                    config.scan_x_peak_segment_source == "scan_ext_band"
                    and scan_ext_y1 is not None
                    and scan_ext_y2 is not None
                ):
                    seg_source_y1 = scan_ext_y1
                    seg_source_y2 = scan_ext_y2
                seg_h = max(1, int(config.scan_x_peak_segment_height))
                segs = []
                for seg_y in range(seg_source_y1, seg_source_y2 + 1, seg_h):
                    seg_y2 = min(seg_source_y2, seg_y + seg_h - 1)
                    seg_ratio, _ = compute_xpeak(seg_y, seg_y2)
                    if seg_ratio is not None:
                        segs.append(seg_ratio)
                if segs:
                    scan_x_peak_segment_min = float(min(segs))
                    pass_count = sum(1 for v in segs if v >= config.scan_x_peak_ratio_min)
                    scan_x_peak_segment_pass = pass_count / float(len(segs))
        scan_peak_ratio_local = None
        if scan_peak_row is not None:
            peak_y1 = scan_peak_row
            peak_h = config.scan_peak_band_height if config.scan_peak_band_height > 0 else scan_h
            peak_y2 = min(h - 1, int(peak_y1 + peak_h - 1))
            if peak_y1 <= peak_y2:
                scan_peak_ratio_local = float(
                    ink[peak_y1 : peak_y2 + 1, sx1 : sx2 + 1].sum()
                ) / float(max(1, peak_y2 - peak_y1 + 1) * max(1, sx2 - sx1 + 1))
        if config.extend_scale > 1.0:
            ext_h = max(scan_h, int(round(scan_h * config.extend_scale)))
            scan_center = int(round((scan_y1 + scan_y2) / 2))
            scan_ext_y1 = max(0, int(round(scan_center - ext_h / 2)))
            scan_ext_y2 = min(h - 1, int(round(scan_center + ext_h / 2)))
            ext_h = max(1, scan_ext_y2 - scan_ext_y1 + 1)
            scan_ext_ratio = float(ink[scan_ext_y1 : scan_ext_y2 + 1, sx1 : sx2 + 1].sum()) / float(
                ext_h * max(1, sx2 - sx1 + 1)
            )
            top_h_scan = max(0, scan_y1 - scan_ext_y1)
            bottom_h_scan = max(0, scan_ext_y2 - scan_y2)
            scan_top_h = int(top_h_scan)
            scan_bottom_h = int(bottom_h_scan)
            if top_h_scan > 0:
                scan_top_ratio = float(ink[scan_ext_y1:scan_y1, sx1 : sx2 + 1].sum()) / float(
                    top_h_scan * max(1, sx2 - sx1 + 1)
                )
            if bottom_h_scan > 0:
                scan_bottom_ratio = float(
                    ink[scan_y2 + 1 : scan_ext_y2 + 1, sx1 : sx2 + 1].sum()
                ) / float(bottom_h_scan * max(1, sx2 - sx1 + 1))
    record_base = {
        "band": [band_y1, band_y2],
        "staff_band": [y1, y2],
        "scan_x_domain": [domain_x1, domain_x2],
        "pred_band": list(pred_band) if pred_band is not None else None,
        "ext_band": [int(ext_y1), int(ext_y2)]
        if ext_y1 is not None and ext_y2 is not None
        else None,
        "top_h": int(top_h),
        "bottom_h": int(bottom_h),
        "scan_band": [int(scan_y1), int(scan_y2)] if scan_band is not None else None,
        "scan_ext_band": [int(scan_ext_y1), int(scan_ext_y2)]
        if scan_ext_y1 is not None and scan_ext_y2 is not None
        else None,
        "scan_base_band": [int(scan_base_y1), int(scan_base_y2)]
        if config.band_source == "horiz_scan"
        else None,
        "scan_row_ratio_mean": scan_row_ratio_mean,
        "scan_row_ratio_max": scan_row_ratio_max,
        "scan_row_ratio_lines": scan_row_ratio_lines,
        "scan_top_h": scan_top_h,
        "scan_bottom_h": scan_bottom_h,
        "scan_row_profile": scan_row_profile,
        "scan_peak_ratio": scan_peak_ratio,
        "scan_peak_row": scan_peak_row,
        "scan_peak_ratio_local": scan_peak_ratio_local,
        "scan_x_peak_ratio": scan_x_peak_ratio,
        "scan_x_peak_neighbor_median": scan_x_peak_neighbor_median,
        "scan_x_peak_segment_min": scan_x_peak_segment_min,
        "scan_x_peak_segment_pass": scan_x_peak_segment_pass,
        "scan_x_peak_ignored_rows": scan_x_peak_ignored_rows,
    }
    return CandidateScanMeasurement(
        scan_ratio=scan_ratio,
        scan_ext_ratio=scan_ext_ratio,
        scan_top_ratio=scan_top_ratio,
        scan_bottom_ratio=scan_bottom_ratio,
        scan_peak_ratio_local=scan_peak_ratio_local,
        scan_x_peak_ratio=scan_x_peak_ratio,
        scan_x_peak_segment_pass=scan_x_peak_segment_pass,
        record_base=record_base,
    )
