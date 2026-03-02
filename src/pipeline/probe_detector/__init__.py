"""Core probe scan detection logic orchestrating submodules."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .bands import (
    build_divisi_map,
    resolve_bands,
    scan_staff_band_from_ink,
)
from .debug import write_debug_output
from .rescue import apply_gap_rescue, apply_rightmost_rescue
from .types import (
    BandSelectionConfig,
    Box,
    DivisiRescueConfig,
    GapRescueConfig,
    RightmostRescueConfig,
)

__all__ = [
    "detect_probe_scan",
]


def detect_probe_scan(
    base_img: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    band_source: str = "staff_mask",
    band_cluster_max_dist: float | None = None,
    band_min_row_count: int = 3,
    row_stats: Sequence[Dict[str, float]] | None = None,
    staff_space: float = 0.0,
    band_row_pad_ratio: float = 0.0,
    band_row_pad_staff_mult: float = 0.0,
    band_scan_width: int = 40,
    band_scan_line_ratio: float = 0.5,
    band_scan_min_lines: int = 3,
    band_scan_pad: int = 0,
    band_scan_pad_ratio: float = 0.0,
    save_row_profile: bool = False,
    probe_width: int = 4,
    ink_threshold: int = 180,
    min_ratio: float = 0.85,
    use_peak_relative_ratio: bool = False,
    peak_ratio_min: float = 0.9,
    extend_scale: float = 1.0,
    extend_max_ratio: float = 1.0,
    extend_top_max_ratio: float = 1.0,
    extend_bottom_max_ratio: float = 1.0,
    min_peak_distance: int = 6,
    refine_window: int = 4,
    max_per_band: int = 8,
    band_height_mode: str = "staff",
    band_height_scale: float = 1.0,
    band_height_min: int = 10,
    x_merge_tol: int = 4,
    scan_fallback_pred_band: bool = False,
    scan_disable_non_scan_extend: bool = False,
    scan_disable_existing_suppression: bool = False,
    scan_existing_min_vertical_iou: float = 0.0,
    scan_peak_band_height: int = 0,
    scan_center_on_peak: bool = False,
    scan_x_peak_rescue: bool = False,
    scan_x_peak_window: int = 12,
    scan_x_peak_ratio_min: float = 1.6,
    scan_x_peak_max_overhang: float = 1.0,
    scan_x_peak_rescue_mode: str = "topbottom",
    scan_x_peak_segment_height: int = 0,
    scan_x_peak_segment_pass_ratio: float = 1.0,
    scan_x_peak_segment_source: str = "scan_band",
    scan_x_peak_ignore_staff_peak: bool = False,
    scan_x_peak_ignore_radius: int = 1,
    scan_rightmost_rescue: bool = False,
    scan_rightmost_tolerance: int = 6,
    scan_rightmost_min_rows: int = 3,
    scan_rightmost_min_ratio: float = 0.85,
    scan_gap_rescue: bool = False,
    scan_gap_threshold_ratio: float = 1.8,
    scan_gap_rescue_min_ratio: float = 0.5,
    scan_gap_margin_ratio: float = 0.1,
    scan_ratio_rel_rescue: bool = False,
    scan_ratio_rel_rescue_min: float = 0.0,
    scan_ratio_rel_rescue_xpeak_min: float = 0.0,
    scan_ratio_rel_rescue_max_overhang: float = 1.0,
    divisi_rescue: bool = False,
    divisi_dist_ratio: float = 1.2,
    divisi_align_tol: int = 4,
    divisi_align_min_count: int = 2,
    divisi_min_ratio: float = 0.5,
    vertical_closing: int = 0,
    debug_path: Path | None = None,
) -> List[Box]:
    gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
    ink = (gray < ink_threshold).astype(np.uint8)
    if vertical_closing > 0:
        kernel = np.ones((vertical_closing, 1), np.uint8)
        ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel)
    h, w = ink.shape[:2]
    band_selection = BandSelectionConfig(
        band_source=band_source,
        band_cluster_max_dist=band_cluster_max_dist,
        band_min_row_count=band_min_row_count,
    )
    bands = resolve_bands(
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        row_stats=row_stats,
        config=band_selection,
    )
    if not bands:
        return []

    width = max(1, int(probe_width))
    kernel = np.ones(width, dtype=np.int32)

    global_heights = [abs(by2 - by1) for _, by1, _, by2 in existing_boxes if abs(by2 - by1) > 0]
    global_height = int(np.median(global_heights)) if global_heights else 0
    divisi_cfg = DivisiRescueConfig(
        enabled=divisi_rescue,
        dist_ratio=divisi_dist_ratio,
        align_tol=divisi_align_tol,
        align_min_count=divisi_align_min_count,
        min_ratio=divisi_min_ratio,
        band_source=band_source,
        band_height_mode=band_height_mode,
    )
    divisi_map = build_divisi_map(
        ink=ink,
        bands=bands,
        existing_boxes=existing_boxes,
        kernel=kernel,
        width=width,
        image_h=h,
        global_height=global_height,
        config=divisi_cfg,
    )

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        band_h = max(1.0, y2 - y1)
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                if scan_existing_min_vertical_iou > 0:
                    iy1 = max(y1, min(by1, by2))
                    iy2 = min(y2, max(by1, by2))
                    inter = max(0.0, iy2 - iy1)
                    box_h = max(1.0, abs(by2 - by1))
                    union = max(1.0, band_h + box_h - inter)
                    v_iou = inter / union
                    if v_iou < scan_existing_min_vertical_iou:
                        continue
                return True
        return False

    def has_existing_for_suppression(x_center: float, y1: int, y2: int) -> bool:
        if scan_disable_existing_suppression:
            return False
        return has_existing(x_center, y1, y2)

    def closest_existing_band(x_center: float, y1: int, y2: int) -> Tuple[int, int] | None:
        best = None
        best_dx = None
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            dx = abs(cx - x_center)
            if best_dx is None or dx < best_dx:
                best_dx = dx
                best = (int(by1), int(by2))
        return best

    candidates: List[Box] = []
    accepted_by_band: dict[int, list[float]] = {}
    trusted_accepted_by_band: dict[int, list[float]] = {}
    rejected_records: list[dict] = []
    debug_records = []
    for band_idx, (y1, y2) in enumerate(bands):
        scan_base_y1 = y1
        scan_base_y2 = y2
        if band_source == "horiz_scan":
            if band_scan_pad_ratio > 0:
                pad = int(round((y2 - y1 + 1) * band_scan_pad_ratio))
            else:
                pad = int(band_scan_pad)
            if pad > 0:
                scan_base_y1 = max(0, int(y1) - pad)
                scan_base_y2 = min(h - 1, int(y2) + pad)
        band_center = int(round((y1 + y2) / 2))
        band_h = max(1, y2 - y1 + 1)
        if band_source == "row_stats":
            band_y1 = max(0, int(y1))
            band_y2 = min(h - 1, int(y2))
            pad = 0
            if band_row_pad_ratio > 0:
                pad = int(round((band_y2 - band_y1 + 1) * band_row_pad_ratio))
            elif band_row_pad_staff_mult > 0 and staff_space > 0:
                pad = int(round(staff_space * band_row_pad_staff_mult))
            if pad > 0:
                band_y1 = max(0, band_y1 - pad)
                band_y2 = min(h - 1, band_y2 + pad)
        else:
            if band_height_mode == "median_box":
                heights = [
                    abs(by2 - by1)
                    for _, by1, _, by2 in existing_boxes
                    if y1 <= (by1 + by2) / 2.0 <= y2 and abs(by2 - by1) > 0
                ]
                median_h = int(np.median(heights)) if heights else global_height
                target_h = (
                    max(band_height_min, int(round(median_h * band_height_scale)))
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
        ext_band_h = None
        ext_ratios = None
        ext_top_ratios = None
        ext_bottom_ratios = None
        ext_y1 = None
        ext_y2 = None
        top_h = 0
        bottom_h = 0
        if extend_scale > 1.0:
            ext_h = max(band_h, int(round(target_h * extend_scale)))
            ext_y1 = max(0, int(round(band_center - ext_h / 2)))
            ext_y2 = min(h - 1, int(round(band_center + ext_h / 2)))
            ext_band = ink[ext_y1 : ext_y2 + 1, :]
            ext_band_h = max(1, ext_y2 - ext_y1 + 1)
        col_sums = band.sum(axis=0)
        stripe_sums = np.convolve(col_sums, kernel, mode="same")
        ratios = stripe_sums / float(band_h * width)
        if ext_band is not None and ext_y1 is not None and ext_y2 is not None:
            ext_col_sums = ext_band.sum(axis=0)
            ext_stripe_sums = np.convolve(ext_col_sums, kernel, mode="same")
            ext_ratios = ext_stripe_sums / float(ext_band_h * width)
            top_h = max(0, band_y1 - ext_y1)
            bottom_h = max(0, ext_y2 - band_y2)
            if top_h > 0:
                top_band = ink[ext_y1:band_y1, :]
                top_col_sums = top_band.sum(axis=0)
                top_stripe_sums = np.convolve(top_col_sums, kernel, mode="same")
                ext_top_ratios = top_stripe_sums / float(top_h * width)
            if bottom_h > 0:
                bottom_band = ink[band_y2 + 1 : ext_y2 + 1, :]
                bottom_col_sums = bottom_band.sum(axis=0)
                bottom_stripe_sums = np.convolve(bottom_col_sums, kernel, mode="same")
                ext_bottom_ratios = bottom_stripe_sums / float(bottom_h * width)
        if ratios.size < 3:
            continue

        effective_min = min_ratio
        if scan_gap_rescue:
            effective_min = min(effective_min, scan_gap_rescue_min_ratio)

        peaks = np.where(
            (ratios >= effective_min) & (ratios >= np.roll(ratios, 1)) & (ratios >= np.roll(ratios, -1))
        )[0]
        if peaks.size == 0:
            debug_records.append({"band": [y1, y2], "status": "no_peaks", "band_idx": band_idx})
            continue
        peak_scores = [(int(x), float(ratios[x])) for x in peaks]
        peak_scores.sort(key=lambda item: item[1], reverse=True)
        selected: list[tuple[int, float]] = []
        for x, score in peak_scores:
            if any(abs(x - sx) < min_peak_distance for sx, _ in selected):
                continue
            selected.append((x, score))
            if max_per_band > 0 and len(selected) >= max_per_band:
                break
        for x, score in selected:
            left = max(0, int(x - refine_window))
            right = min(len(ratios) - 1, int(x + refine_window))
            if right >= left:
                local_idx = int(left + np.argmax(ratios[left : right + 1]))
            else:
                local_idx = int(x)
            x1 = max(0, int(round(local_idx - width / 2)))
            x2 = min(w - 1, int(round(local_idx + width / 2)))
            pred_band = closest_existing_band(float(local_idx), y1, y2)
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
            rescue_reason = None
            if band_source == "horiz_scan":
                scan_band = scan_staff_band_from_ink(
                    ink,
                    int(local_idx),
                    scan_base_y1,
                    scan_base_y2,
                    band_scan_width,
                    band_scan_line_ratio,
                    band_scan_min_lines,
                )
            if band_source in ("horiz_scan", "row_stats") and scan_base_y2 > scan_base_y1:
                full_strip = ink[scan_base_y1 : scan_base_y2 + 1, :]
                if full_strip.size > 0 and full_strip.shape[1] > 0:
                    row_ratio_full = full_strip.sum(axis=1) / float(full_strip.shape[1])
                    scan_row_ratio_mean = float(row_ratio_full.mean())
                    scan_row_ratio_max = float(row_ratio_full.max())
                    scan_row_ratio_lines = int((row_ratio_full >= band_scan_line_ratio).sum())
                    scan_peak_ratio = scan_row_ratio_max
                    if scan_peak_ratio is not None:
                        peak_idx = int(np.argmax(row_ratio_full))
                        scan_peak_row = int(scan_base_y1 + peak_idx)
                    if save_row_profile:
                        scan_row_profile = [float(v) for v in row_ratio_full.tolist()]
            if scan_band is not None:
                scan_y1, scan_y2 = scan_band
            elif scan_fallback_pred_band and pred_band is not None:
                scan_y1, scan_y2 = pred_band
            else:
                scan_y1, scan_y2 = band_y1, band_y2
            if band_source == "horiz_scan" and scan_center_on_peak and scan_peak_row is not None:
                peak_h = scan_peak_band_height if scan_peak_band_height > 0 else band_h
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
            if band_source == "horiz_scan":
                sx1 = max(0, int(round(local_idx - width / 2)))
                sx2 = min(w - 1, int(round(local_idx + width / 2)))
                scan_ratio = float(ink[scan_y1 : scan_y2 + 1, sx1 : sx2 + 1].sum()) / float(
                    scan_h * max(1, sx2 - sx1 + 1)
                )
                if scan_x_peak_rescue:

                    def compute_xpeak(band_y1: int, band_y2: int) -> tuple[Optional[float], int]:
                        ignored_rows = 0
                        if band_y2 < band_y1:
                            return None, ignored_rows
                        scan_strip = ink[band_y1 : band_y2 + 1, :]
                        if scan_strip.size == 0:
                            return None, ignored_rows
                        if scan_x_peak_ignore_staff_peak and scan_peak_row is not None:
                            rel_peak = int(scan_peak_row - band_y1)
                            radius = max(0, int(scan_x_peak_ignore_radius))
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
                        wsize = max(1, int(scan_x_peak_window))
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
                    if scan_x_peak_segment_height > 0:
                        seg_source_y1 = scan_y1
                        seg_source_y2 = scan_y2
                        if (
                            scan_x_peak_segment_source == "scan_ext_band"
                            and scan_ext_y1 is not None
                            and scan_ext_y2 is not None
                        ):
                            seg_source_y1 = scan_ext_y1
                            seg_source_y2 = scan_ext_y2
                        seg_h = max(1, int(scan_x_peak_segment_height))
                        segs = []
                        for seg_y in range(seg_source_y1, seg_source_y2 + 1, seg_h):
                            seg_y2 = min(seg_source_y2, seg_y + seg_h - 1)
                            seg_ratio, _ = compute_xpeak(seg_y, seg_y2)
                            if seg_ratio is not None:
                                segs.append(seg_ratio)
                        if segs:
                            scan_x_peak_segment_min = float(min(segs))
                            pass_count = sum(1 for v in segs if v >= scan_x_peak_ratio_min)
                            scan_x_peak_segment_pass = pass_count / float(len(segs))
                scan_peak_ratio_local = None
                if scan_peak_row is not None:
                    peak_y1 = scan_peak_row
                    peak_h = scan_peak_band_height if scan_peak_band_height > 0 else scan_h
                    peak_y2 = min(h - 1, int(peak_y1 + peak_h - 1))
                    if peak_y1 <= peak_y2:
                        scan_peak_ratio_local = float(
                            ink[peak_y1 : peak_y2 + 1, sx1 : sx2 + 1].sum()
                        ) / float(max(1, peak_y2 - peak_y1 + 1) * max(1, sx2 - sx1 + 1))
                if extend_scale > 1.0:
                    ext_h = max(scan_h, int(round(scan_h * extend_scale)))
                    scan_center = int(round((scan_y1 + scan_y2) / 2))
                    scan_ext_y1 = max(0, int(round(scan_center - ext_h / 2)))
                    scan_ext_y2 = min(h - 1, int(round(scan_center + ext_h / 2)))
                    ext_h = max(1, scan_ext_y2 - scan_ext_y1 + 1)
                    scan_ext_ratio = float(
                        ink[scan_ext_y1 : scan_ext_y2 + 1, sx1 : sx2 + 1].sum()
                    ) / float(ext_h * max(1, sx2 - sx1 + 1))
                    top_h_scan = max(0, scan_y1 - scan_ext_y1)
                    bottom_h_scan = max(0, scan_ext_y2 - scan_y2)
                    scan_top_h = int(top_h_scan)
                    scan_bottom_h = int(bottom_h_scan)
                    if top_h_scan > 0:
                        scan_top_ratio = float(
                            ink[scan_ext_y1:scan_y1, sx1 : sx2 + 1].sum()
                        ) / float(top_h_scan * max(1, sx2 - sx1 + 1))
                    if bottom_h_scan > 0:
                        scan_bottom_ratio = float(
                            ink[scan_y2 + 1 : scan_ext_y2 + 1, sx1 : sx2 + 1].sum()
                        ) / float(bottom_h_scan * max(1, sx2 - sx1 + 1))
            record_base = {
                "band": [band_y1, band_y2],
                "staff_band": [y1, y2],
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
                if band_source == "horiz_scan"
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
            if use_peak_relative_ratio and scan_peak_ratio_local:
                peak_relative_ratio = scan_ratio / max(scan_peak_ratio_local, 1e-6)
            else:
                peak_relative_ratio = None

            # Determine the primary ratio to check against min_ratio
            check_ratio = scan_ratio if scan_ratio is not None else float(ratios[local_idx])

            if check_ratio < min_ratio:
                rec = {
                    "status": "scan_ratio_low",
                    "col": local_idx,
                    "ratio": check_ratio,
                    "extended_ratio": scan_ext_ratio,
                    "top_ratio": scan_top_ratio,
                    "bottom_ratio": scan_bottom_ratio,
                    "peak_relative_ratio": peak_relative_ratio,
                    "seed_col": x,
                    **record_base,
                }
                debug_records.append(rec)
                rejected_records.append(
                    {
                        "band_idx": band_idx,
                        "col": float(local_idx),
                        "box": (x1, band_y1, x2, band_y2),
                        "record": rec,
                    }
                )
                continue
            if (
                use_peak_relative_ratio
                and peak_relative_ratio is not None
                and peak_relative_ratio < peak_ratio_min
            ):
                rescue_ok = (
                    scan_ratio_rel_rescue
                    and peak_relative_ratio is not None
                    and peak_relative_ratio >= scan_ratio_rel_rescue_min
                    and scan_x_peak_ratio is not None
                    and scan_x_peak_ratio >= scan_ratio_rel_rescue_xpeak_min
                    and (
                        scan_top_ratio is None
                        or scan_top_ratio <= scan_ratio_rel_rescue_max_overhang
                    )
                    and (
                        scan_bottom_ratio is None
                        or scan_bottom_ratio <= scan_ratio_rel_rescue_max_overhang
                    )
                )
                if rescue_ok:
                    rec = {
                        "status": "scan_ratio_rel_low_rescued_limited",
                        "col": local_idx,
                        "ratio": scan_ratio,
                        "extended_ratio": scan_ext_ratio,
                        "top_ratio": scan_top_ratio,
                        "bottom_ratio": scan_bottom_ratio,
                        "peak_relative_ratio": peak_relative_ratio,
                        "seed_col": x,
                        **record_base,
                    }
                    debug_records.append(rec)
                    candidates.append((x1, band_y1, x2, band_y2))
                    accepted_by_band.setdefault(band_idx, []).append(float(local_idx))
                    # Rescued items are not added to trusted_accepted_by_band
                    continue
                rec = {
                    "status": "scan_ratio_rel_low",
                    "col": local_idx,
                    "ratio": scan_ratio,
                    "extended_ratio": scan_ext_ratio,
                    "top_ratio": scan_top_ratio,
                    "bottom_ratio": scan_bottom_ratio,
                    "peak_relative_ratio": peak_relative_ratio,
                    "seed_col": x,
                    **record_base,
                }
                debug_records.append(rec)
                rejected_records.append(
                    {
                        "band_idx": band_idx,
                        "col": float(local_idx),
                        "box": (x1, band_y1, x2, band_y2),
                        "record": rec,
                    }
                )
                continue
            if (
                scan_ext_ratio is not None
                and extend_max_ratio < 1.0
                and scan_ext_ratio >= extend_max_ratio
            ):
                rec = {
                    "status": "extended_ratio_scan",
                    "col": local_idx,
                    "ratio": scan_ratio,
                    "extended_ratio": scan_ext_ratio,
                    "top_ratio": scan_top_ratio,
                    "bottom_ratio": scan_bottom_ratio,
                    "seed_col": x,
                    **record_base,
                }
                debug_records.append(rec)
                rejected_records.append(
                    {
                        "band_idx": band_idx,
                        "col": float(local_idx),
                        "box": (x1, band_y1, x2, band_y2),
                        "record": rec,
                    }
                )
                continue
            if (
                scan_top_ratio is not None
                and extend_top_max_ratio < 1.0
                and scan_top_ratio >= extend_top_max_ratio
            ):
                is_divisi_link = False
                if divisi_rescue and band_idx in divisi_map and divisi_map[band_idx]["has_top"]:
                    is_divisi_link = True

                rescue_ok = False
                if is_divisi_link:
                    rescue_ok = True
                else:
                    rescue_ok = (
                        scan_x_peak_rescue_mode in ("topbottom", "both")
                        and scan_x_peak_rescue
                        and scan_x_peak_ratio is not None
                        and scan_x_peak_ratio >= scan_x_peak_ratio_min
                        and (scan_top_ratio is None or scan_top_ratio <= scan_x_peak_max_overhang)
                        and (
                            scan_bottom_ratio is None
                            or scan_bottom_ratio <= scan_x_peak_max_overhang
                        )
                    )
                    if scan_x_peak_segment_height > 0 and scan_x_peak_segment_pass is not None:
                        rescue_ok = rescue_ok and (
                            scan_x_peak_segment_pass >= scan_x_peak_segment_pass_ratio
                        )

                if rescue_ok:
                    rescue_reason = "top_divisi" if is_divisi_link else "top_xpeak"
                    # Rescued: pass to next checks (do not continue/return, allowing fall-through to accepted)
                    pass
                else:
                    rec = {
                        "status": "extended_top_ratio_scan",
                        "col": local_idx,
                        "ratio": scan_ratio,
                        "extended_ratio": scan_ext_ratio,
                        "top_ratio": scan_top_ratio,
                        "bottom_ratio": scan_bottom_ratio,
                        "seed_col": x,
                        **record_base,
                    }
                    debug_records.append(rec)
                    rejected_records.append(
                        {
                            "band_idx": band_idx,
                            "col": float(local_idx),
                            "box": (x1, band_y1, x2, band_y2),
                            "record": rec,
                        }
                    )
                    continue
            if (
                scan_bottom_ratio is not None
                and extend_bottom_max_ratio < 1.0
                and scan_bottom_ratio >= extend_bottom_max_ratio
            ):
                is_divisi_link = False
                if divisi_rescue and band_idx in divisi_map and divisi_map[band_idx]["has_bottom"]:
                    is_divisi_link = True

                rescue_ok = False
                if is_divisi_link:
                    rescue_ok = True
                else:
                    rescue_ok = (
                        scan_x_peak_rescue_mode in ("topbottom", "both")
                        and scan_x_peak_rescue
                        and scan_x_peak_ratio is not None
                        and scan_x_peak_ratio >= scan_x_peak_ratio_min
                        and (scan_top_ratio is None or scan_top_ratio <= scan_x_peak_max_overhang)
                        and (
                            scan_bottom_ratio is None
                            or scan_bottom_ratio <= scan_x_peak_max_overhang
                        )
                    )
                    if scan_x_peak_segment_height > 0 and scan_x_peak_segment_pass is not None:
                        rescue_ok = rescue_ok and (
                            scan_x_peak_segment_pass >= scan_x_peak_segment_pass_ratio
                        )

                if rescue_ok:
                    rescue_reason = "bot_divisi" if is_divisi_link else "bot_xpeak"
                    pass
                else:
                    rec = {
                        "status": "extended_bottom_ratio_scan",
                        "col": local_idx,
                        "ratio": scan_ratio,
                        "extended_ratio": scan_ext_ratio,
                        "top_ratio": scan_top_ratio,
                        "bottom_ratio": scan_bottom_ratio,
                        "seed_col": x,
                        **record_base,
                    }
                    debug_records.append(rec)
                    rejected_records.append(
                        {
                            "band_idx": band_idx,
                            "col": float(local_idx),
                            "box": (x1, band_y1, x2, band_y2),
                            "record": rec,
                        }
                    )
                    continue
            if not (scan_disable_non_scan_extend and band_source == "horiz_scan"):
                if ext_ratios is not None and extend_max_ratio < 1.0:
                    ext_ratio = float(ext_ratios[local_idx])
                    if ext_ratio >= extend_max_ratio:
                        rec = {
                            "status": "extended_ratio",
                            "col": local_idx,
                            "ratio": float(ratios[local_idx]),
                            "extended_ratio": ext_ratio,
                            "top_ratio": float(ext_top_ratios[local_idx])
                            if ext_top_ratios is not None
                            else None,
                            "bottom_ratio": float(ext_bottom_ratios[local_idx])
                            if ext_bottom_ratios is not None
                            else None,
                            "seed_col": x,
                            **record_base,
                        }
                        debug_records.append(rec)
                        rejected_records.append(
                            {
                                "band_idx": band_idx,
                                "col": float(local_idx),
                                "box": (x1, band_y1, x2, band_y2),
                                "record": rec,
                            }
                        )
                        continue
                if ext_top_ratios is not None and extend_top_max_ratio < 1.0:
                    top_ratio = float(ext_top_ratios[local_idx])
                    if top_ratio >= extend_top_max_ratio:
                        rec = {
                            "status": "extended_top_ratio",
                            "col": local_idx,
                            "ratio": float(ratios[local_idx]),
                            "extended_ratio": float(ext_ratios[local_idx])
                            if ext_ratios is not None
                            else None,
                            "top_ratio": top_ratio,
                            "bottom_ratio": float(ext_bottom_ratios[local_idx])
                            if ext_bottom_ratios is not None
                            else None,
                            "seed_col": x,
                            **record_base,
                        }
                        debug_records.append(rec)
                        rejected_records.append(
                            {
                                "band_idx": band_idx,
                                "col": float(local_idx),
                                "box": (x1, band_y1, x2, band_y2),
                                "record": rec,
                            }
                        )
                        continue
                if ext_bottom_ratios is not None and extend_bottom_max_ratio < 1.0:
                    bottom_ratio = float(ext_bottom_ratios[local_idx])
                    if bottom_ratio >= extend_bottom_max_ratio:
                        rec = {
                            "status": "extended_bottom_ratio",
                            "col": local_idx,
                            "ratio": float(ratios[local_idx]),
                            "extended_ratio": float(ext_ratios[local_idx])
                            if ext_ratios is not None
                            else None,
                            "top_ratio": float(ext_top_ratios[local_idx])
                            if ext_top_ratios is not None
                            else None,
                            "bottom_ratio": bottom_ratio,
                            "seed_col": x,
                            **record_base,
                        }
                        debug_records.append(rec)
                        rejected_records.append(
                            {
                                "band_idx": band_idx,
                                "col": float(local_idx),
                                "box": (x1, band_y1, x2, band_y2),
                                "record": rec,
                            }
                        )
                        continue

            if has_existing_for_suppression(float(local_idx), y1, y2):
                debug_records.append(
                    {
                        "status": "existing",
                        "col": local_idx,
                        "ratio": float(ratios[local_idx]),
                        "extended_ratio": float(ext_ratios[local_idx])
                        if ext_ratios is not None
                        else None,
                        "top_ratio": float(ext_top_ratios[local_idx])
                        if ext_top_ratios is not None
                        else None,
                        "bottom_ratio": float(ext_bottom_ratios[local_idx])
                        if ext_bottom_ratios is not None
                        else None,
                        "seed_col": x,
                        **record_base,
                    }
                )
                continue
            candidates.append((x1, band_y1, x2, band_y2))
            accepted_by_band.setdefault(band_idx, []).append(float(local_idx))
            if rescue_reason is None:
                trusted_accepted_by_band.setdefault(band_idx, []).append(float(local_idx))

            debug_records.append(
                {
                    "status": "accepted" if rescue_reason is None else f"accepted_{rescue_reason}",
                    "col": local_idx,
                    "ratio": float(ratios[local_idx]),
                    "extended_ratio": float(ext_ratios[local_idx])
                    if ext_ratios is not None
                    else None,
                    "top_ratio": float(ext_top_ratios[local_idx])
                    if ext_top_ratios is not None
                    else None,
                    "bottom_ratio": float(ext_bottom_ratios[local_idx])
                    if ext_bottom_ratios is not None
                    else None,
                    "seed_col": x,
                    **record_base,
                }
            )

    rightmost_cfg = RightmostRescueConfig(
        enabled=scan_rightmost_rescue,
        tolerance=scan_rightmost_tolerance,
        min_rows=scan_rightmost_min_rows,
        min_ratio=scan_rightmost_min_ratio,
    )
    apply_rightmost_rescue(
        config=rightmost_cfg,
        accepted_by_band=accepted_by_band,
        trusted_accepted_by_band=trusted_accepted_by_band,
        rejected_records=rejected_records,
        bands=bands,
        has_existing=has_existing_for_suppression,
        candidates=candidates,
        debug_records=debug_records,
    )

    gap_cfg = GapRescueConfig(
        enabled=scan_gap_rescue,
        threshold_ratio=scan_gap_threshold_ratio,
        min_ratio=scan_gap_rescue_min_ratio,
        margin_ratio=scan_gap_margin_ratio,
    )
    apply_gap_rescue(
        config=gap_cfg,
        accepted_by_band=accepted_by_band,
        rejected_records=rejected_records,
        bands=bands,
        existing_boxes=existing_boxes,
        has_existing=has_existing_for_suppression,
        candidates=candidates,
        debug_records=debug_records,
    )

    if debug_path is not None:
        debug_params = {
            "method": "probe_scan",
            "band_source": band_source,
            "band_cluster_max_dist": band_cluster_max_dist,
            "band_min_row_count": band_min_row_count,
            "band_row_stats_count": len(row_stats) if row_stats is not None else None,
            "band_row_pad_ratio": band_row_pad_ratio,
            "band_row_pad_staff_mult": band_row_pad_staff_mult,
            "band_scan_width": band_scan_width,
            "band_scan_line_ratio": band_scan_line_ratio,
            "band_scan_min_lines": band_scan_min_lines,
            "band_scan_pad": band_scan_pad,
            "band_scan_pad_ratio": band_scan_pad_ratio,
            "save_row_profile": save_row_profile,
            "probe_width": width,
            "ink_threshold": ink_threshold,
            "min_ratio": min_ratio,
            "extend_scale": extend_scale,
            "extend_max_ratio": extend_max_ratio,
            "extend_top_max_ratio": extend_top_max_ratio,
            "extend_bottom_max_ratio": extend_bottom_max_ratio,
            "min_peak_distance": min_peak_distance,
            "max_per_band": max_per_band,
            "x_merge_tol": x_merge_tol,
            "use_peak_relative_ratio": use_peak_relative_ratio,
            "peak_ratio_min": peak_ratio_min,
            "scan_peak_band_height": scan_peak_band_height,
            "scan_center_on_peak": scan_center_on_peak,
            "scan_x_peak_rescue": scan_x_peak_rescue,
            "scan_x_peak_window": scan_x_peak_window,
            "scan_x_peak_ratio_min": scan_x_peak_ratio_min,
            "scan_x_peak_max_overhang": scan_x_peak_max_overhang,
            "scan_x_peak_rescue_mode": scan_x_peak_rescue_mode,
            "scan_x_peak_segment_height": scan_x_peak_segment_height,
            "scan_x_peak_segment_pass_ratio": scan_x_peak_segment_pass_ratio,
            "scan_x_peak_segment_source": scan_x_peak_segment_source,
            "scan_x_peak_ignore_staff_peak": scan_x_peak_ignore_staff_peak,
            "scan_x_peak_ignore_radius": scan_x_peak_ignore_radius,
            "scan_disable_existing_suppression": scan_disable_existing_suppression,
            "scan_existing_min_vertical_iou": scan_existing_min_vertical_iou,
            "scan_rightmost_rescue": scan_rightmost_rescue,
            "scan_rightmost_tolerance": scan_rightmost_tolerance,
            "scan_rightmost_min_rows": scan_rightmost_min_rows,
            "scan_rightmost_min_ratio": scan_rightmost_min_ratio,
            "scan_gap_rescue": scan_gap_rescue,
            "scan_gap_threshold_ratio": scan_gap_threshold_ratio,
            "scan_gap_rescue_min_ratio": scan_gap_rescue_min_ratio,
            "scan_gap_margin_ratio": scan_gap_margin_ratio,
            "scan_ratio_rel_rescue": scan_ratio_rel_rescue,
            "scan_ratio_rel_rescue_min": scan_ratio_rel_rescue_min,
            "scan_ratio_rel_rescue_xpeak_min": scan_ratio_rel_rescue_xpeak_min,
            "scan_ratio_rel_rescue_max_overhang": scan_ratio_rel_rescue_max_overhang,
        }
        write_debug_output(
            base_img=base_img,
            bands=bands,
            debug_records=debug_records,
            debug_path=debug_path,
            width=width,
            params=debug_params,
            divisi_map=divisi_map,
            extend_top_max_ratio=extend_top_max_ratio,
            extend_bottom_max_ratio=extend_bottom_max_ratio,
        )
    return candidates
