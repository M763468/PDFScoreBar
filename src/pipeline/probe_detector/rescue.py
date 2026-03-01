"""Rescue logic for probe detection."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence, Tuple

import numpy as np

from .types import (
    _RIGHTMOST_RESCUE_DEBUG_KEYS,
    Box,
    GapRescueConfig,
    RightmostRescueConfig,
)


def apply_rightmost_rescue(
    *,
    config: RightmostRescueConfig,
    accepted_by_band: Dict[int, List[float]],
    trusted_accepted_by_band: Dict[int, List[float]],
    rejected_records: List[Dict[str, Any]],
    bands: Sequence[Tuple[int, int]],
    has_existing: Callable[[float, int, int], bool],
    candidates: List[Box],
    debug_records: List[Dict[str, Any]],
) -> None:
    if not config.enabled or not accepted_by_band:
        return

    pool = trusted_accepted_by_band if trusted_accepted_by_band else accepted_by_band
    rightmost_by_band_map = {band_idx: max(xs) for band_idx, xs in pool.items() if xs}
    rightmost_values = list(rightmost_by_band_map.values())
    if not rightmost_values:
        return

    max_col = max(rightmost_values)
    if config.min_ratio > 0:
        rightmost_values = [x for x in rightmost_values if x >= max_col * config.min_ratio]
    if not rightmost_values:
        rightmost_values = [max_col]
    target = float(np.median(rightmost_values))

    band_updates: dict[tuple[int, int], float] = {}
    for rec in rejected_records:
        band_as_list = rec["record"].get("staff_band")
        if not band_as_list:
            continue
        col = float(rec["col"])
        if abs(col - target) > config.tolerance:
            continue
        band_key = (int(band_as_list[0]), int(band_as_list[1]))
        prev = band_updates.get(band_key)
        if prev is None or abs(col - target) < abs(prev - target):
            band_updates[band_key] = col

    updated_values = []
    for band_idx, col in rightmost_by_band_map.items():
        band = bands[band_idx]
        updated_values.append(band_updates.get((int(band[0]), int(band[1])), col))
    inliers = [x for x in updated_values if abs(x - target) <= config.tolerance]
    if len(inliers) < config.min_rows:
        return

    rescued_cols: set[int] = set()
    rescue_statuses = {
        "scan_ratio_low",
        "scan_ratio_rel_low",
        "extended_ratio_scan",
        "extended_top_ratio_scan",
        "extended_bottom_ratio_scan",
    }
    for rec in rejected_records:
        rec_status = rec["record"].get("status")
        if rec_status not in rescue_statuses:
            continue
        col = float(rec["col"])
        if abs(col - target) > config.tolerance:
            continue
        col_i = int(round(col))
        if col_i in rescued_cols:
            continue
        box = rec["box"]
        if has_existing(col, box[1], box[3]):
            continue
        candidates.append(box)
        rescued_cols.add(col_i)
        debug_records.append(
            {
                "status": "rightmost_rescued",
                "col": col,
                "ratio": rec["record"].get("ratio"),
                "extended_ratio": rec["record"].get("extended_ratio"),
                "top_ratio": rec["record"].get("top_ratio"),
                "bottom_ratio": rec["record"].get("bottom_ratio"),
                "seed_col": rec["record"].get("seed_col"),
                "rightmost_target": target,
                "rightmost_delta": float(col - target),
                "rightmost_band_updated": bool(band_updates),
                **{k: rec["record"].get(k) for k in _RIGHTMOST_RESCUE_DEBUG_KEYS},
            }
        )


def apply_gap_rescue(
    *,
    config: GapRescueConfig,
    accepted_by_band: Dict[int, List[float]],
    rejected_records: List[Dict[str, Any]],
    bands: Sequence[Tuple[int, int]],
    existing_boxes: Sequence[Box],
    has_existing: Callable[[float, int, int], bool],
    candidates: List[Box],
    debug_records: List[Dict[str, Any]],
) -> None:
    """Rescue barlines in large gaps between detected barlines using relaxed threshold."""
    if not config.enabled:
        return

    # Build a combined pool of barlines per band (accepted + existing)
    # This ensures we find gaps that are truly empty.
    pool_by_band: Dict[int, List[float]] = {i: list(xs) for i, xs in accepted_by_band.items()}
    for bx1, by1, bx2, by2 in existing_boxes:
        cy = (by1 + by2) / 2.0
        cx = (bx1 + bx2) / 2.0
        for i, (y1, y2) in enumerate(bands):
            if y1 <= cy <= y2:
                pool_by_band.setdefault(i, []).append(cx)
                break

    if not pool_by_band:
        return

    # Calculate page-wide median gap between consecutive barlines
    all_gaps = []
    for _, xs in pool_by_band.items():
        if len(xs) < 2:
            continue
        sorted_xs = sorted(set(xs)) # set to avoid 0-width gaps from overlaps
        gaps = [sorted_xs[i + 1] - sorted_xs[i] for i in range(len(sorted_xs) - 1)]
        all_gaps.extend(gaps)

    if not all_gaps:
        return

    median_gap = float(np.median(all_gaps))
    threshold_gap = median_gap * config.threshold_ratio

    rescued_cols_by_band: Dict[int, set[int]] = {}

    for band_idx, xs in pool_by_band.items():
        sorted_xs = sorted(set(xs))
        rescued_cols = rescued_cols_by_band.setdefault(band_idx, set())

        for i in range(len(sorted_xs) - 1):
            x_left = sorted_xs[i]
            x_right = sorted_xs[i + 1]
            gap_w = x_right - x_left

            if gap_w < threshold_gap:
                continue

            # Look for candidates in this specific gap from rejected_records
            gap_candidates = [
                rec
                for rec in rejected_records
                if rec["band_idx"] == band_idx
                and x_left + 15 < rec["col"] < x_right - 15
                and rec["record"].get("ratio", 0) >= config.min_ratio
            ]

            if not gap_candidates:
                continue

            gap_candidates.sort(key=lambda r: r["record"].get("ratio", 0), reverse=True)
            best_rec = gap_candidates[0]

            col = float(best_rec["col"])
            col_i = int(round(col))
            if col_i in rescued_cols:
                continue

            box = best_rec["box"]
            if has_existing(col, box[1], box[3]):
                continue

            candidates.append(box)
            rescued_cols.add(col_i)
            debug_records.append(
                {
                    "status": "gap_rescued",
                    "col": col,
                    "ratio": best_rec["record"].get("ratio"),
                    "median_gap": median_gap,
                    "gap_width": gap_w,
                    **{k: best_rec["record"].get(k) for k in _RIGHTMOST_RESCUE_DEBUG_KEYS},
                }
            )
