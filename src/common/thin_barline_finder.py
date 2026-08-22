"""Heuristics for recovering thin vertical barlines missed by primary detectors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import cv2
import numpy as np

from src.common import Box

_RUN_X_BLOCK = 64
_PAIR_OUTER_CHUNK = 1024


@dataclass(frozen=True)
class ThinBarlineConfig:
    min_height: int = 18
    max_height: int = 24
    max_width: int = 4
    pixel_threshold: int = 200
    dark_pixel_threshold: int = 120
    y_merge_tolerance: int = 4
    y_center_tolerance: int = 8
    x_center_tolerance: int = 4
    adjacent_min_intensity: int = 185
    adjacent_relaxed_span: int = 6
    adjacent_relaxed_dark_ratio: float = 0.18
    max_intensity_std: float = 60.0
    max_intensity_std_relaxed: float = 80.0
    notehead_dark_ratio: float = 0.21
    notehead_std_floor: float = 45.0
    allow_single_side_bright: bool = True
    single_side_dark_ratio: float = 0.6
    vertical_gap_fill: int = 2
    left_margin_limit: int = 80
    cluster_x_tolerance: int = 2
    cluster_reject_count: int = 4
    cluster_reject_span: int = 120
    double_pair_max_gap: int = 6
    double_pair_min_overlap: float = 0.75
    double_pair_min_height: int = 18
    double_pair_max_width: int = 6


def _centroid(box: Box) -> Tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _is_close(candidate: Box, existing: Sequence[Box], *, cfg: ThinBarlineConfig) -> bool:
    cx, cy = _centroid(candidate)
    for box in existing:
        ex, ey = _centroid(box)
        if abs(cx - ex) <= cfg.x_center_tolerance and abs(cy - ey) <= cfg.y_center_tolerance:
            return True
    return False


def _extract_vertical_runs(
    binary: np.ndarray,
    *,
    min_height: int,
    max_height: int,
) -> List[Tuple[int, int, int]]:
    """Return qualifying vertical runs in the legacy x-then-y order.

    Process cache-sized x blocks so the very large x4 binary image does not
    require one full-image transition temporary. Each block preserves the
    legacy x-then-y ordering, and concatenating blocks preserves global order.
    """

    if binary.ndim != 2:
        raise ValueError(f"Thin-barline binary image must be 2-D, got {binary.shape}")
    if max_height < 1:
        return []

    min_height_relaxed = max(min_height - 1, 1)
    width = binary.shape[1]
    runs: List[Tuple[int, int, int]] = []
    for x_offset in range(0, width, _RUN_X_BLOCK):
        x_end = min(width, x_offset + _RUN_X_BLOCK)
        active_xy = (binary[:, x_offset:x_end] != 0).T
        padded = np.pad(
            active_xy,
            ((0, 0), (1, 1)),
            mode="constant",
            constant_values=False,
        )
        edge_x, edge_y = np.nonzero(padded[:, 1:] != padded[:, :-1])
        if edge_x.size == 0:
            continue
        if edge_x.size % 2:
            raise RuntimeError("Unbalanced thin-barline vertical run transitions")

        start_x = edge_x[0::2]
        start_y = edge_y[0::2]
        end_x = edge_x[1::2]
        end_y = edge_y[1::2]
        if start_x.shape != end_x.shape or not np.array_equal(start_x, end_x):
            raise RuntimeError("Unbalanced thin-barline vertical run transitions")

        run_heights = end_y - start_y
        keep = (run_heights >= min_height_relaxed) & (run_heights <= max_height)
        runs.extend(
            (int(x_offset + x), int(y1), int(y2))
            for x, y1, y2 in zip(start_x[keep], start_y[keep], end_y[keep])
        )
    return runs


def _find_double_pairs(merged: Sequence[Box], *, cfg: ThinBarlineConfig) -> set[Box]:
    """Return exact double-barline membership with bounded vectorized chunks."""

    if len(merged) < 2 or cfg.double_pair_max_gap <= 0:
        return set()

    boxes = np.asarray(merged, dtype=np.int64)
    count = len(boxes)
    starts = boxes[:, 0]
    widths = boxes[:, 2] - boxes[:, 0]
    heights = boxes[:, 3] - boxes[:, 1]
    eligible = (widths <= cfg.double_pair_max_width) & (heights >= cfg.double_pair_min_height)
    paired = np.zeros(count, dtype=bool)
    indices = np.arange(count, dtype=np.int64)

    for chunk_start in range(0, count - 1, _PAIR_OUTER_CHUNK):
        chunk_end = min(count - 1, chunk_start + _PAIR_OUTER_CHUNK)
        outer = indices[chunk_start:chunk_end]
        first = np.searchsorted(starts, boxes[outer, 2], side="right")
        last = np.searchsorted(
            starts,
            boxes[outer, 2] + cfg.double_pair_max_gap,
            side="right",
        )
        lengths = last - first
        lengths = np.where(eligible[outer], lengths, 0)
        total = int(lengths.sum())
        if total == 0:
            continue

        left_indices = np.repeat(outer, lengths)
        offsets = np.cumsum(lengths, dtype=np.int64) - lengths
        right_indices = np.arange(total, dtype=np.int64) + np.repeat(first - offsets, lengths)

        right_eligible = eligible[right_indices]
        if not np.any(right_eligible):
            continue
        left_indices = left_indices[right_eligible]
        right_indices = right_indices[right_eligible]

        overlap = np.minimum(boxes[left_indices, 3], boxes[right_indices, 3]) - np.maximum(
            boxes[left_indices, 1], boxes[right_indices, 1]
        )
        valid = (overlap > 0) & (
            overlap.astype(np.float64) / np.maximum(heights[left_indices], heights[right_indices])
            >= cfg.double_pair_min_overlap
        )
        if np.any(valid):
            paired[left_indices[valid]] = True
            paired[right_indices[valid]] = True

    return {tuple(int(value) for value in boxes[index]) for index in np.flatnonzero(paired)}


def _rectangle_sums(
    integral: np.ndarray,
    y1: np.ndarray,
    y2: np.ndarray,
    x1: np.ndarray,
    x2: np.ndarray,
) -> np.ndarray:
    return integral[y2, x2] - integral[y1, x2] - integral[y2, x1] + integral[y1, x1]


def _filter_candidates(
    image: np.ndarray,
    merged: Sequence[Box],
    paired_boxes: set[Box],
    existing: Sequence[Box],
    *,
    cfg: ThinBarlineConfig,
) -> List[Box]:
    """Apply the legacy candidate filters using batched rectangle statistics.

    Immediate/relaxed neighbour means and dark-pixel ratios are exact integer
    rectangle sums. Computing them by x blocks avoids tens of thousands of
    tiny NumPy calls while retaining the legacy thresholds and candidate order.
    Expensive ROI mean/std checks are still evaluated with NumPy for the small
    subset that passes adjacency filtering.
    """

    height, width = image.shape
    early: List[Tuple[int, Box]] = []
    for index, box in enumerate(merged):
        x1, y1, x2, y2 = box
        box_width = x2 - x1
        box_height = y2 - y1
        if box_width < 2 and box_height < cfg.min_height:
            continue
        if box not in paired_boxes and _is_close(box, existing, cfg=cfg):
            continue
        cx, _ = _centroid(box)
        if cfg.left_margin_limit > 0 and cx <= cfg.left_margin_limit:
            continue
        if y2 <= y1 or x2 <= x1:
            continue
        if x1 <= 0 or x2 >= width:
            continue
        early.append((index, box))

    if not early:
        return []

    span = max(cfg.adjacent_relaxed_span, 0)
    side_span = max(span, 3)
    max_candidate_width = max(box[2] - box[0] for _, box in early)
    int32_limit = int(np.iinfo(np.int32).max)
    max_i32_strip_width = max(int32_limit // max(height * 255, 1), 1)
    padding_width = side_span + max_candidate_width + side_span
    core_width = min(192, max_i32_strip_width - padding_width)
    if core_width >= 1:
        integral_depth = cv2.CV_32S
    else:
        core_width = 64
        integral_depth = cv2.CV_64F

    grouped: Dict[int, List[Tuple[int, Box]]] = {}
    for item in early:
        grouped.setdefault(item[1][0] // core_width, []).append(item)

    adjacency_survivors: Dict[int, Tuple[Box, float, float, bool, bool, bool]] = {}
    for block_index, items in grouped.items():
        core_start = block_index * core_width
        core_end = min(width, (block_index + 1) * core_width)
        strip_start = max(0, core_start - side_span)
        strip_end = min(width, core_end + max_candidate_width + side_span)
        strip = image[:, strip_start:strip_end]
        integral = cv2.integral(strip, sdepth=integral_depth)
        dark_integral = cv2.integral(
            (strip < cfg.dark_pixel_threshold).astype(np.uint8),
            sdepth=cv2.CV_32S,
        )

        item_indices = np.asarray([item[0] for item in items], dtype=np.int64)
        boxes = np.asarray([item[1] for item in items], dtype=np.int64)
        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]

        def local_x(values: np.ndarray) -> np.ndarray:
            return values - strip_start

        left_x1 = np.maximum(0, x1 - 3)
        left_x2 = x1
        right_x1 = x2
        right_x2 = np.minimum(width, x2 + 3)
        left_count = (y2 - y1) * (left_x2 - left_x1)
        right_count = (y2 - y1) * (right_x2 - right_x1)

        left_sum = _rectangle_sums(integral, y1, y2, local_x(left_x1), local_x(left_x2)).astype(
            np.float64
        )
        right_sum = _rectangle_sums(integral, y1, y2, local_x(right_x1), local_x(right_x2)).astype(
            np.float64
        )
        left_dark_count = _rectangle_sums(
            dark_integral, y1, y2, local_x(left_x1), local_x(left_x2)
        ).astype(np.float64)
        right_dark_count = _rectangle_sums(
            dark_integral, y1, y2, local_x(right_x1), local_x(right_x2)
        ).astype(np.float64)

        left_mean = left_sum / left_count
        right_mean = right_sum / right_count
        left_dark_ratio = left_dark_count / left_count
        right_dark_ratio = right_dark_count / right_count
        left_ok = left_mean >= cfg.adjacent_min_intensity
        right_ok = right_mean >= cfg.adjacent_min_intensity

        if span > 3:
            relaxed_left_x1 = np.maximum(0, x1 - span)
            relaxed_left_x2 = np.maximum(0, x1 - 3)
            relaxed_right_x1 = np.minimum(width, x2 + 3)
            relaxed_right_x2 = np.minimum(width, x2 + span)
            relaxed_left_count = (y2 - y1) * (relaxed_left_x2 - relaxed_left_x1)
            relaxed_right_count = (y2 - y1) * (relaxed_right_x2 - relaxed_right_x1)
            left_valid = relaxed_left_count > 0
            right_valid = relaxed_right_count > 0

            if np.any(left_valid):
                relaxed_left_sum = _rectangle_sums(
                    integral,
                    y1[left_valid],
                    y2[left_valid],
                    local_x(relaxed_left_x1[left_valid]),
                    local_x(relaxed_left_x2[left_valid]),
                ).astype(np.float64)
                relaxed_left_dark = _rectangle_sums(
                    dark_integral,
                    y1[left_valid],
                    y2[left_valid],
                    local_x(relaxed_left_x1[left_valid]),
                    local_x(relaxed_left_x2[left_valid]),
                ).astype(np.float64)
                relaxed_left_mean = relaxed_left_sum / relaxed_left_count[left_valid]
                relaxed_left_ratio = relaxed_left_dark / relaxed_left_count[left_valid]
                left_positions = np.flatnonzero(left_valid)
                left_ok[left_positions] |= (relaxed_left_mean >= cfg.adjacent_min_intensity) & (
                    relaxed_left_ratio <= cfg.adjacent_relaxed_dark_ratio
                )

            if np.any(right_valid):
                relaxed_right_sum = _rectangle_sums(
                    integral,
                    y1[right_valid],
                    y2[right_valid],
                    local_x(relaxed_right_x1[right_valid]),
                    local_x(relaxed_right_x2[right_valid]),
                ).astype(np.float64)
                relaxed_right_dark = _rectangle_sums(
                    dark_integral,
                    y1[right_valid],
                    y2[right_valid],
                    local_x(relaxed_right_x1[right_valid]),
                    local_x(relaxed_right_x2[right_valid]),
                ).astype(np.float64)
                relaxed_right_mean = relaxed_right_sum / relaxed_right_count[right_valid]
                relaxed_right_ratio = relaxed_right_dark / relaxed_right_count[right_valid]
                right_positions = np.flatnonzero(right_valid)
                right_ok[right_positions] |= (relaxed_right_mean >= cfg.adjacent_min_intensity) & (
                    relaxed_right_ratio <= cfg.adjacent_relaxed_dark_ratio
                )

        adjacency_ok = left_ok & right_ok
        single_side_override = np.zeros(len(items), dtype=bool)
        if cfg.allow_single_side_bright:
            one_side_ok = left_ok ^ right_ok
            failing_ratio = np.where(left_ok, right_dark_ratio, left_dark_ratio)
            single_side_override = (
                (~adjacency_ok) & one_side_ok & (failing_ratio <= cfg.single_side_dark_ratio)
            )

        box_widths = x2 - x1
        box_heights = y2 - y1
        keep = (adjacency_ok | single_side_override) & ~(
            single_side_override & (box_widths == 1) & (box_heights < 20)
        )
        for position in np.flatnonzero(keep):
            adjacency_survivors[int(item_indices[position])] = (
                tuple(int(value) for value in boxes[position]),
                float(left_dark_ratio[position]),
                float(right_dark_ratio[position]),
                bool(left_ok[position]),
                bool(right_ok[position]),
                bool(single_side_override[position]),
            )

    candidates: List[Box] = []
    for index, box in enumerate(merged):
        metrics = adjacency_survivors.get(index)
        if metrics is None:
            continue
        box, left_dark_ratio, right_dark_ratio, left_ok, right_ok, single_side_override = metrics
        x1, y1, x2, y2 = box
        roi = image[y1:y2, x1:x2]
        mean_intensity = float(np.mean(roi))
        if mean_intensity >= cfg.pixel_threshold:
            continue

        std_intensity = float(np.std(roi))
        if std_intensity > cfg.max_intensity_std:
            box_width = max(box[2] - box[0], 1)
            if not (
                box_width <= 4
                and ((left_ok and right_ok) or single_side_override)
                and std_intensity <= cfg.max_intensity_std_relaxed
            ):
                continue
        left_dark = left_dark_ratio > cfg.notehead_dark_ratio
        right_dark = right_dark_ratio > cfg.notehead_dark_ratio
        reject_notehead = (
            left_dark and right_dark if single_side_override else left_dark or right_dark
        )
        if reject_notehead and std_intensity >= cfg.notehead_std_floor:
            continue
        candidates.append(box)

    return candidates


def detect_thin_vertical_runs(
    image_path: Path,
    existing_boxes: Iterable[Box],
    *,
    config: ThinBarlineConfig | None = None,
    grayscale_image: np.ndarray | None = None,
) -> List[Box]:
    """Detect slender vertical runs likely corresponding to missed barlines.

    Callers that already own the decoded source image can pass ``grayscale_image``
    to avoid decoding the same image again. Standalone callers may continue to
    supply only ``image_path``.
    """

    cfg = config or ThinBarlineConfig()
    image = grayscale_image
    if image is None:
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(
                f"Failed to load image for thin barline detection: {image_path}"
            )
    elif image.ndim != 2:
        raise ValueError(f"Thin-barline grayscale image must be 2-D, got {image.shape}")

    binary = (image < cfg.pixel_threshold).astype(np.uint8)
    if cfg.vertical_gap_fill > 0:
        kernel = np.ones((cfg.vertical_gap_fill + 1, 1), dtype=np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    runs = _extract_vertical_runs(
        binary,
        min_height=cfg.min_height,
        max_height=cfg.max_height,
    )
    if not runs:
        return []

    runs.sort()
    merged: List[Box] = []
    idx = 0
    while idx < len(runs):
        x, y1, y2 = runs[idx]
        current_x1 = x
        current_x2 = x + 1
        current_y1 = y1
        current_y2 = y2
        idx += 1
        while idx < len(runs):
            nx, ny1, ny2 = runs[idx]
            if (
                nx - current_x2 <= 1
                and abs(ny1 - current_y1) <= cfg.y_merge_tolerance
                and abs(ny2 - current_y2) <= cfg.y_merge_tolerance
            ):
                current_x2 = nx + 1
                current_y1 = min(current_y1, ny1)
                current_y2 = max(current_y2, ny2)
                idx += 1
            else:
                break
        if current_x2 - current_x1 <= cfg.max_width:
            merged.append((current_x1, current_y1, current_x2, current_y2))

    if not merged:
        return []

    paired_boxes = _find_double_pairs(merged, cfg=cfg)
    existing = list(existing_boxes)
    candidates = _filter_candidates(image, merged, paired_boxes, existing, cfg=cfg)
    if not candidates:
        return []

    bucket_width = max(cfg.cluster_x_tolerance, 1)
    clustered: Dict[int, List[Box]] = {}
    for box in candidates:
        cx, _ = _centroid(box)
        key = int(round(cx / bucket_width)) * bucket_width
        clustered.setdefault(key, []).append(box)

    filtered: List[Box] = []
    for key, bucket_boxes in clustered.items():
        if (
            cfg.cluster_reject_count > 0
            and len(bucket_boxes) >= cfg.cluster_reject_count
            and cfg.cluster_reject_span > 0
        ):
            min_y = min(box[1] for box in bucket_boxes)
            max_y = max(box[3] for box in bucket_boxes)
            if max_y - min_y >= cfg.cluster_reject_span:
                is_near_existing = False
                for e_box in existing:
                    e_cx, _ = _centroid(e_box)
                    if abs(key - e_cx) < cfg.x_center_tolerance * 2:
                        is_near_existing = True
                        break

                if not is_near_existing:
                    continue
                rescued_boxes = []
                for box in bucket_boxes:
                    h = box[3] - box[1]
                    if h >= 20:
                        rescued_boxes.append(box)
                bucket_boxes = rescued_boxes
                if not bucket_boxes:
                    continue

        filtered.extend(bucket_boxes)

    return filtered


__all__ = ["ThinBarlineConfig", "detect_thin_vertical_runs"]
