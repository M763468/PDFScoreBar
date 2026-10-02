"""Recover barlines at staff ends without changing existing geometry settings."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

import cv2
import numpy as np

from .barline_candidates import _ensure_mask_shape
from .types import BarlinePrediction, Box
from .utils import eprint


def _cluster_by_y_centers(y_centers: List[float], max_distance: float) -> List[List[int]]:
    if not y_centers:
        return []
    sorted_indices = np.argsort(y_centers)
    sorted_y = [y_centers[i] for i in sorted_indices]
    clusters: List[List[int]] = []
    current_cluster = [int(sorted_indices[0])]
    for idx in range(1, len(sorted_y)):
        if sorted_y[idx] - sorted_y[idx - 1] <= max_distance:
            current_cluster.append(int(sorted_indices[idx]))
        else:
            clusters.append(current_cluster)
            current_cluster = [int(sorted_indices[idx])]
    clusters.append(current_cluster)
    return clusters


def _scan_vertical_line(
    gray: np.ndarray,
    y_top: int,
    y_bottom: int,
    x_center: float,
    *,
    search_half_width: int,
    dark_threshold: int,
    min_dark_ratio: float,
    right_band_px: int,
    right_dark_ratio_max: float,
    line_width: int,
) -> Optional[Box]:
    h, w = gray.shape[:2]
    y1 = max(0, min(h - 1, y_top))
    y2 = max(0, min(h, y_bottom))
    if y2 <= y1:
        return None

    x_start = max(0, int(round(x_center - search_half_width)))
    x_end = min(w - 1, int(round(x_center + search_half_width)))
    if x_end < x_start:
        return None

    best = None
    best_ratio = 0.0
    for x in range(x_start, x_end + 1):
        x1 = x
        x2 = min(w, x + line_width)
        if x2 <= x1:
            continue
        column = gray[y1:y2, x1:x2]
        dark_ratio = float(np.mean(column < dark_threshold))
        if dark_ratio < min_dark_ratio:
            continue

        rx1 = min(w, x2)
        rx2 = min(w, x2 + right_band_px)
        if rx2 <= rx1:
            continue
        right_band = gray[y1:y2, rx1:rx2]
        right_dark_ratio = float(np.mean(right_band < dark_threshold))
        if right_dark_ratio > right_dark_ratio_max:
            continue

        if dark_ratio > best_ratio:
            best_ratio = dark_ratio
            best = (x1, y1, x2, y2)

    return best


def recover_end_barlines(
    image_path: Path,
    detections: Sequence[BarlinePrediction],
    staff_mask: Optional[np.ndarray] = None,
    sr_scale: float = 1.0,
) -> List[BarlinePrediction]:
    if len(detections) < 3:
        return []

    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return []

    if staff_mask is not None:
        staff_mask = _ensure_mask_shape(staff_mask, gray.shape[:2])

    heights = [max(1, pred.orig_bbox[3] - pred.orig_bbox[1]) for pred in detections]
    median_height = float(np.median(heights)) if heights else 20.0
    row_cluster_px = max(18, int(round(median_height * 1.4)))
    min_height_px = max(14, int(round(median_height * 0.8)))

    x_ref_global: Optional[float] = None
    if staff_mask is None:
        centers_x = [(pred.orig_bbox[0] + pred.orig_bbox[2]) / 2.0 for pred in detections]
        max_center_x = max(centers_x)

        x_bin_width = int(8 * sr_scale)
        min_bin_count = 2
        max_x_gap_px = int(40 * sr_scale)
        bins: Dict[int, int] = {}
        for cx in centers_x:
            key = int(round(cx / x_bin_width))
            bins[key] = bins.get(key, 0) + 1

        candidate_bins = [
            (key, count)
            for key, count in bins.items()
            if count >= min_bin_count and (key * x_bin_width) >= (max_center_x - max_x_gap_px)
        ]
        if not candidate_bins:
            return []

        rightmost_key = max(candidate_bins, key=lambda item: item[0])[0]
        x_ref_global = rightmost_key * x_bin_width
        if x_ref_global < gray.shape[1] * 0.7:
            return []

    staff_groups: Dict[int, List[int]] = {}
    for idx, pred in enumerate(detections):
        if pred.staff_index >= 0:
            staff_groups.setdefault(pred.staff_index, []).append(idx)

    row_groups: List[List[int]]
    if staff_groups:
        row_groups = [group for group in staff_groups.values() if len(group) >= 2]
    else:
        y_centers = [(pred.orig_bbox[1] + pred.orig_bbox[3]) / 2.0 for pred in detections]
        row_groups = _cluster_by_y_centers(y_centers, row_cluster_px)

    added: List[BarlinePrediction] = []
    search_half_width = max(8, int(round(median_height * 0.45)))
    x_tolerance_px = max(6, int(round(median_height * 0.25)))

    for group in row_groups:
        cluster_boxes = [detections[i].orig_bbox for i in group]
        y_top = min(box[1] for box in cluster_boxes)
        y_bottom = max(box[3] for box in cluster_boxes)
        if (y_bottom - y_top) < min_height_px:
            continue

        if staff_mask is not None:
            y1 = max(0, min(staff_mask.shape[0] - 1, y_top))
            y2 = max(0, min(staff_mask.shape[0], y_bottom))
            if y2 <= y1:
                continue
            row_mask = staff_mask[y1:y2]
            cols = np.where(row_mask.any(axis=0))[0]
            if cols.size == 0:
                continue
            x_ref = float(np.percentile(cols, 98))
        else:
            if x_ref_global is None:
                continue
            x_ref = x_ref_global

        if x_ref < gray.shape[1] * 0.7:
            continue

        if any(abs(((box[0] + box[2]) / 2.0) - x_ref) <= (x_tolerance_px) for box in cluster_boxes):
            continue

        candidate = _scan_vertical_line(
            gray,
            y_top,
            y_bottom,
            x_ref,
            search_half_width=search_half_width,
            dark_threshold=120,
            min_dark_ratio=0.5,
            right_band_px=int(4 * sr_scale),
            right_dark_ratio_max=0.25,
            line_width=int(2 * sr_scale),
        )
        if not candidate:
            continue

        added.append(
            BarlinePrediction(
                pred_bbox=candidate,
                orig_bbox=candidate,
                system_index=-3,
                staff_index=-1,
            )
        )

    if added:
        eprint(f"End barline recovery added {len(added)} candidates")
    return added
