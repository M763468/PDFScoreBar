#!/usr/bin/env python3
"""
Re-evaluate hybrid (homr + omr-dln union) with row + geom notehead filter
against rebuilt GT. Produces metrics + overlays with TP/FP/FN.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import cv2
import numpy as np
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import greedy_barline_match

Box = Tuple[int, int, int, int]
Color = Tuple[int, int, int]

TP_COLOR: Color = (0, 255, 0)
FP_COLOR: Color = (0, 0, 255)
FN_COLOR: Color = (255, 0, 255)


@dataclass
class PageSpec:
    name: str
    image: Path
    gt: Path
    notehead_mask: Path
    clefs_keys_mask: Path
    staff_mask: Path
    staff_mask_alt: Path
    barline_mask: Path
    omr_preds: Path
    union_preds: Path


def load_preds(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    raw = data["predictions"] if isinstance(data, dict) and "predictions" in data else data
    preds: List[Box] = []
    for item in raw:
        if isinstance(item, list):
            preds.append(tuple(map(int, item)))
        elif isinstance(item, dict):
            bbox = item.get("orig_bbox", item.get("bbox", item.get("pred_bbox")))
            if bbox:
                preds.append(tuple(map(int, bbox)))
    return preds


def load_omr_preds(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return [tuple(map(int, item)) for item in data if isinstance(item, list) and len(item) == 4]
    return []


def load_gt(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, list) and data and "barline_location" in data[0]:
        return [tuple(map(int, x["barline_location"])) for x in data]
    return [tuple(map(int, x)) for x in data]


def cluster_by_y_distance(y_centers: np.ndarray, max_distance: float, min_cluster_size: int):
    sorted_indices = np.argsort(y_centers)
    sorted_y = y_centers[sorted_indices]
    clusters: List[List[int]] = []
    current_cluster = [int(sorted_indices[0])]
    for i in range(1, len(sorted_y)):
        if sorted_y[i] - sorted_y[i - 1] <= max_distance:
            current_cluster.append(int(sorted_indices[i]))
        else:
            clusters.append(current_cluster)
            current_cluster = [int(sorted_indices[i])]
    clusters.append(current_cluster)

    valid_clusters: Dict[int, List[int]] = {}
    noise: List[int] = []
    cluster_id = 0
    for cluster in clusters:
        if len(cluster) >= min_cluster_size:
            valid_clusters[cluster_id] = cluster
            cluster_id += 1
        else:
            noise.extend(cluster)
    return valid_clusters, noise


def estimate_staff_space(rows: Dict[int, List[int]], preds_list: Sequence[Box]) -> float:
    if len(rows) < 2:
        return 20.0
    row_medians = []
    for row_id in sorted(rows.keys()):
        indices = rows[row_id]
        y_centers = [(preds_list[i][1] + preds_list[i][3]) / 2 for i in indices]
        row_medians.append(float(np.median(y_centers)))
    gaps = [row_medians[i + 1] - row_medians[i] for i in range(len(row_medians) - 1)]
    median_gap = float(np.median(gaps)) if gaps else 100.0
    return median_gap / 5.0


def row_filter(
    preds: Sequence[Box],
    cluster_max_dist: float,
    min_row_count: int,
    tol_top: float,
    tol_bottom: float,
) -> List[Box]:
    y_centers = np.array([(box[1] + box[3]) / 2 for box in preds])
    rows, _ = cluster_by_y_distance(y_centers, cluster_max_dist, min_row_count)
    accepted_indices = set()
    for _, indices in rows.items():
        if len(indices) < min_row_count:
            continue
        tops = [preds[i][1] for i in indices]
        bottoms = [preds[i][3] for i in indices]
        ref_top = float(np.median(tops))
        ref_bottom = float(np.median(bottoms))
        for i in indices:
            x1, y1, x2, y2 = map(int, preds[i])
            if abs(y1 - ref_top) <= tol_top and abs(y2 - ref_bottom) <= tol_bottom:
                accepted_indices.add(i)
    return [preds[i] for i in sorted(accepted_indices)]


def build_row_stats(
    preds: Sequence[Box],
    cluster_max_dist: float,
    min_row_count: int,
) -> List[Dict[str, float]]:
    if not preds:
        return []
    y_centers = np.array([(box[1] + box[3]) / 2 for box in preds])
    rows, _ = cluster_by_y_distance(y_centers, cluster_max_dist, min_row_count)
    stats: List[Dict[str, float]] = []
    for indices in rows.values():
        if len(indices) < min_row_count:
            continue
        tops = [preds[i][1] for i in indices]
        bottoms = [preds[i][3] for i in indices]
        centers = [y_centers[i] for i in indices]
        stats.append(
            {
                "center": float(np.median(centers)),
                "top": float(np.median(tops)),
                "bottom": float(np.median(bottoms)),
            }
        )
    return stats


def row_filter_with_stats(
    preds: Sequence[Box],
    row_stats: Sequence[Dict[str, float]],
    max_dist: float,
    tol_top: float,
    tol_bottom: float,
) -> List[Box]:
    if not preds or not row_stats:
        return []
    accepted: List[Box] = []
    for box in preds:
        _, y1, _, y2 = box
        cy = (y1 + y2) / 2.0
        closest = min(row_stats, key=lambda row: abs(row["center"] - cy))
        if abs(closest["center"] - cy) > max_dist:
            continue
        if abs(y1 - closest["top"]) <= tol_top and abs(y2 - closest["bottom"]) <= tol_bottom:
            accepted.append(box)
    return accepted


def load_notehead_mask(path: Path, target_hw: Tuple[int, int]) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Failed to load notehead mask: {path}")
    _, bin_mask = cv2.threshold(img, 1, 255, cv2.THRESH_BINARY)
    if bin_mask.shape[:2] != target_hw:
        h, w = target_hw
        bin_mask = cv2.resize(bin_mask, (w, h), interpolation=cv2.INTER_NEAREST)
    return bin_mask


def denoise_notehead_mask(
    mask: np.ndarray,
    open_kernel: int,
    min_area: int,
) -> np.ndarray:
    """Remove small speckles from notehead mask without erasing true noteheads."""
    cleaned = (mask > 0).astype(np.uint8)
    if open_kernel and open_kernel > 1:
        kernel = np.ones((open_kernel, open_kernel), np.uint8)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)
    if min_area and min_area > 0:
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            cleaned, connectivity=8
        )
        filtered = np.zeros_like(cleaned)
        for label in range(1, num_labels):
            if stats[label, cv2.CC_STAT_AREA] >= min_area:
                filtered[labels == label] = 1
        cleaned = filtered
    return (cleaned * 255).astype(np.uint8)


def filter_notehead_components(
    mask: np.ndarray,
    max_aspect_ratio: float,
    min_height_px: int,
    max_width_px: int,
) -> np.ndarray:
    """Remove tall, thin components that are likely barlines or stems."""
    if max_aspect_ratio <= 0:
        return mask
    binary = (mask > 0).astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    filtered = np.zeros_like(binary)
    for label in range(1, num_labels):
        x, y, w, h, area = stats[label]
        if min_height_px and h < min_height_px:
            filtered[labels == label] = 1
            continue
        if max_width_px and w > max_width_px:
            filtered[labels == label] = 1
            continue
        aspect = h / max(w, 1)
        if aspect <= max_aspect_ratio:
            filtered[labels == label] = 1
    return (filtered * 255).astype(np.uint8)


def filter_clefs_keys_overlap(
    preds: Sequence[Box],
    clefs_keys_mask: np.ndarray,
    left_margin_ratio: float,
    min_overlap_ratio: float,
    right_margin_ratio: float,
    min_overlap_ratio_right: float,
) -> Tuple[List[Box], Dict[str, object]]:
    h, w = clefs_keys_mask.shape[:2]
    kept: List[Box] = []
    rejected: List[Dict[str, object]] = []
    left_limit = int(round(w * left_margin_ratio))
    right_limit = int(round(w * right_margin_ratio)) if right_margin_ratio > 0 else None
    for idx, box in enumerate(preds):
        x1, y1, x2, y2 = map(int, box)
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w - 1, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h - 1, y2))
        xm = (x1 + x2) // 2
        if xm > left_limit and (right_limit is None or xm < right_limit):
            kept.append((x1, y1, x2, y2))
            continue
        region = clefs_keys_mask[y1 : y2 + 1, x1 : x2 + 1]
        overlap = 0.0
        if region.size:
            overlap = float(np.count_nonzero(region)) / float(region.size)
        threshold = min_overlap_ratio
        if right_limit is not None and xm >= right_limit:
            threshold = min_overlap_ratio_right
        if overlap >= threshold:
            rejected.append(
                {
                    "index": idx,
                    "bbox": [x1, y1, x2, y2],
                    "overlap_ratio": overlap,
                    "threshold": threshold,
                }
            )
            continue
        kept.append((x1, y1, x2, y2))
    debug = {
        "left_margin_ratio": left_margin_ratio,
        "left_margin_px": left_limit,
        "min_overlap_ratio": min_overlap_ratio,
        "right_margin_ratio": right_margin_ratio,
        "right_margin_px": right_limit,
        "min_overlap_ratio_right": min_overlap_ratio_right,
        "rejected": rejected,
    }
    return kept, debug


def filter_barline_clefs_low(
    preds: Sequence[Box],
    barline_mask: np.ndarray,
    clefs_mask: np.ndarray,
    barline_ratio_max: float,
    clefs_ratio_max: float,
) -> Tuple[List[Box], Dict[str, object]]:
    kept: List[Box] = []
    rejected: List[Dict[str, object]] = []
    for idx, box in enumerate(preds):
        x1, y1, x2, y2 = map(int, box)
        barline_region = barline_mask[y1 : y2 + 1, x1 : x2 + 1]
        clefs_region = clefs_mask[y1 : y2 + 1, x1 : x2 + 1]
        barline_ratio = float(barline_region.mean()) if barline_region.size else 0.0
        clefs_ratio = float(clefs_region.mean()) if clefs_region.size else 0.0
        if barline_ratio < barline_ratio_max and clefs_ratio < clefs_ratio_max:
            rejected.append(
                {
                    "index": idx,
                    "bbox": [x1, y1, x2, y2],
                    "barline_ratio": barline_ratio,
                    "clefs_ratio": clefs_ratio,
                }
            )
            continue
        kept.append((x1, y1, x2, y2))
    debug = {
        "barline_ratio_max": barline_ratio_max,
        "clefs_ratio_max": clefs_ratio_max,
        "rejected": rejected,
    }
    return kept, debug


def filter_min_height_ratio(
    preds: Sequence[Box],
    staff_mask: np.ndarray,
    min_height_ratio: float,
) -> Tuple[List[Box], Dict[str, object]]:
    if min_height_ratio <= 0:
        return list(preds), {"min_height_ratio": min_height_ratio, "rejected": []}
    bands = staff_bands_from_mask(staff_mask)
    band_heights = [abs(y2 - y1) + 1 for y1, y2 in bands] if bands else []
    fallback_height = int(np.median(band_heights)) if band_heights else 0
    kept: List[Box] = []
    rejected: List[Dict[str, object]] = []
    for idx, box in enumerate(preds):
        x1, y1, x2, y2 = map(int, box)
        yc = (y1 + y2) // 2
        band_h = fallback_height
        for by1, by2 in bands:
            if by1 <= yc <= by2:
                band_h = abs(by2 - by1) + 1
                break
        min_h = int(round(band_h * min_height_ratio)) if band_h else 0
        height = abs(y2 - y1) + 1
        if min_h and height < min_h:
            rejected.append(
                {
                    "index": idx,
                    "bbox": [x1, y1, x2, y2],
                    "height": height,
                    "band_height": band_h,
                    "min_height": min_h,
                }
            )
            continue
        kept.append((x1, y1, x2, y2))
    debug = {
        "min_height_ratio": min_height_ratio,
        "fallback_height": fallback_height,
        "band_count": len(bands),
        "rejected": rejected,
    }
    return kept, debug


def filter_stem_outside_staff(
    preds: Sequence[Box],
    staff_mask: np.ndarray,
    max_height_ratio: float,
    min_band_cover: float,
) -> Tuple[List[Box], Dict[str, object]]:
    if max_height_ratio <= 0:
        return list(preds), {"max_height_ratio": max_height_ratio, "rejected": []}
    bands = staff_bands_from_mask(staff_mask)
    band_heights = [abs(y2 - y1) + 1 for y1, y2 in bands] if bands else []
    fallback_height = int(np.median(band_heights)) if band_heights else 0
    kept: List[Box] = []
    rejected: List[Dict[str, object]] = []
    for idx, box in enumerate(preds):
        x1, y1, x2, y2 = map(int, box)
        yc = (y1 + y2) // 2
        band_y1, band_y2 = None, None
        band_h = fallback_height
        for by1, by2 in bands:
            if by1 <= yc <= by2:
                band_y1, band_y2 = by1, by2
                band_h = abs(by2 - by1) + 1
                break
        if band_y1 is None and bands:
            band_y1, band_y2 = bands[0]
            band_h = abs(band_y2 - band_y1) + 1
        height = abs(y2 - y1) + 1
        max_h = int(round(band_h * max_height_ratio)) if band_h else 0
        cover = 1.0
        if band_y1 is not None and band_y2 is not None and height > 0:
            inter = max(0, min(y2, band_y2) - max(y1, band_y1) + 1)
            cover = inter / float(height)
        if max_h and height > max_h and cover < min_band_cover:
            rejected.append(
                {
                    "index": idx,
                    "bbox": [x1, y1, x2, y2],
                    "height": height,
                    "band_height": band_h,
                    "max_height": max_h,
                    "band_cover": cover,
                }
            )
            continue
        kept.append((x1, y1, x2, y2))
    debug = {
        "max_height_ratio": max_height_ratio,
        "min_band_cover": min_band_cover,
        "fallback_height": fallback_height,
        "band_count": len(bands),
        "rejected": rejected,
    }
    return kept, debug


def load_staff_mask(path: Path, target_hw: Tuple[int, int]) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Failed to load staff mask: {path}")
    _, bin_mask = cv2.threshold(img, 1, 255, cv2.THRESH_BINARY)
    if bin_mask.shape[:2] != target_hw:
        h, w = target_hw
        bin_mask = cv2.resize(bin_mask, (w, h), interpolation=cv2.INTER_NEAREST)
    return bin_mask


def load_barline_mask(path: Path, target_hw: Tuple[int, int]) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Failed to load barline mask: {path}")
    _, bin_mask = cv2.threshold(img, 1, 255, cv2.THRESH_BINARY)
    if bin_mask.shape[:2] != target_hw:
        h, w = target_hw
        bin_mask = cv2.resize(bin_mask, (w, h), interpolation=cv2.INTER_NEAREST)
    return bin_mask


def load_clefs_keys_mask(path: Path, target_hw: Tuple[int, int]) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Failed to load clefs_keys mask: {path}")
    _, bin_mask = cv2.threshold(img, 1, 255, cv2.THRESH_BINARY)
    if bin_mask.shape[:2] != target_hw:
        h, w = target_hw
        bin_mask = cv2.resize(bin_mask, (w, h), interpolation=cv2.INTER_NEAREST)
    return bin_mask


def refine_clefs_keys_mask(
    mask: np.ndarray,
    open_kernel: int,
    min_area: int,
    max_aspect_ratio: float,
    min_height_px: int,
    max_width_px: int,
) -> np.ndarray:
    cleaned = (mask > 0).astype(np.uint8)
    if open_kernel and open_kernel > 1:
        kernel = np.ones((open_kernel, open_kernel), np.uint8)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)
    if min_area and min_area > 0:
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            cleaned, connectivity=8
        )
        filtered = np.zeros_like(cleaned)
        for label in range(1, num_labels):
            if stats[label, cv2.CC_STAT_AREA] >= min_area:
                filtered[labels == label] = 1
        cleaned = filtered
    if max_aspect_ratio and max_aspect_ratio > 0:
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            cleaned, connectivity=8
        )
        filtered = np.zeros_like(cleaned)
        for label in range(1, num_labels):
            x, y, w, h, area = stats[label]
            if min_height_px and h < min_height_px:
                filtered[labels == label] = 1
                continue
            if max_width_px and w > max_width_px:
                filtered[labels == label] = 1
                continue
            aspect = h / max(w, 1)
            if aspect <= max_aspect_ratio:
                filtered[labels == label] = 1
        cleaned = filtered
    return (cleaned * 255).astype(np.uint8)


def staff_bands_from_mask(mask: np.ndarray) -> List[Tuple[int, int]]:
    rows = np.where(mask.sum(axis=1) > 0)[0]
    if rows.size == 0:
        return []
    bands: List[Tuple[int, int]] = []
    start = rows[0]
    prev = rows[0]
    for y in rows[1:]:
        if y == prev + 1:
            prev = y
            continue
        bands.append((int(start), int(prev)))
        start = y
        prev = y
    bands.append((int(start), int(prev)))
    return bands


def detect_end_barlines(
    base_img: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    search_width: int = 40,
    min_height_ratio: float = 0.6,
    right_clear_width: int = 10,
    right_clear_ratio: float = 0.08,
    x_merge_tol: int = 4,
    debug_path: Path | None = None,
) -> List[Box]:
    gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = (ink > 0).astype(np.uint8)

    h, w = ink.shape[:2]
    bands = staff_bands_from_mask(staff_mask)
    if not bands:
        return []

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                return True
        return False

    candidates: List[Box] = []
    debug_records = []
    x_start = max(0, w - search_width)
    for y1, y2 in bands:
        band_h = max(1, y2 - y1 + 1)
        band_ink = ink[y1 : y2 + 1, x_start:w]
        col_sums = band_ink.sum(axis=0)
        min_ink = int(round(band_h * min_height_ratio))
        valid_cols = np.where(col_sums >= min_ink)[0]
        if valid_cols.size == 0:
            debug_records.append(
                {
                    "band": [y1, y2],
                    "status": "no_valid_cols",
                    "min_ink": min_ink,
                }
            )
            continue
        col = int(valid_cols[-1]) + x_start
        x_center = float(col)
        if has_existing(x_center, y1, y2):
            debug_records.append(
                {
                    "band": [y1, y2],
                    "status": "existing",
                    "col": col,
                    "min_ink": min_ink,
                }
            )
            continue
        right_x1 = min(w, col + 2)
        right_x2 = min(w, col + 2 + right_clear_width)
        if right_x1 < right_x2:
            right_window = ink[y1 : y2 + 1, right_x1:right_x2]
            right_ratio = float(right_window.mean()) if right_window.size else 0.0
            if right_ratio > right_clear_ratio:
                debug_records.append(
                    {
                        "band": [y1, y2],
                        "status": "right_blocked",
                        "col": col,
                        "right_ratio": right_ratio,
                    }
                )
                continue
        debug_records.append(
            {
                "band": [y1, y2],
                "status": "accepted",
                "col": col,
            }
        )
        candidates.append((max(0, col - 1), y1, min(w - 1, col + 1), y2))

    if debug_path is not None:
        overlay = base_img.copy()
        mask_overlay = overlay.copy()
        # Staff bands (cyan)
        for y1, y2 in bands:
            cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
        overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
        # Right search window (yellow)
        cv2.rectangle(overlay, (x_start, 0), (w - 1, h - 1), (0, 255, 255), 1)
        # Candidate columns
        for rec in debug_records:
            col = rec.get("col")
            if col is None:
                continue
            color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
            cv2.line(overlay, (col, 0), (col, h - 1), color, 1)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), overlay)
        debug_json = debug_path.with_suffix(".json")
        debug_json.write_text(
            json.dumps(
                {
                    "params": {
                        "search_width": search_width,
                        "min_height_ratio": min_height_ratio,
                        "right_clear_width": right_clear_width,
                        "right_clear_ratio": right_clear_ratio,
                        "x_merge_tol": x_merge_tol,
                    },
                    "bands": bands,
                    "records": debug_records,
                },
                indent=2,
            )
        )
    return candidates


def detect_end_barlines_from_mask(
    mask: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    search_width: int = 40,
    min_height_ratio: float = 0.6,
    x_merge_tol: int = 4,
    debug_path: Path | None = None,
) -> List[Box]:
    h, w = mask.shape[:2]
    bands = staff_bands_from_mask(staff_mask)
    if not bands:
        return []

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                return True
        return False

    candidates: List[Box] = []
    debug_records = []
    x_start = max(0, w - search_width)
    for y1, y2 in bands:
        band_h = max(1, y2 - y1 + 1)
        band = (mask[y1 : y2 + 1, x_start:w] > 0).astype(np.uint8)
        col_sums = band.sum(axis=0)
        min_ink = int(round(band_h * min_height_ratio))
        valid_cols = np.where(col_sums >= min_ink)[0]
        if valid_cols.size == 0:
            debug_records.append({"band": [y1, y2], "status": "no_valid_cols", "min_ink": min_ink})
            continue
        col = int(valid_cols[-1]) + x_start
        x_center = float(col)
        if has_existing(x_center, y1, y2):
            debug_records.append({"band": [y1, y2], "status": "existing", "col": col})
            continue
        candidates.append((max(0, col - 1), y1, min(w - 1, col + 1), y2))
        debug_records.append({"band": [y1, y2], "status": "accepted", "col": col})

    if debug_path is not None:
        overlay = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        mask_overlay = overlay.copy()
        for y1, y2 in bands:
            cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
        overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
        cv2.rectangle(overlay, (x_start, 0), (w - 1, h - 1), (0, 255, 255), 1)
        for rec in debug_records:
            col = rec.get("col")
            if col is None:
                continue
            color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
            cv2.line(overlay, (col, 0), (col, h - 1), color, 1)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), overlay)
        debug_json = debug_path.with_suffix(".json")
        debug_json.write_text(
            json.dumps(
                {
                    "params": {
                        "method": "barline_mask",
                        "search_width": search_width,
                        "min_height_ratio": min_height_ratio,
                        "x_merge_tol": x_merge_tol,
                    },
                    "bands": bands,
                    "records": debug_records,
                },
                indent=2,
            )
        )
    return candidates


def detect_end_barlines_morph(
    base_img: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    search_width: int = 40,
    min_height_ratio: float = 0.6,
    morph_kernel_scale: float = 0.6,
    constrain_height: bool = False,
    x_merge_tol: int = 4,
    debug_path: Path | None = None,
) -> List[Box]:
    gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = (ink > 0).astype(np.uint8)

    h, w = ink.shape[:2]
    bands = staff_bands_from_mask(staff_mask)
    if not bands:
        return []

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                return True
        return False

    candidates: List[Box] = []
    debug_records = []
    x_start = max(0, w - search_width)
    for y1, y2 in bands:
        band_h = max(1, y2 - y1 + 1)
        band = ink[y1 : y2 + 1, x_start:w]
        k_h = max(3, int(round(band_h * morph_kernel_scale)))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, k_h))
        closed = cv2.morphologyEx(band, cv2.MORPH_CLOSE, kernel)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
        for idx in range(1, num_labels):
            x, y, bw, bh, area = stats[idx]
            if bh < int(round(band_h * min_height_ratio)):
                continue
            if constrain_height and bh > band_h:
                debug_records.append({"band": [y1, y2], "status": "too_tall", "bbox": [x, y, bw, bh]})
                continue
            col = x + bw // 2 + x_start
            x_center = float(col)
            if has_existing(x_center, y1, y2):
                debug_records.append({"band": [y1, y2], "status": "existing", "col": col})
                continue
            candidates.append((max(0, col - 1), y1, min(w - 1, col + 1), y2))
            debug_records.append({"band": [y1, y2], "status": "accepted", "col": col, "bbox": [x, y, bw, bh]})

    if debug_path is not None:
        overlay = base_img.copy()
        mask_overlay = overlay.copy()
        for y1, y2 in bands:
            cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
        overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
        cv2.rectangle(overlay, (x_start, 0), (w - 1, h - 1), (0, 255, 255), 1)
        for rec in debug_records:
            col = rec.get("col")
            if col is None:
                continue
            color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
            cv2.line(overlay, (col, 0), (col, h - 1), color, 1)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), overlay)
        debug_json = debug_path.with_suffix(".json")
        debug_json.write_text(
            json.dumps(
                {
                    "params": {
                        "method": "morph",
                        "search_width": search_width,
                        "min_height_ratio": min_height_ratio,
                        "morph_kernel_scale": morph_kernel_scale,
                        "constrain_height": constrain_height,
                        "x_merge_tol": x_merge_tol,
                    },
                    "bands": bands,
                    "records": debug_records,
                },
                indent=2,
            )
        )
    return candidates


def detect_end_barlines_hough(
    base_img: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    search_width: int = 40,
    min_height_ratio: float = 0.6,
    constrain_height: bool = False,
    canny1: int = 50,
    canny2: int = 150,
    hough_threshold: int = 30,
    min_line_ratio: float = 0.6,
    max_line_gap: int = 6,
    x_merge_tol: int = 4,
    debug_path: Path | None = None,
) -> List[Box]:
    gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, canny1, canny2)

    h, w = edges.shape[:2]
    bands = staff_bands_from_mask(staff_mask)
    if not bands:
        return []

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                return True
        return False

    candidates: List[Box] = []
    debug_records = []
    x_start = max(0, w - search_width)

    for y1, y2 in bands:
        band_h = max(1, y2 - y1 + 1)
        roi = edges[y1 : y2 + 1, x_start:w]
        min_line_len = int(round(band_h * min_line_ratio))
        lines = cv2.HoughLinesP(
            roi,
            rho=1,
            theta=np.pi / 180,
            threshold=hough_threshold,
            minLineLength=min_line_len,
            maxLineGap=max_line_gap,
        )
        if lines is None:
            debug_records.append({"band": [y1, y2], "status": "no_lines"})
            continue
        for line in lines[:, 0]:
            x1, y1l, x2, y2l = map(int, line.tolist())
            dx = abs(x2 - x1)
            dy = abs(y2l - y1l)
            if dy < int(round(band_h * min_height_ratio)):
                continue
            if dx > 2:
                continue
            if constrain_height and dy > band_h:
                debug_records.append({"band": [y1, y2], "status": "too_tall", "line": line.tolist()})
                continue
            col = x1 + x_start
            x_center = float(col)
            if has_existing(x_center, y1, y2):
                debug_records.append({"band": [y1, y2], "status": "existing", "col": col})
                continue
            candidates.append((max(0, col - 1), y1, min(w - 1, col + 1), y2))
            debug_records.append({"band": [y1, y2], "status": "accepted", "col": col, "line": line.tolist()})

    if debug_path is not None:
        overlay = base_img.copy()
        mask_overlay = overlay.copy()
        for y1, y2 in bands:
            cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
        overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
        cv2.rectangle(overlay, (x_start, 0), (w - 1, h - 1), (0, 255, 255), 1)
        for rec in debug_records:
            col = rec.get("col")
            if col is None:
                continue
            color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
            cv2.line(overlay, (col, 0), (col, h - 1), color, 1)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), overlay)
        debug_json = debug_path.with_suffix(".json")
        debug_json.write_text(
            json.dumps(
                {
                    "params": {
                        "method": "hough",
                        "search_width": search_width,
                        "min_height_ratio": min_height_ratio,
                        "constrain_height": constrain_height,
                        "canny1": canny1,
                        "canny2": canny2,
                        "hough_threshold": hough_threshold,
                        "min_line_ratio": min_line_ratio,
                        "max_line_gap": max_line_gap,
                    },
                    "bands": bands,
                    "records": debug_records,
                },
                indent=2,
            )
        )
    return candidates


def detect_end_barlines_runlen(
    base_img: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    search_width: int = 40,
    min_height_ratio: float = 0.6,
    constrain_height: bool = False,
    x_merge_tol: int = 4,
    debug_path: Path | None = None,
) -> List[Box]:
    gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = (ink > 0).astype(np.uint8)

    h, w = ink.shape[:2]
    bands = staff_bands_from_mask(staff_mask)
    if not bands:
        return []

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                return True
        return False

    candidates: List[Box] = []
    debug_records = []
    x_start = max(0, w - search_width)

    for y1, y2 in bands:
        band_h = max(1, y2 - y1 + 1)
        min_len = int(round(band_h * min_height_ratio))
        band = ink[y1 : y2 + 1, x_start:w]
        for col_idx in range(band.shape[1]):
            col = band[:, col_idx]
            # compute max run length of 1s
            max_run = 0
            run = 0
            for v in col:
                if v:
                    run += 1
                    if run > max_run:
                        max_run = run
                else:
                    run = 0
            if max_run < min_len:
                continue
            if constrain_height and max_run > band_h:
                debug_records.append({"band": [y1, y2], "status": "too_tall", "col": col_idx})
                continue
            x_abs = x_start + col_idx
            if has_existing(float(x_abs), y1, y2):
                debug_records.append({"band": [y1, y2], "status": "existing", "col": x_abs})
                continue
            candidates.append((max(0, x_abs - 1), y1, min(w - 1, x_abs + 1), y2))
            debug_records.append({"band": [y1, y2], "status": "accepted", "col": x_abs, "max_run": max_run})

    if debug_path is not None:
        overlay = base_img.copy()
        mask_overlay = overlay.copy()
        for y1, y2 in bands:
            cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
        overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
        cv2.rectangle(overlay, (x_start, 0), (w - 1, h - 1), (0, 255, 255), 1)
        for rec in debug_records:
            col = rec.get("col")
            if col is None:
                continue
            color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
            cv2.line(overlay, (col, 0), (col, h - 1), color, 1)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), overlay)
        debug_json = debug_path.with_suffix(".json")
        debug_json.write_text(
            json.dumps(
                {
                    "params": {
                        "method": "runlen",
                        "search_width": search_width,
                        "min_height_ratio": min_height_ratio,
                        "constrain_height": constrain_height,
                        "x_merge_tol": x_merge_tol,
                    },
                    "bands": bands,
                    "records": debug_records,
                },
                indent=2,
            )
        )
    return candidates


def detect_end_barlines_staff_anchor(
    base_img: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    search_width: int = 40,
    min_height_ratio: float = 0.6,
    anchor_pad: int = 4,
    x_merge_tol: int = 4,
    debug_path: Path | None = None,
) -> List[Box]:
    gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = (ink > 0).astype(np.uint8)

    h, w = ink.shape[:2]
    bands = staff_bands_from_mask(staff_mask)
    if not bands:
        return []

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                return True
        return False

    candidates: List[Box] = []
    debug_records = []
    for y1, y2 in bands:
        band = staff_mask[y1 : y2 + 1, :]
        ys, xs = np.where(band > 0)
        if xs.size == 0:
            debug_records.append({"band": [y1, y2], "status": "no_staff_anchor"})
            continue
        anchor_x = int(xs.max())
        x_start = max(0, anchor_x - search_width)
        x_end = min(w, anchor_x + anchor_pad + 1)
        band_h = max(1, y2 - y1 + 1)
        min_ink = int(round(band_h * min_height_ratio))
        band_ink = ink[y1 : y2 + 1, x_start:x_end]
        col_sums = band_ink.sum(axis=0)
        valid_cols = np.where(col_sums >= min_ink)[0]
        if valid_cols.size == 0:
            debug_records.append(
                {
                    "band": [y1, y2],
                    "status": "no_valid_cols",
                    "anchor_x": anchor_x,
                    "min_ink": min_ink,
                }
            )
            continue
        col = int(valid_cols[-1]) + x_start
        x_center = float(col)
        if has_existing(x_center, y1, y2):
            debug_records.append(
                {"band": [y1, y2], "status": "existing", "col": col, "anchor_x": anchor_x}
            )
            continue
        candidates.append((max(0, col - 1), y1, min(w - 1, col + 1), y2))
        debug_records.append(
            {"band": [y1, y2], "status": "accepted", "col": col, "anchor_x": anchor_x}
        )

    if debug_path is not None:
        overlay = base_img.copy()
        mask_overlay = overlay.copy()
        for y1, y2 in bands:
            cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
        overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
        for rec in debug_records:
            anchor_x = rec.get("anchor_x")
            if anchor_x is not None:
                cv2.line(overlay, (anchor_x, 0), (anchor_x, h - 1), (0, 165, 255), 1)
            col = rec.get("col")
            if col is None:
                continue
            color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
            cv2.line(overlay, (col, 0), (col, h - 1), color, 1)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), overlay)
        debug_json = debug_path.with_suffix(".json")
        debug_json.write_text(
            json.dumps(
                {
                    "params": {
                        "method": "staff_anchor",
                        "search_width": search_width,
                        "min_height_ratio": min_height_ratio,
                        "anchor_pad": anchor_pad,
                        "x_merge_tol": x_merge_tol,
                    },
                    "bands": bands,
                    "records": debug_records,
                },
                indent=2,
            )
        )
    return candidates


def detect_end_barlines_adaptive(
    base_img: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    search_width: int = 40,
    min_height_ratio: float = 0.6,
    adapt_block_size: int = 25,
    adapt_c: int = 5,
    x_merge_tol: int = 4,
    debug_path: Path | None = None,
) -> List[Box]:
    gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    bands = staff_bands_from_mask(staff_mask)
    if not bands:
        return []

    block_size = adapt_block_size if adapt_block_size % 2 == 1 else adapt_block_size + 1
    block_size = max(3, block_size)

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                return True
        return False

    candidates: List[Box] = []
    debug_records = []
    x_start = max(0, w - search_width)
    for y1, y2 in bands:
        band_h = max(1, y2 - y1 + 1)
        min_ink = int(round(band_h * min_height_ratio))
        band_gray = gray[y1 : y2 + 1, x_start:w]
        if band_gray.size == 0:
            continue
        band_bin = cv2.adaptiveThreshold(
            band_gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block_size,
            adapt_c,
        )
        band_ink = (band_bin > 0).astype(np.uint8)
        col_sums = band_ink.sum(axis=0)
        valid_cols = np.where(col_sums >= min_ink)[0]
        if valid_cols.size == 0:
            debug_records.append(
                {"band": [y1, y2], "status": "no_valid_cols", "min_ink": min_ink}
            )
            continue
        col = int(valid_cols[-1]) + x_start
        x_center = float(col)
        if has_existing(x_center, y1, y2):
            debug_records.append({"band": [y1, y2], "status": "existing", "col": col})
            continue
        candidates.append((max(0, col - 1), y1, min(w - 1, col + 1), y2))
        debug_records.append({"band": [y1, y2], "status": "accepted", "col": col})

    if debug_path is not None:
        overlay = base_img.copy()
        mask_overlay = overlay.copy()
        for y1, y2 in bands:
            cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
        overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
        cv2.rectangle(overlay, (x_start, 0), (w - 1, h - 1), (0, 255, 255), 1)
        for rec in debug_records:
            col = rec.get("col")
            if col is None:
                continue
            color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
            cv2.line(overlay, (col, 0), (col, h - 1), color, 1)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), overlay)
        debug_json = debug_path.with_suffix(".json")
        debug_json.write_text(
            json.dumps(
                {
                    "params": {
                        "method": "adaptive",
                        "search_width": search_width,
                        "min_height_ratio": min_height_ratio,
                        "adapt_block_size": block_size,
                        "adapt_c": adapt_c,
                        "x_merge_tol": x_merge_tol,
                    },
                    "bands": bands,
                    "records": debug_records,
                },
                indent=2,
            )
        )
    return candidates


def detect_end_barlines_lsd(
    base_img: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    search_width: int = 40,
    min_height_ratio: float = 0.6,
    vertical_tol: int = 2,
    x_merge_tol: int = 4,
    debug_path: Path | None = None,
) -> List[Box]:
    gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    bands = staff_bands_from_mask(staff_mask)
    if not bands:
        return []

    lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_ADV)

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                return True
        return False

    candidates: List[Box] = []
    debug_records = []
    x_start = max(0, w - search_width)

    for y1, y2 in bands:
        band_h = max(1, y2 - y1 + 1)
        min_len = band_h * min_height_ratio
        band_gray = gray[y1 : y2 + 1, x_start:w]
        lines = lsd.detect(band_gray)[0]
        best_x = None
        if lines is not None:
            for (x1, y1_l, x2, y2_l) in lines.reshape(-1, 4):
                if abs(x1 - x2) > vertical_tol:
                    continue
                length = abs(y2_l - y1_l)
                if length < min_len:
                    continue
                x_mean = (x1 + x2) * 0.5 + x_start
                if best_x is None or x_mean > best_x:
                    best_x = x_mean
        if best_x is None:
            debug_records.append({"band": [y1, y2], "status": "no_vertical"})
            continue
        x_center = float(best_x)
        if has_existing(x_center, y1, y2):
            debug_records.append({"band": [y1, y2], "status": "existing", "col": x_center})
            continue
        col = int(round(best_x))
        candidates.append((max(0, col - 1), y1, min(w - 1, col + 1), y2))
        debug_records.append({"band": [y1, y2], "status": "accepted", "col": col})

    if debug_path is not None:
        overlay = base_img.copy()
        mask_overlay = overlay.copy()
        for y1, y2 in bands:
            cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
        overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
        cv2.rectangle(overlay, (x_start, 0), (w - 1, h - 1), (0, 255, 255), 1)
        for rec in debug_records:
            col = rec.get("col")
            if col is None:
                continue
            color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
            cv2.line(overlay, (int(round(col)), 0), (int(round(col)), h - 1), color, 1)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), overlay)
        debug_json = debug_path.with_suffix(".json")
        debug_json.write_text(
            json.dumps(
                {
                    "params": {
                        "method": "lsd",
                        "search_width": search_width,
                        "min_height_ratio": min_height_ratio,
                        "vertical_tol": vertical_tol,
                        "x_merge_tol": x_merge_tol,
                    },
                    "bands": bands,
                    "records": debug_records,
                },
                indent=2,
            )
        )
    return candidates


def detect_end_barlines_omr(
    base_img: np.ndarray,
    staff_mask: np.ndarray,
    barline_mask: np.ndarray | None,
    omr_preds: Sequence[Box],
    existing_boxes: Sequence[Box],
    *,
    min_height_ratio: float = 0.6,
    x_merge_tol: int = 4,
    debug_path: Path | None = None,
) -> List[Box]:
    gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = (ink > 0).astype(np.uint8)

    h, w = ink.shape[:2]
    bands = staff_bands_from_mask(staff_mask)
    if not bands:
        return []

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                return True
        return False

    candidates: List[Box] = []
    debug_records = []
    for y1, y2 in bands:
        band_h = max(1, y2 - y1 + 1)
        min_ink = int(round(band_h * min_height_ratio))
        xs = []
        for bx1, by1, bx2, by2 in omr_preds:
            cy = (by1 + by2) / 2.0
            if y1 <= cy <= y2:
                xs.append((bx1 + bx2) * 0.5)
        if not xs:
            debug_records.append({"band": [y1, y2], "status": "no_omr"})
            continue
        x_center = float(max(xs))
        col = int(round(x_center))
        if has_existing(x_center, y1, y2):
            debug_records.append({"band": [y1, y2], "status": "existing", "col": col})
            continue
        x1 = max(0, col - 1)
        x2 = min(w, col + 2)
        band_ink = ink[y1 : y2 + 1, x1:x2]
        ink_sum = int(band_ink.sum())
        if ink_sum < min_ink:
            debug_records.append(
                {"band": [y1, y2], "status": "low_ink", "col": col, "ink": ink_sum}
            )
            continue
        if barline_mask is not None:
            band_mask = (barline_mask[y1 : y2 + 1, x1:x2] > 0).astype(np.uint8)
            mask_sum = int(band_mask.sum())
            if mask_sum < min_ink:
                debug_records.append(
                    {"band": [y1, y2], "status": "mask_low", "col": col, "mask": mask_sum}
                )
                continue
        candidates.append((x1, y1, min(w - 1, col + 1), y2))
        debug_records.append({"band": [y1, y2], "status": "accepted", "col": col})

    if debug_path is not None:
        overlay = base_img.copy()
        mask_overlay = overlay.copy()
        for y1, y2 in bands:
            cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
        overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
        for rec in debug_records:
            col = rec.get("col")
            if col is None:
                continue
            color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
            cv2.line(overlay, (int(round(col)), 0), (int(round(col)), h - 1), color, 1)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), overlay)
        debug_json = debug_path.with_suffix(".json")
        debug_json.write_text(
            json.dumps(
                {
                    "params": {
                        "method": "omr",
                        "min_height_ratio": min_height_ratio,
                        "x_merge_tol": x_merge_tol,
                    },
                    "bands": bands,
                    "records": debug_records,
                },
                indent=2,
            )
        )
    return candidates


def detect_probe_scan(
    base_img: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    probe_width: int = 4,
    ink_threshold: int = 180,
    min_ratio: float = 0.85,
    min_peak_distance: int = 6,
    refine_window: int = 4,
    max_per_band: int = 8,
    band_height_mode: str = "staff",
    band_height_scale: float = 1.0,
    band_height_min: int = 10,
    x_merge_tol: int = 4,
    debug_path: Path | None = None,
) -> List[Box]:
    gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
    ink = (gray < ink_threshold).astype(np.uint8)
    h, w = ink.shape[:2]
    bands = staff_bands_from_mask(staff_mask)
    if not bands:
        return []

    width = max(1, int(probe_width))
    kernel = np.ones(width, dtype=np.int32)

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                return True
        return False

    global_heights = [abs(by2 - by1) for _, by1, _, by2 in existing_boxes if abs(by2 - by1) > 0]
    global_height = int(np.median(global_heights)) if global_heights else 0

    candidates: List[Box] = []
    debug_records = []
    for band_idx, (y1, y2) in enumerate(bands):
        band_center = int(round((y1 + y2) / 2))
        band_h = max(1, y2 - y1 + 1)
        if band_height_mode == "median_box":
            heights = [
                abs(by2 - by1)
                for _, by1, _, by2 in existing_boxes
                if y1 <= (by1 + by2) / 2.0 <= y2 and abs(by2 - by1) > 0
            ]
            median_h = int(np.median(heights)) if heights else global_height
            target_h = max(band_height_min, int(round(median_h * band_height_scale))) if median_h else band_h
        else:
            target_h = band_h
        band_y1 = max(0, int(round(band_center - target_h / 2)))
        band_y2 = min(h - 1, int(round(band_center + target_h / 2)))
        band = ink[band_y1 : band_y2 + 1, :]
        band_h = max(1, band_y2 - band_y1 + 1)
        col_sums = band.sum(axis=0)
        stripe_sums = np.convolve(col_sums, kernel, mode="same")
        ratios = stripe_sums / float(band_h * width)
        if ratios.size < 3:
            continue
        peaks = np.where(
            (ratios >= min_ratio)
            & (ratios >= np.roll(ratios, 1))
            & (ratios >= np.roll(ratios, -1))
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
            if has_existing(float(local_idx), y1, y2):
                debug_records.append(
                    {
                        "band": [band_y1, band_y2],
                        "status": "existing",
                        "col": local_idx,
                        "ratio": float(ratios[local_idx]),
                        "seed_col": x,
                    }
                )
                continue
            candidates.append((x1, band_y1, x2, band_y2))
            debug_records.append(
                {
                    "band": [band_y1, band_y2],
                    "status": "accepted",
                    "col": local_idx,
                    "ratio": float(ratios[local_idx]),
                    "seed_col": x,
                }
            )

    if debug_path is not None:
        overlay = base_img.copy()
        mask_overlay = overlay.copy()
        for y1, y2 in bands:
            cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
        overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
        for rec in debug_records:
            col = rec.get("col")
            if col is None:
                continue
            color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
            cv2.line(overlay, (int(col), 0), (int(col), h - 1), color, 1)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), overlay)
        debug_json = debug_path.with_suffix(".json")
        debug_json.write_text(
            json.dumps(
                {
                    "params": {
                        "method": "probe_scan",
                        "probe_width": width,
                        "ink_threshold": ink_threshold,
                        "min_ratio": min_ratio,
                        "min_peak_distance": min_peak_distance,
                        "max_per_band": max_per_band,
                        "x_merge_tol": x_merge_tol,
                    },
                    "bands": bands,
                    "records": debug_records,
                },
                indent=2,
            )
        )
    return candidates


def filter_vertical_run(
    boxes: Sequence[Box],
    gray: np.ndarray,
    *,
    ink_threshold: int,
    min_run_ratio: float,
) -> Tuple[List[Box], Dict[str, object]]:
    if not boxes:
        return [], {"before": 0, "after": 0}
    h, w = gray.shape[:2]
    kept: List[Box] = []
    records = []
    for box in boxes:
        x1, y1, x2, y2 = map(int, box)
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w - 1, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h - 1, y2))
        region = (gray[y1 : y2 + 1, x1 : x2 + 1] < ink_threshold).astype(np.uint8)
        if region.size == 0:
            continue
        max_run = 0
        for col in range(region.shape[1]):
            col_vec = region[:, col]
            run = 0
            for v in col_vec:
                if v:
                    run += 1
                    max_run = max(max_run, run)
                else:
                    run = 0
        height = max(1, y2 - y1 + 1)
        ratio = max_run / float(height)
        records.append({"bbox": [x1, y1, x2, y2], "max_run": max_run, "ratio": ratio})
        if ratio >= min_run_ratio:
            kept.append((x1, y1, x2, y2))
    return kept, {"before": len(boxes), "after": len(kept), "records": records}


def filter_staff_overlap(
    boxes: Sequence[Box],
    staff_mask: np.ndarray,
    *,
    min_ratio: float,
) -> Tuple[List[Box], Dict[str, object]]:
    if not boxes:
        return [], {"before": 0, "after": 0}
    h, w = staff_mask.shape[:2]
    kept: List[Box] = []
    records = []
    for box in boxes:
        x1, y1, x2, y2 = map(int, box)
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w - 1, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h - 1, y2))
        region = staff_mask[y1 : y2 + 1, x1 : x2 + 1]
        ratio = float(region.mean()) if region.size else 0.0
        records.append({"bbox": [x1, y1, x2, y2], "staff_ratio": ratio})
        if ratio >= min_ratio:
            kept.append((x1, y1, x2, y2))
    return kept, {"before": len(boxes), "after": len(kept), "records": records}


def filter_multiband_consensus(
    boxes: Sequence[Box],
    staff_bands: Sequence[Tuple[int, int]],
    *,
    x_tol: int,
    min_bands: int,
) -> Tuple[List[Box], Dict[str, object]]:
    if not boxes:
        return [], {"before": 0, "after": 0}
    centers = [((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0) for b in boxes]
    band_indices = []
    for _, cy in centers:
        band_idx = None
        for i, (y1, y2) in enumerate(staff_bands):
            if y1 <= cy <= y2:
                band_idx = i
                break
        band_indices.append(band_idx)
    kept: List[Box] = []
    records = []
    for idx, (cx, _) in enumerate(centers):
        bands = set()
        for j, (cx2, _) in enumerate(centers):
            if abs(cx2 - cx) <= x_tol:
                if band_indices[j] is not None:
                    bands.add(band_indices[j])
        records.append({"bbox": list(boxes[idx]), "band_count": len(bands)})
        if len(bands) >= min_bands:
            kept.append(boxes[idx])
    return kept, {"before": len(boxes), "after": len(kept), "records": records}


def filter_right_ink(
    boxes: Sequence[Box],
    gray: np.ndarray,
    *,
    ink_threshold: int,
    right_width: int,
    max_ratio: float,
) -> Tuple[List[Box], Dict[str, object]]:
    if not boxes:
        return [], {"before": 0, "after": 0}
    h, w = gray.shape[:2]
    kept: List[Box] = []
    records = []
    for box in boxes:
        x1, y1, x2, y2 = map(int, box)
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w - 1, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h - 1, y2))
        rx1 = min(w - 1, x2 + 1)
        rx2 = min(w - 1, x2 + max(1, right_width))
        region = (gray[y1 : y2 + 1, rx1 : rx2 + 1] < ink_threshold).astype(np.uint8)
        ratio = float(region.mean()) if region.size else 0.0
        records.append({"bbox": [x1, y1, x2, y2], "right_ratio": ratio})
        if ratio <= max_ratio:
            kept.append((x1, y1, x2, y2))
    return kept, {"before": len(boxes), "after": len(kept), "records": records}


def filter_thinness(
    boxes: Sequence[Box],
    gray: np.ndarray,
    *,
    ink_threshold: int,
    max_width_px: int,
) -> Tuple[List[Box], Dict[str, object]]:
    if not boxes:
        return [], {"before": 0, "after": 0}
    h, w = gray.shape[:2]
    kept: List[Box] = []
    records = []
    for box in boxes:
        x1, y1, x2, y2 = map(int, box)
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w - 1, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h - 1, y2))
        region = (gray[y1 : y2 + 1, x1 : x2 + 1] < ink_threshold).astype(np.uint8)
        max_run = 0
        for row in range(region.shape[0]):
            row_vec = region[row]
            run = 0
            row_max = 0
            for v in row_vec:
                if v:
                    run += 1
                    row_max = max(row_max, run)
                else:
                    run = 0
            max_run = max(max_run, row_max)
        records.append({"bbox": [x1, y1, x2, y2], "max_row_width": max_run})
        if max_run <= max_width_px:
            kept.append((x1, y1, x2, y2))
    return kept, {"before": len(boxes), "after": len(kept), "records": records}


def geom_notehead_ratio_filter(
    preds: Sequence[Box],
    notehead_mask: np.ndarray,
    staff_space_px: float,
    threshold: float,
    endpoint_x_scale: float,
    endpoint_y_scale: float,
):
    h, w = notehead_mask.shape[:2]
    kept: List[Box] = []
    rejected: List[Dict[str, object]] = []
    scores: List[Dict[str, object]] = []

    rx = max(1, int(round(staff_space_px * endpoint_x_scale)))
    ry = max(2, int(round(staff_space_px * endpoint_y_scale)))

    for i, box in enumerate(preds):
        x1, y1, x2, y2 = map(int, box)
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w - 1, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h - 1, y2))

        xm = (x1 + x2) // 2

        tx1, tx2 = max(0, xm - rx), min(w, xm + rx + 1)
        ty1, ty2 = max(0, y1 - ry), min(h, y1 + ry + 1)
        bx1, bx2 = max(0, xm - rx), min(w, xm + rx + 1)
        by1, by2 = max(0, y2 - ry), min(h, y2 + ry + 1)

        top_region = notehead_mask[ty1:ty2, tx1:tx2]
        bot_region = notehead_mask[by1:by2, bx1:bx2]

        notehead_pixels_top = int(np.count_nonzero(top_region))
        notehead_pixels_bottom = int(np.count_nonzero(bot_region))
        total_area = int(top_region.size + bot_region.size)
        total_notehead = notehead_pixels_top + notehead_pixels_bottom
        overlap_ratio = 0.0 if total_area == 0 else total_notehead / total_area

        scores.append(
            {
                "index": i,
                "bbox": [x1, y1, x2, y2],
                "endpoint_overlap_ratio": float(overlap_ratio),
                "endpoint_radius_px": {"x": int(rx), "y": int(ry)},
            }
        )

        if overlap_ratio > threshold:
            rejected.append(
                {
                    "index": i,
                    "bbox": [x1, y1, x2, y2],
                    "reason": "endpoint_ratio_overlap",
                    "overlap_ratio": float(overlap_ratio),
                    "threshold": threshold,
                }
            )
            continue
        kept.append((x1, y1, x2, y2))

    debug = {
        "config": {
            "mode": "endpoint_ratio_overlap",
            "threshold": threshold,
            "endpoint_x_radius_scale": endpoint_x_scale,
            "endpoint_y_radius_scale": endpoint_y_scale,
            "endpoint_radius_px": {"x": int(rx), "y": int(ry)},
        },
        "scores": scores,
        "rejected": rejected,
    }
    return kept, debug


def dilate_mask(mask: np.ndarray, kernel_size: int) -> np.ndarray:
    if kernel_size <= 0:
        return mask
    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
    return cv2.dilate(mask, kernel, iterations=1)


def draw_boxes(base: np.ndarray, boxes: Sequence[Box], color: Tuple[int, int, int], thickness: int, label: str):
    for idx, (x1, y1, x2, y2) in enumerate(boxes):
        cv2.rectangle(base, (x1, y1), (x2, y2), color, thickness)
        cv2.putText(
            base,
            f"{label}{idx}",
            (x1, max(12, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )


def load_mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    if not path.exists():
        return np.zeros(shape, dtype=np.uint8)
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return np.zeros(shape, dtype=np.uint8)
    if mask.shape[:2] != shape:
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return (mask > 0).astype(np.uint8)


def classify_fp(fp_boxes: Sequence[Box], barline_mask: np.ndarray) -> list[dict]:
    results = []
    for idx, (x1, y1, x2, y2) in enumerate(fp_boxes):
        band_mask = barline_mask[y1 : y2 + 1, x1 : x2 + 1]
        barline_ratio = float(band_mask.mean()) if band_mask.size else 0.0
        results.append(
            {
                "index": idx,
                "bbox": [x1, y1, x2, y2],
                "barline_mask_ratio": barline_ratio,
            }
        )
    return results


def save_crops(base: np.ndarray, boxes: Sequence[Box], out_dir: Path, prefix: str, pad: int = 12) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    h, w = base.shape[:2]
    for idx, (x1, y1, x2, y2) in enumerate(boxes):
        cx1 = max(0, x1 - pad)
        cy1 = max(0, y1 - pad)
        cx2 = min(w, x2 + pad)
        cy2 = min(h, y2 + pad)
        crop = base[cy1:cy2, cx1:cx2]
        out_path = out_dir / f"{prefix}{idx}.png"
        cv2.imwrite(str(out_path), crop)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--union-root", type=Path, required=True)
    parser.add_argument("--endpoint-ratio-threshold", type=float, default=0.04)
    parser.add_argument("--endpoint-x-scale", type=float, default=0.12)
    parser.add_argument("--endpoint-y-scale", type=float, default=0.8)
    parser.add_argument(
        "--notehead-open-kernel",
        type=int,
        default=0,
        help="Apply MORPH_OPEN with this kernel size to denoise the notehead mask.",
    )
    parser.add_argument(
        "--notehead-min-area",
        type=int,
        default=0,
        help="Remove connected components smaller than this area in the notehead mask.",
    )
    parser.add_argument(
        "--notehead-dilate",
        type=int,
        default=0,
        help="Dilate the notehead mask before geom filtering.",
    )
    parser.add_argument("--filter-clefs-keys", action="store_true")
    parser.add_argument("--clefs-keys-dilate", type=int, default=0)
    parser.add_argument("--clefs-keys-left-margin-ratio", type=float, default=0.2)
    parser.add_argument("--clefs-keys-overlap-min", type=float, default=0.05)
    parser.add_argument("--clefs-keys-right-margin-ratio", type=float, default=-1.0)
    parser.add_argument("--clefs-keys-overlap-min-right", type=float, default=0.0)
    parser.add_argument("--clefs-keys-open-kernel", type=int, default=0)
    parser.add_argument("--clefs-keys-min-area", type=int, default=0)
    parser.add_argument("--clefs-keys-max-aspect", type=float, default=0.0)
    parser.add_argument("--clefs-keys-min-height", type=int, default=0)
    parser.add_argument("--clefs-keys-max-width", type=int, default=0)
    parser.add_argument("--filter-barline-clefs-low", action="store_true")
    parser.add_argument("--barline-low-ratio", type=float, default=0.02)
    parser.add_argument("--clefs-low-ratio", type=float, default=0.02)
    parser.add_argument("--barline-min-height-ratio", type=float, default=0.0)
    parser.add_argument(
        "--barline-min-height-mask",
        choices=["staff", "staffs"],
        default="staff",
    )
    parser.add_argument("--barline-stem-max-height-ratio", type=float, default=0.0)
    parser.add_argument("--barline-stem-min-band-cover", type=float, default=0.6)
    parser.add_argument(
        "--barline-stem-mask",
        choices=["staff", "staffs"],
        default="staffs",
    )
    parser.add_argument(
        "--notehead-max-aspect",
        type=float,
        default=0.0,
        help="Remove tall thin components with height/width above this ratio.",
    )
    parser.add_argument(
        "--notehead-min-height",
        type=int,
        default=0,
        help="Minimum height in px to consider for aspect filtering.",
    )
    parser.add_argument(
        "--notehead-max-width",
        type=int,
        default=0,
        help="Keep components wider than this width (px) regardless of aspect.",
    )
    parser.add_argument("--cluster-max-dist", type=float, default=25.0)
    parser.add_argument("--min-row-count", type=int, default=3)
    parser.add_argument("--tol-top-px", type=float, default=5.0)
    parser.add_argument("--tol-bottom-px", type=float, default=5.0)
    parser.add_argument("--enable-end-barline-recovery", action="store_true")
    parser.add_argument("--endbar-search-width", type=int, default=40)
    parser.add_argument("--endbar-min-height-ratio", type=float, default=0.6)
    parser.add_argument("--endbar-right-clear-width", type=int, default=10)
    parser.add_argument("--endbar-right-clear-ratio", type=float, default=0.08)
    parser.add_argument("--endbar-staff-mask-mode", choices=["staff", "staffs"], default="staff")
    parser.add_argument("--endbar-debug", action="store_true")
    parser.add_argument(
        "--endbar-method",
        choices=[
            "projection",
            "morph",
            "hough",
            "runlen",
            "barline_mask",
            "staff_anchor",
            "adaptive",
            "lsd",
            "omr",
            "probe_scan",
        ],
        default="projection",
    )
    parser.add_argument("--endbar-morph-kernel-scale", type=float, default=0.6)
    parser.add_argument("--endbar-morph-constrain-height", action="store_true")
    parser.add_argument("--endbar-hough-constrain-height", action="store_true")
    parser.add_argument("--endbar-runlen-constrain-height", action="store_true")
    parser.add_argument("--endbar-anchor-pad", type=int, default=4)
    parser.add_argument("--endbar-adapt-block-size", type=int, default=25)
    parser.add_argument("--endbar-adapt-c", type=int, default=5)
    parser.add_argument("--endbar-lsd-vertical-tol", type=int, default=2)
    parser.add_argument("--probe-width", type=int, default=4)
    parser.add_argument("--probe-ink-threshold", type=int, default=180)
    parser.add_argument("--probe-min-ratio", type=float, default=0.85)
    parser.add_argument("--probe-min-peak-distance", type=int, default=6)
    parser.add_argument("--probe-max-per-band", type=int, default=8)
    parser.add_argument("--probe-refine-window", type=int, default=4)
    parser.add_argument("--probe-band-height-mode", choices=["staff", "median_box"], default="staff")
    parser.add_argument("--probe-band-height-scale", type=float, default=1.0)
    parser.add_argument("--probe-band-height-min", type=int, default=10)
    parser.add_argument("--probe-row-filter-mode", choices=["recluster", "reuse_rows"], default="recluster")
    parser.add_argument("--probe-row-min-count", type=int, default=2)
    parser.add_argument("--probe-row-max-dist", type=float, default=30.0)
    parser.add_argument("--probe-row-tol-top", type=float, default=12.0)
    parser.add_argument("--probe-row-tol-bottom", type=float, default=12.0)
    parser.add_argument("--probe-barline-mask-min-ratio", type=float, default=0.0)
    parser.add_argument("--probe-filter-vertical-run", action="store_true")
    parser.add_argument("--probe-vertical-run-ratio", type=float, default=0.8)
    parser.add_argument("--probe-filter-staff-overlap", action="store_true")
    parser.add_argument("--probe-staff-overlap-min", type=float, default=0.1)
    parser.add_argument("--probe-filter-multiband", action="store_true")
    parser.add_argument("--probe-multiband-x-tol", type=int, default=3)
    parser.add_argument("--probe-multiband-min-bands", type=int, default=2)
    parser.add_argument("--probe-filter-right-ink", action="store_true")
    parser.add_argument("--probe-right-ink-width", type=int, default=6)
    parser.add_argument("--probe-right-ink-max-ratio", type=float, default=0.25)
    parser.add_argument("--probe-filter-thinness", action="store_true")
    parser.add_argument("--probe-thinness-max-width", type=int, default=4)
    parser.add_argument("--probe-endpoint-x-scale", type=float, default=-1.0)
    parser.add_argument("--probe-endpoint-y-scale", type=float, default=-1.0)
    parser.add_argument("--probe-notehead-dilate", type=int, default=0)
    parser.add_argument(
        "--omr-preds-root",
        type=Path,
        default=REPO_ROOT / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5",
    )
    args = parser.parse_args()

    pages = [
        PageSpec(
            name="page_001",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_001_boxes_sorted.json",
            notehead_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_6_notehead.png",
            clefs_keys_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_7_clefs_keys.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_3_staff.png",
            staff_mask_alt=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_15_staffs.png",
            barline_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_8_bar_line_img.png",
            omr_preds=args.omr_preds_root / "page_001" / "predictions.json",
            union_preds=args.union_root / "page_001_hybrid_preds.json",
        ),
        PageSpec(
            name="page_004",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_004_boxes_sorted.json",
            notehead_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_6_notehead.png",
            clefs_keys_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_7_clefs_keys.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_3_staff.png",
            staff_mask_alt=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_15_staffs.png",
            barline_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_8_bar_line_img.png",
            omr_preds=args.omr_preds_root / "page_004" / "predictions.json",
            union_preds=args.union_root / "page_004_hybrid_preds.json",
        ),
        PageSpec(
            name="page_10",
            image=REPO_ROOT / "data/training/images/page_10.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_10_boxes_sorted.json",
            notehead_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_6_notehead.png",
            clefs_keys_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_7_clefs_keys.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_3_staff.png",
            staff_mask_alt=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_15_staffs.png",
            barline_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_8_bar_line_img.png",
            omr_preds=args.omr_preds_root / "page_10" / "predictions.json",
            union_preds=args.union_root / "page_10_hybrid_preds.json",
        ),
        PageSpec(
            name="page_15",
            image=REPO_ROOT / "data/training/images/page_15.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_15_boxes_sorted.json",
            notehead_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_6_notehead.png",
            clefs_keys_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_7_clefs_keys.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_3_staff.png",
            staff_mask_alt=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_15_staffs.png",
            barline_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_8_bar_line_img.png",
            omr_preds=args.omr_preds_root / "page_15" / "predictions.json",
            union_preds=args.union_root / "page_15_hybrid_preds.json",
        ),
    ]

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    overlays_root = output_root / "overlays"
    overlays_root.mkdir(parents=True, exist_ok=True)
    per_page_root = output_root / "per_page"
    per_page_root.mkdir(parents=True, exist_ok=True)

    summary_rows = []

    for page in pages:
        preds = load_preds(page.union_preds)
        base_img = cv2.imread(str(page.image))
        if base_img is None:
            raise FileNotFoundError(f"Failed to load image: {page.image}")
        notehead_mask = load_notehead_mask(page.notehead_mask, base_img.shape[:2])
        notehead_mask = denoise_notehead_mask(
            notehead_mask, args.notehead_open_kernel, args.notehead_min_area
        )
        notehead_mask = filter_notehead_components(
            notehead_mask,
            args.notehead_max_aspect,
            args.notehead_min_height,
            args.notehead_max_width,
        )
        notehead_mask = dilate_mask(notehead_mask, args.notehead_dilate)
        clefs_keys_mask = None
        if args.filter_clefs_keys:
            clefs_keys_mask = load_clefs_keys_mask(
                page.clefs_keys_mask, base_img.shape[:2]
            )
            clefs_keys_mask = refine_clefs_keys_mask(
                clefs_keys_mask,
                args.clefs_keys_open_kernel,
                args.clefs_keys_min_area,
                args.clefs_keys_max_aspect,
                args.clefs_keys_min_height,
                args.clefs_keys_max_width,
            )
            clefs_keys_mask = dilate_mask(clefs_keys_mask, args.clefs_keys_dilate)
        gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
        gt_boxes = load_gt(page.gt)

        y_centers = np.array([(box[1] + box[3]) / 2 for box in preds])
        rows, _ = cluster_by_y_distance(y_centers, args.cluster_max_dist, args.min_row_count)
        staff_space = estimate_staff_space(rows, preds)
        base_row_stats = build_row_stats(preds, args.cluster_max_dist, args.min_row_count)

        row_filtered = row_filter(
            preds,
            args.cluster_max_dist,
            args.min_row_count,
            args.tol_top_px,
            args.tol_bottom_px,
        )

        out_dir = per_page_root / page.name
        out_dir.mkdir(parents=True, exist_ok=True)

        geom_kept, geom_debug = geom_notehead_ratio_filter(
            row_filtered,
            notehead_mask,
            staff_space,
            args.endpoint_ratio_threshold,
            args.endpoint_x_scale,
            args.endpoint_y_scale,
        )
        geom_debug["notehead_mask_filter"] = {
            "open_kernel": args.notehead_open_kernel,
            "min_area": args.notehead_min_area,
            "dilate": args.notehead_dilate,
            "max_aspect": args.notehead_max_aspect,
            "min_height": args.notehead_min_height,
            "max_width": args.notehead_max_width,
        }
        added_end = []
        if args.enable_end_barline_recovery:
            staff_mask_path = page.staff_mask if args.endbar_staff_mask_mode == "staff" else page.staff_mask_alt
            staff_mask = load_staff_mask(staff_mask_path, base_img.shape[:2])
            debug_path = None
            if args.endbar_debug:
                debug_path = out_dir / "endbar_debug.png"
            if args.endbar_method == "projection":
                added_end = detect_end_barlines(
                    base_img,
                    staff_mask,
                    geom_kept,
                    search_width=args.endbar_search_width,
                    min_height_ratio=args.endbar_min_height_ratio,
                    right_clear_width=args.endbar_right_clear_width,
                    right_clear_ratio=args.endbar_right_clear_ratio,
                    debug_path=debug_path,
                )
            elif args.endbar_method == "morph":
                added_end = detect_end_barlines_morph(
                    base_img,
                    staff_mask,
                    geom_kept,
                    search_width=args.endbar_search_width,
                    min_height_ratio=args.endbar_min_height_ratio,
                    morph_kernel_scale=args.endbar_morph_kernel_scale,
                    constrain_height=args.endbar_morph_constrain_height,
                    debug_path=debug_path,
                )
            elif args.endbar_method == "hough":
                added_end = detect_end_barlines_hough(
                    base_img,
                    staff_mask,
                    geom_kept,
                    search_width=args.endbar_search_width,
                    min_height_ratio=args.endbar_min_height_ratio,
                    constrain_height=args.endbar_hough_constrain_height,
                    debug_path=debug_path,
                )
            elif args.endbar_method == "runlen":
                added_end = detect_end_barlines_runlen(
                    base_img,
                    staff_mask,
                    geom_kept,
                    search_width=args.endbar_search_width,
                    min_height_ratio=args.endbar_min_height_ratio,
                    constrain_height=args.endbar_runlen_constrain_height,
                    debug_path=debug_path,
                )
            elif args.endbar_method == "barline_mask":
                barline_mask = load_barline_mask(page.barline_mask, base_img.shape[:2])
                added_end = detect_end_barlines_from_mask(
                    barline_mask,
                    staff_mask,
                    geom_kept,
                    search_width=args.endbar_search_width,
                    min_height_ratio=args.endbar_min_height_ratio,
                    debug_path=debug_path,
                )
            elif args.endbar_method == "staff_anchor":
                added_end = detect_end_barlines_staff_anchor(
                    base_img,
                    staff_mask,
                    geom_kept,
                    search_width=args.endbar_search_width,
                    min_height_ratio=args.endbar_min_height_ratio,
                    anchor_pad=args.endbar_anchor_pad,
                    debug_path=debug_path,
                )
            elif args.endbar_method == "adaptive":
                added_end = detect_end_barlines_adaptive(
                    base_img,
                    staff_mask,
                    geom_kept,
                    search_width=args.endbar_search_width,
                    min_height_ratio=args.endbar_min_height_ratio,
                    adapt_block_size=args.endbar_adapt_block_size,
                    adapt_c=args.endbar_adapt_c,
                    debug_path=debug_path,
                )
            elif args.endbar_method == "lsd":
                added_end = detect_end_barlines_lsd(
                    base_img,
                    staff_mask,
                    geom_kept,
                    search_width=args.endbar_search_width,
                    min_height_ratio=args.endbar_min_height_ratio,
                    vertical_tol=args.endbar_lsd_vertical_tol,
                    debug_path=debug_path,
                )
            elif args.endbar_method == "probe_scan":
                added_end = detect_probe_scan(
                    base_img,
                    staff_mask,
                    geom_kept,
                    probe_width=args.probe_width,
                    ink_threshold=args.probe_ink_threshold,
                    min_ratio=args.probe_min_ratio,
                    min_peak_distance=args.probe_min_peak_distance,
                    refine_window=args.probe_refine_window,
                    max_per_band=args.probe_max_per_band,
                    band_height_mode=args.probe_band_height_mode,
                    band_height_scale=args.probe_band_height_scale,
                    band_height_min=args.probe_band_height_min,
                    debug_path=debug_path,
                )
            else:
                barline_mask = load_barline_mask(page.barline_mask, base_img.shape[:2])
                omr_preds = load_omr_preds(page.omr_preds)
                added_end = detect_end_barlines_omr(
                    base_img,
                    staff_mask,
                    barline_mask,
                    omr_preds,
                    geom_kept,
                    min_height_ratio=args.endbar_min_height_ratio,
                    debug_path=debug_path,
                )
            if added_end:
                if args.probe_row_filter_mode == "reuse_rows":
                    added_row = row_filter_with_stats(
                        added_end,
                        base_row_stats,
                        args.probe_row_max_dist,
                        args.probe_row_tol_top,
                        args.probe_row_tol_bottom,
                    )
                else:
                    added_row = row_filter(
                        added_end,
                        args.probe_row_max_dist,
                        args.probe_row_min_count,
                        args.probe_row_tol_top,
                        args.probe_row_tol_bottom,
                    )
                probe_notehead_mask = dilate_mask(
                    notehead_mask, args.probe_notehead_dilate
                )
                probe_x_scale = args.endpoint_x_scale if args.probe_endpoint_x_scale <= 0 else args.probe_endpoint_x_scale
                probe_y_scale = args.endpoint_y_scale if args.probe_endpoint_y_scale <= 0 else args.probe_endpoint_y_scale
                added_geom, added_geom_debug = geom_notehead_ratio_filter(
                    added_row,
                    probe_notehead_mask,
                    staff_space,
                    args.endpoint_ratio_threshold,
                    probe_x_scale,
                    probe_y_scale,
                )
                added_geom_debug["notehead_mask_filter"] = {
                    "open_kernel": args.notehead_open_kernel,
                    "min_area": args.notehead_min_area,
                    "dilate": args.notehead_dilate,
                    "probe_dilate": args.probe_notehead_dilate,
                    "max_aspect": args.notehead_max_aspect,
                    "min_height": args.notehead_min_height,
                    "max_width": args.notehead_max_width,
                }
                added_geom_pre_mask = list(added_geom)
                if args.probe_barline_mask_min_ratio > 0:
                    barline_mask = load_mask(page.barline_mask, base_img.shape[:2])
                    before = len(added_geom)
                    added_geom = [
                        box
                        for box in added_geom
                        if barline_mask[box[1] : box[3] + 1, box[0] : box[2] + 1].mean()
                        >= args.probe_barline_mask_min_ratio
                    ]
                    after = len(added_geom)
                    (out_dir / "end_recovered_barline_mask.json").write_text(
                        json.dumps(
                            {
                                "min_ratio": args.probe_barline_mask_min_ratio,
                                "before": before,
                                "after": after,
                            },
                            indent=2,
                        )
                    )
                if args.probe_filter_vertical_run:
                    added_geom, vr_debug = filter_vertical_run(
                        added_geom,
                        gray,
                        ink_threshold=args.probe_ink_threshold,
                        min_run_ratio=args.probe_vertical_run_ratio,
                    )
                    (out_dir / "end_recovered_vertical_run.json").write_text(json.dumps(vr_debug, indent=2))
                if args.probe_filter_staff_overlap:
                    staff_mask_used = staff_mask if args.endbar_staff_mask_mode == "staff" else staff_mask
                    added_geom, staff_debug = filter_staff_overlap(
                        added_geom,
                        staff_mask_used,
                        min_ratio=args.probe_staff_overlap_min,
                    )
                    (out_dir / "end_recovered_staff_overlap.json").write_text(json.dumps(staff_debug, indent=2))
                if args.probe_filter_multiband:
                    band_mask_path = page.staff_mask if args.endbar_staff_mask_mode == "staff" else page.staff_mask_alt
                    staff_mask_used = load_staff_mask(band_mask_path, base_img.shape[:2])
                    bands = staff_bands_from_mask(staff_mask_used)
                    added_geom, multi_debug = filter_multiband_consensus(
                        added_geom,
                        bands,
                        x_tol=args.probe_multiband_x_tol,
                        min_bands=args.probe_multiband_min_bands,
                    )
                    (out_dir / "end_recovered_multiband.json").write_text(json.dumps(multi_debug, indent=2))
                if args.probe_filter_right_ink:
                    added_geom, right_debug = filter_right_ink(
                        added_geom,
                        gray,
                        ink_threshold=args.probe_ink_threshold,
                        right_width=args.probe_right_ink_width,
                        max_ratio=args.probe_right_ink_max_ratio,
                    )
                    (out_dir / "end_recovered_right_ink.json").write_text(json.dumps(right_debug, indent=2))
                if args.probe_filter_thinness:
                    added_geom, thin_debug = filter_thinness(
                        added_geom,
                        gray,
                        ink_threshold=args.probe_ink_threshold,
                        max_width_px=args.probe_thinness_max_width,
                    )
                    (out_dir / "end_recovered_thinness.json").write_text(json.dumps(thin_debug, indent=2))
                (out_dir / "end_recovered_row.json").write_text(json.dumps(added_row, indent=2))
                (out_dir / "end_recovered_geom_pre_mask.json").write_text(
                    json.dumps(added_geom_pre_mask, indent=2)
                )
                (out_dir / "end_recovered_geom.json").write_text(json.dumps(added_geom, indent=2))
                (out_dir / "end_recovered_geom_debug.json").write_text(json.dumps(added_geom_debug, indent=2))
                geom_kept = geom_kept + added_geom

        if args.filter_clefs_keys and clefs_keys_mask is not None:
            before = len(geom_kept)
            geom_kept, clef_debug = filter_clefs_keys_overlap(
                geom_kept,
                clefs_keys_mask,
                args.clefs_keys_left_margin_ratio,
                args.clefs_keys_overlap_min,
                args.clefs_keys_right_margin_ratio,
                args.clefs_keys_overlap_min_right,
            )
            clef_debug["before"] = before
            clef_debug["after"] = len(geom_kept)
            clef_debug["clefs_keys_dilate"] = args.clefs_keys_dilate
            clef_debug["refine"] = {
                "open_kernel": args.clefs_keys_open_kernel,
                "min_area": args.clefs_keys_min_area,
                "max_aspect": args.clefs_keys_max_aspect,
                "min_height": args.clefs_keys_min_height,
                "max_width": args.clefs_keys_max_width,
            }
            (out_dir / "clefs_keys_filter.json").write_text(
                json.dumps(clef_debug, indent=2)
            )

        if args.filter_barline_clefs_low:
            barline_mask = load_mask(page.barline_mask, base_img.shape[:2])
            clefs_mask = load_mask(page.clefs_keys_mask, base_img.shape[:2])
            before = len(geom_kept)
            geom_kept, bc_debug = filter_barline_clefs_low(
                geom_kept,
                barline_mask,
                clefs_mask,
                args.barline_low_ratio,
                args.clefs_low_ratio,
            )
            bc_debug["before"] = before
            bc_debug["after"] = len(geom_kept)
            (out_dir / "barline_clefs_low_filter.json").write_text(
                json.dumps(bc_debug, indent=2)
            )

        if args.barline_min_height_ratio > 0:
            staff_mask_path = (
                page.staff_mask
                if args.barline_min_height_mask == "staff"
                else page.staff_mask_alt
            )
            staff_mask = load_staff_mask(staff_mask_path, base_img.shape[:2])
            before = len(geom_kept)
            geom_kept, height_debug = filter_min_height_ratio(
                geom_kept, staff_mask, args.barline_min_height_ratio
            )
            height_debug["before"] = before
            height_debug["after"] = len(geom_kept)
            height_debug["mask"] = args.barline_min_height_mask
            (out_dir / "min_height_filter.json").write_text(
                json.dumps(height_debug, indent=2)
            )

        if args.barline_stem_max_height_ratio > 0:
            staff_mask_path = (
                page.staff_mask
                if args.barline_stem_mask == "staff"
                else page.staff_mask_alt
            )
            staff_mask = load_staff_mask(staff_mask_path, base_img.shape[:2])
            before = len(geom_kept)
            geom_kept, stem_debug = filter_stem_outside_staff(
                geom_kept,
                staff_mask,
                args.barline_stem_max_height_ratio,
                args.barline_stem_min_band_cover,
            )
            stem_debug["before"] = before
            stem_debug["after"] = len(geom_kept)
            stem_debug["mask"] = args.barline_stem_mask
            (out_dir / "stem_outside_filter.json").write_text(
                json.dumps(stem_debug, indent=2)
            )

        match = greedy_barline_match(list(geom_kept), list(gt_boxes), iou_threshold=0.5)
        tp = len(match.matches)
        fp = len(match.false_positive_indices)
        fn = len(match.false_negative_indices)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        (out_dir / "row_filtered.json").write_text(json.dumps(row_filtered, indent=2))
        (out_dir / "geom_kept.json").write_text(json.dumps(geom_kept, indent=2))
        (out_dir / "geom_debug.json").write_text(json.dumps(geom_debug, indent=2))
        if added_end:
            (out_dir / "end_recovered.json").write_text(json.dumps(added_end, indent=2))
        (out_dir / "metrics.json").write_text(
            json.dumps(
                {
                    "TP": tp,
                    "FP": fp,
                    "FN": fn,
                    "Precision": precision,
                    "Recall": recall,
                    "F1": f1,
                },
                indent=2,
            )
        )

        overlay = base_img.copy()
        tp_indices = {m.pred_index for m in match.matches}
        tp_boxes = [geom_kept[i] for i in sorted(tp_indices)]
        fp_boxes = [geom_kept[i] for i in sorted(match.false_positive_indices)]
        fn_boxes = [gt_boxes[i] for i in sorted(match.false_negative_indices)]
        draw_boxes(overlay, tp_boxes, TP_COLOR, 2, "TP#")
        draw_boxes(overlay, fp_boxes, FP_COLOR, 2, "FP#")
        draw_boxes(overlay, fn_boxes, FN_COLOR, 2, "FN#")
        overlay_path = overlays_root / f"{page.name}_tp_fp_fn.png"
        cv2.imwrite(str(overlay_path), overlay)
        save_crops(base_img, fp_boxes, out_dir / "fp_crops", "FP_")
        (out_dir / "fn_boxes.json").write_text(json.dumps(fn_boxes, indent=2))
        (out_dir / "fp_boxes.json").write_text(json.dumps(fp_boxes, indent=2))
        (out_dir / "tp_boxes.json").write_text(json.dumps(tp_boxes, indent=2))
        barline_mask = load_mask(page.barline_mask, base_img.shape[:2])
        fp_class = classify_fp(fp_boxes, barline_mask)
        (out_dir / "fp_classification.json").write_text(json.dumps(fp_class, indent=2))
        if fn_boxes:
            fn_overlay = base_img.copy()
            draw_boxes(fn_overlay, fn_boxes, FN_COLOR, 3, "FN#")
            fn_overlay_path = overlays_root / f"{page.name}_fn_only.png"
            cv2.imwrite(str(fn_overlay_path), fn_overlay)
        if fp_boxes:
            fp_overlay = base_img.copy()
            draw_boxes(fp_overlay, fp_boxes, FP_COLOR, 2, "FP#")
            fp_overlay_path = overlays_root / f"{page.name}_fp_only.png"
            cv2.imwrite(str(fp_overlay_path), fp_overlay)

        summary_rows.append(
            {
                "page": page.name,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "kept": len(geom_kept),
                "row_kept": len(row_filtered),
            }
        )

    summary_table = [
        "| Page | TP | FP | FN | row_kept | geom_kept |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in summary_rows:
        summary_table.append(
            f"| {row['page']} | {row['tp']} | {row['fp']} | {row['fn']} | {row['row_kept']} | {row['kept']} |"
        )
    (output_root / "summary_table.md").write_text("\n".join(summary_table) + "\n")


if __name__ == "__main__":
    main()
