"""Staff projections, peak selection and candidate measurements before acceptance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from .bands import compute_domain_ratios, scan_staff_band_from_ink
from .types import BandProjectionConfig, Box, CandidateScanConfig


@dataclass(frozen=True)
class BandProjection:
    scan_base_y1: int
    scan_base_y2: int
    band_y1: int
    band_y2: int
    band_h: int
    ratios: np.ndarray
    ext_ratios: np.ndarray | None
    ext_top_ratios: np.ndarray | None
    ext_bottom_ratios: np.ndarray | None
    ext_y1: int | None
    ext_y2: int | None
    top_h: int
    bottom_h: int
    projected_columns: int


def project_staff_band(
    ink: np.ndarray,
    *,
    y1: int,
    y2: int,
    existing_boxes: Sequence[Box],
    global_height: int,
    kernel: np.ndarray,
    width: int,
    x_domain: tuple[int, int],
    config: BandProjectionConfig,
) -> BandProjection:
    h, w = ink.shape[:2]
    domain_x1, domain_x2 = x_domain
    scan_base_y1 = y1
    scan_base_y2 = y2
    if config.band_source == "horiz_scan":
        if config.band_scan_pad_ratio > 0:
            pad = int(round((y2 - y1 + 1) * config.band_scan_pad_ratio))
        else:
            pad = int(config.band_scan_pad)
        if pad > 0:
            scan_base_y1 = max(0, int(y1) - pad)
            scan_base_y2 = min(h - 1, int(y2) + pad)
    band_center = int(round((y1 + y2) / 2))
    band_h = max(1, y2 - y1 + 1)
    if config.band_source == "row_stats":
        band_y1 = max(0, int(y1))
        band_y2 = min(h - 1, int(y2))
        pad = 0
        if config.band_row_pad_ratio > 0:
            pad = int(round((band_y2 - band_y1 + 1) * config.band_row_pad_ratio))
        elif config.band_row_pad_staff_mult > 0 and config.staff_space > 0:
            pad = int(round(config.staff_space * config.band_row_pad_staff_mult))
        if pad > 0:
            band_y1 = max(0, band_y1 - pad)
            band_y2 = min(h - 1, band_y2 + pad)
    else:
        if config.band_height_mode == "median_box":
            heights = [
                abs(by2 - by1)
                for _, by1, _, by2 in existing_boxes
                if y1 <= (by1 + by2) / 2.0 <= y2 and abs(by2 - by1) > 0
            ]
            median_h = int(np.median(heights)) if heights else global_height
            target_h = (
                max(config.band_height_min, int(round(median_h * config.band_height_scale)))
                if median_h
                else band_h
            )
        else:
            target_h = band_h
        band_y1 = max(0, int(band_center - target_h // 2))
        band_y2 = min(h - 1, int(band_center + target_h // 2))
    band = ink[band_y1 : band_y2 + 1, :]
    band_h = max(1, band_y2 - band_y1 + 1)
    target_h = band_h
    ext_band = None
    ext_ratios = None
    ext_top_ratios = None
    ext_bottom_ratios = None
    ext_y1 = None
    ext_y2 = None
    top_h = 0
    bottom_h = 0
    if config.extend_scale > 1.0:
        ext_h = max(band_h, int(round(target_h * config.extend_scale)))
        ext_y1 = max(0, int(round(band_center - ext_h / 2)))
        ext_y2 = min(h - 1, int(round(band_center + ext_h / 2)))
        ext_band = ink[ext_y1 : ext_y2 + 1, :]
    ratios, projected = compute_domain_ratios(
        band,
        kernel=kernel,
        width=width,
        image_width=w,
        x_domain=(domain_x1, domain_x2),
    )
    if ext_band is not None and ext_y1 is not None and ext_y2 is not None:
        ext_ratios, _ = compute_domain_ratios(
            ext_band,
            kernel=kernel,
            width=width,
            image_width=w,
            x_domain=(domain_x1, domain_x2),
        )
        top_h = max(0, band_y1 - ext_y1)
        bottom_h = max(0, ext_y2 - band_y2)
        if top_h > 0:
            top_band = ink[ext_y1:band_y1, :]
            ext_top_ratios, _ = compute_domain_ratios(
                top_band,
                kernel=kernel,
                width=width,
                image_width=w,
                x_domain=(domain_x1, domain_x2),
            )
        if bottom_h > 0:
            bottom_band = ink[band_y2 + 1 : ext_y2 + 1, :]
            ext_bottom_ratios, _ = compute_domain_ratios(
                bottom_band,
                kernel=kernel,
                width=width,
                image_width=w,
                x_domain=(domain_x1, domain_x2),
            )
    return BandProjection(
        scan_base_y1=scan_base_y1,
        scan_base_y2=scan_base_y2,
        band_y1=band_y1,
        band_y2=band_y2,
        band_h=band_h,
        ratios=ratios,
        ext_ratios=ext_ratios,
        ext_top_ratios=ext_top_ratios,
        ext_bottom_ratios=ext_bottom_ratios,
        ext_y1=ext_y1,
        ext_y2=ext_y2,
        top_h=top_h,
        bottom_h=bottom_h,
        projected_columns=projected,
    )


def select_signal_peaks(
    ratios: np.ndarray,
    *,
    effective_min: float,
    domain_x1: int,
    domain_x2: int,
    min_peak_distance: int,
    max_per_band: int,
) -> tuple[int, list[tuple[int, float]]]:
    peaks = np.where(
        (ratios >= effective_min) & (ratios >= np.roll(ratios, 1)) & (ratios >= np.roll(ratios, -1))
    )[0]
    peaks = peaks[(peaks >= domain_x1) & (peaks <= domain_x2)]
    peak_scores = [(int(x), float(ratios[x])) for x in peaks]
    peak_scores.sort(key=lambda item: item[1], reverse=True)
    selected: list[tuple[int, float]] = []
    for x, score in peak_scores:
        if any(abs(x - sx) < min_peak_distance for sx, _ in selected):
            continue
        selected.append((x, score))
        if max_per_band > 0 and len(selected) >= max_per_band:
            break
    return int(peaks.size), selected


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
