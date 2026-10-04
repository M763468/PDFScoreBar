"""Core probe scan detection logic orchestrating submodules."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Sequence

import cv2
import numpy as np

from src.pipeline.probe_detector.measurements import (
    measure_candidate_scan,
    project_staff_band,
    select_signal_peaks,
)

from .bands import (
    build_divisi_map,
    resolve_bands,
    resolve_x_domains,
)
from .debug import write_debug_output
from .existing import ExistingBarlines
from .rescue import apply_gap_rescue, apply_rightmost_rescue
from .types import (
    BandProjectionConfig,
    BandSelectionConfig,
    Box,
    CandidateScanConfig,
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
    scan_x_domain_mode: str = "full_width",
    scan_x_domain_pad: int = 0,
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
    scan_stats: Dict[str, object] | None = None,
) -> List[Box]:
    scan_started_at = time.perf_counter()
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
        if scan_stats is not None:
            scan_stats.update(
                {
                    "band_count": 0,
                    "image_width": w,
                    "full_width_columns": 0,
                    "eligible_domain_columns": 0,
                    "projected_columns": 0,
                    "full_width_domain_count": 0,
                    "raw_peak_count": 0,
                    "selected_peak_count": 0,
                    "candidate_count": 0,
                    "elapsed_seconds": time.perf_counter() - scan_started_at,
                }
            )
        return []

    x_domains = resolve_x_domains(
        mode=scan_x_domain_mode,
        bands=bands,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        image_width=w,
        pad=scan_x_domain_pad,
    )

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
        x_domains=x_domains,
    )

    existing = ExistingBarlines(
        existing_boxes,
        x_merge_tol,
        scan_existing_min_vertical_iou,
        scan_disable_existing_suppression,
    )
    has_existing_for_suppression = existing.has_existing_for_suppression
    closest_existing_band = existing.closest_existing_band

    projection_config = BandProjectionConfig(
        band_source=band_source,
        band_scan_pad_ratio=band_scan_pad_ratio,
        band_scan_pad=band_scan_pad,
        band_row_pad_ratio=band_row_pad_ratio,
        band_row_pad_staff_mult=band_row_pad_staff_mult,
        staff_space=staff_space,
        band_height_mode=band_height_mode,
        band_height_min=band_height_min,
        band_height_scale=band_height_scale,
        extend_scale=extend_scale,
    )

    scan_config = CandidateScanConfig(
        band_scan_line_ratio=band_scan_line_ratio,
        band_scan_min_lines=band_scan_min_lines,
        band_scan_width=band_scan_width,
        band_source=band_source,
        extend_scale=extend_scale,
        save_row_profile=save_row_profile,
        scan_center_on_peak=scan_center_on_peak,
        scan_fallback_pred_band=scan_fallback_pred_band,
        scan_peak_band_height=scan_peak_band_height,
        scan_x_peak_rescue=scan_x_peak_rescue,
        scan_x_peak_segment_height=scan_x_peak_segment_height,
        scan_x_peak_segment_source=scan_x_peak_segment_source,
        scan_x_peak_ignore_staff_peak=scan_x_peak_ignore_staff_peak,
        scan_x_peak_ignore_radius=scan_x_peak_ignore_radius,
        scan_x_peak_window=scan_x_peak_window,
        scan_x_peak_ratio_min=scan_x_peak_ratio_min,
    )

    full_width_columns = 0
    eligible_domain_columns = 0
    projected_columns = 0
    full_width_domain_count = 0
    raw_peak_count = 0
    selected_peak_count = 0

    candidates: List[Box] = []
    accepted_by_band: dict[int, list[float]] = {}
    trusted_accepted_by_band: dict[int, list[float]] = {}
    rejected_records: list[dict] = []
    debug_records = []
    for band_idx, (y1, y2) in enumerate(bands):
        domain_x1, domain_x2 = x_domains[band_idx] if band_idx < len(x_domains) else (0, w - 1)
        domain_width = max(0, domain_x2 - domain_x1 + 1)
        full_width_columns += w
        eligible_domain_columns += domain_width
        if domain_x1 == 0 and domain_x2 == w - 1:
            full_width_domain_count += 1
        projection = project_staff_band(
            ink,
            y1=y1,
            y2=y2,
            existing_boxes=existing_boxes,
            global_height=global_height,
            kernel=kernel,
            width=width,
            x_domain=(domain_x1, domain_x2),
            config=projection_config,
        )
        band_y1 = projection.band_y1
        band_y2 = projection.band_y2
        ratios = projection.ratios
        ext_ratios = projection.ext_ratios
        ext_top_ratios = projection.ext_top_ratios
        ext_bottom_ratios = projection.ext_bottom_ratios
        projected_columns += projection.projected_columns
        if ratios.size < 3:
            continue

        effective_min = min_ratio
        if scan_gap_rescue:
            effective_min = min(effective_min, scan_gap_rescue_min_ratio)

        peak_count, selected = select_signal_peaks(
            ratios,
            effective_min=effective_min,
            domain_x1=domain_x1,
            domain_x2=domain_x2,
            min_peak_distance=min_peak_distance,
            max_per_band=max_per_band,
        )
        raw_peak_count += peak_count
        if peak_count == 0:
            debug_records.append(
                {
                    "band": [y1, y2],
                    "status": "no_peaks",
                    "band_idx": band_idx,
                    "scan_x_domain": [domain_x1, domain_x2],
                }
            )
            continue
        selected_peak_count += len(selected)
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
            measurement = measure_candidate_scan(
                ink,
                local_idx=local_idx,
                pred_band=pred_band,
                staff_band=(y1, y2),
                x_domain=(domain_x1, domain_x2),
                projection=projection,
                width=width,
                kernel=kernel,
                config=scan_config,
            )
            scan_ratio = measurement.scan_ratio
            scan_ext_ratio = measurement.scan_ext_ratio
            scan_top_ratio = measurement.scan_top_ratio
            scan_bottom_ratio = measurement.scan_bottom_ratio
            scan_peak_ratio_local = measurement.scan_peak_ratio_local
            scan_x_peak_ratio = measurement.scan_x_peak_ratio
            scan_x_peak_segment_pass = measurement.scan_x_peak_segment_pass
            record_base = measurement.record_base
            rescue_reason = None
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
            "scan_x_domain_mode": scan_x_domain_mode,
            "scan_x_domain_pad": scan_x_domain_pad,
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
            x_domains=x_domains,
            extend_top_max_ratio=extend_top_max_ratio,
            extend_bottom_max_ratio=extend_bottom_max_ratio,
        )
    if scan_stats is not None:
        scan_stats.update(
            {
                "band_count": len(bands),
                "image_width": w,
                "full_width_columns": full_width_columns,
                "eligible_domain_columns": eligible_domain_columns,
                "projected_columns": projected_columns,
                "full_width_domain_count": full_width_domain_count,
                "raw_peak_count": raw_peak_count,
                "selected_peak_count": selected_peak_count,
                "candidate_count": len(candidates),
                "eligible_width_ratio": (
                    eligible_domain_columns / float(full_width_columns)
                    if full_width_columns
                    else 1.0
                ),
                "projected_width_ratio": (
                    projected_columns / float(full_width_columns) if full_width_columns else 1.0
                ),
                "elapsed_seconds": time.perf_counter() - scan_started_at,
            }
        )
    return candidates
