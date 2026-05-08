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
    base_img: np.ndarray | None = None,
    probe_width: int = 4,
    global_height: int = 0,
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

    # Active rescue: for any band that does not have a candidate near target, proactively add one.
    for band_idx, band in enumerate(bands):
        band_y1, band_y2 = band
        is_covered = False
        for bx1, by1, bx2, by2 in candidates:
            cy = (by1 + by2) / 2
            cx = (bx1 + bx2) / 2
            if band_y1 <= cy <= band_y2 and abs(cx - target) <= config.tolerance:
                if global_height > 0 and abs(by2 - by1) >= global_height * 0.7:
                    is_covered = True
                    break
                elif global_height == 0:
                    is_covered = True
                    break

        if not is_covered:
            local_target = target
            if base_img is not None:
                import cv2
                y_start = max(0, int(band_y1))
                y_end = min(base_img.shape[0], int(band_y2))
                x_start = max(0, int(target - config.tolerance))
                x_end = min(base_img.shape[1], int(target + config.tolerance))
                if y_end > y_start and x_end > x_start:
                    region = base_img[y_start:y_end, x_start:x_end]
                    if len(region.shape) == 3:
                        region = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
                    inv_region = 255 - region
                    col_sum = np.sum(inv_region, axis=0)
                    local_peak_idx = int(np.argmax(col_sum))
                    local_target = float(x_start + local_peak_idx)
            
            x1 = int(local_target - probe_width // 2)
            x2 = int(local_target + (probe_width - probe_width // 2))
            
            # Use global_height if current band is too short
            y1 = int(band_y1)
            y2 = int(band_y2)
            if global_height > 0 and (y2 - y1) < global_height * 0.8:
                center_y = (y1 + y2) // 2
                y1 = max(0, center_y - global_height // 2)
                y2 = min(base_img.shape[0], y1 + global_height)

            new_box = [x1, y1, x2, y2]
            candidates.append(new_box)
            debug_records.append(
                {
                    "status": "rightmost_active_injected",
                    "col": float(local_target),
                    "rightmost_target": target,
                    "band_idx": band_idx,
                    "height": y2 - y1,
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
        sorted_xs = sorted(set(xs))  # set to avoid 0-width gaps from overlaps
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
            # Use dynamic margin to avoid boundary noise.
            # Only rescue candidates that were rejected due to low ratio (not geometry issues).
            margin = gap_w * config.margin_ratio
            rescue_statuses = {"scan_ratio_low", "scan_ratio_rel_low"}

            gap_candidates = [
                rec
                for rec in rejected_records
                if rec["band_idx"] == band_idx
                and x_left + margin < rec["col"] < x_right - margin
                and rec["record"].get("status") in rescue_statuses
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

def apply_active_x_alignment_rescue(
    *,
    accepted_by_band: Dict[int, List[float]],
    bands: Sequence[Tuple[int, int]],
    existing_boxes: Sequence[Box],
    candidates: List[Box],
    debug_records: List[Dict[str, Any]],
    base_img: Any = None,
    probe_width: int = 4,
    tolerance: int = 15,
    global_height: int = 0,
) -> None:
    """Actively injects missing barlines if they strongly align with barlines in other bands."""
    if base_img is None:
        return

    import cv2
    import numpy as np

    # Collect ALL X coordinates (both from accepted_by_band AND existing_boxes)
    # This ensures we find targets even if they were missed in this system but found in others.
    all_x = []
    for xs in accepted_by_band.values():
        all_x.extend(xs)
    for bx1, by1, bx2, by2 in existing_boxes:
        all_x.append((bx1 + bx2) / 2.0)
    
    if not all_x:
        return

    # Find common X alignment clusters
    all_x = sorted(all_x)
    clusters = []
    current_cluster = [all_x[0]]
    for x in all_x[1:]:
        if x - current_cluster[0] <= tolerance:
            current_cluster.append(x)
        else:
            clusters.append(current_cluster)
            current_cluster = [x]
    clusters.append(current_cluster)

    # Use a fixed minimum number of bands/boxes to consider an alignment "strong"
    strong_targets = [np.median(c) for c in clusters if len(c) >= 3]

    # Find ALL systems by clustering existing_boxes by Y
    all_y_centers = [(by1 + by2) / 2.0 for _, by1, _, by2 in existing_boxes]
    system_centers = []
    if all_y_centers:
        all_y_centers = sorted(all_y_centers)
        y_clusters = []
        curr_y_cluster = [all_y_centers[0]]
        for y in all_y_centers[1:]:
            if y - curr_y_cluster[0] <= (global_height or 50) * 0.5:
                curr_y_cluster.append(y)
            else:
                y_clusters.append(curr_y_cluster)
                curr_y_cluster = [y]
        y_clusters.append(curr_y_cluster)
        system_centers = [np.median(c) for c in y_clusters]

    # Also include centers from bands list (staff mask)
    for y1, y2 in bands:
        bc = (y1 + y2) / 2.0
        if not any(abs(bc - sc) < (global_height or 50) * 0.3 for sc in system_centers):
            system_centers.append(bc)

    for target in strong_targets:
        for cy in system_centers:
            # Check if ANY candidate covers this (cy, target)
            is_covered = False
            for bx1, by1, bx2, by2 in candidates:
                if by1 <= cy <= by2 and abs((bx1 + bx2) / 2.0 - target) <= tolerance:
                    # Taller boxes (>= 70% of global height) count as covering.
                    if global_height > 0 and abs(by2 - by1) >= global_height * 0.7:
                        is_covered = True
                        break
                    elif global_height == 0:
                        is_covered = True
                        break
            
            if not is_covered:
                y1 = int(cy - (global_height or 80) // 2)
                y2 = int(cy + (global_height or 80) // 2)
                y_start = max(0, y1)
                y_end = min(base_img.shape[0], y2)
                x_start = max(0, int(target - tolerance))
                x_end = min(base_img.shape[1], int(target + tolerance))
                
                local_target = target
                if y_end > y_start and x_end > x_start:
                    region = base_img[y_start:y_end, x_start:x_end]
                    if len(region.shape) == 3:
                        region = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
                    inv_region = 255 - region
                    col_sum = np.sum(inv_region, axis=0)
                    local_peak_idx = int(np.argmax(col_sum))
                    local_target = float(x_start + local_peak_idx)
                
                x1 = int(local_target - probe_width // 2)
                x2 = int(local_target + (probe_width - probe_width // 2))
                
                new_box = [x1, y_start, x2, y_end]
                candidates.append(new_box)
                debug_records.append(
                    {
                        "status": "x_alignment_active_injected",
                        "col": float(local_target),
                        "target": float(target),
                        "cy": float(cy),
                        "height": y_end - y_start,
                    }
                )
