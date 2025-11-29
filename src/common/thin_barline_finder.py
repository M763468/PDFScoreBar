"""Heuristics for recovering thin vertical barlines missed by primary detectors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]


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


def detect_thin_vertical_runs(
    image_path: Path,
    existing_boxes: Iterable[Box],
    *,
    config: ThinBarlineConfig | None = None,
) -> List[Box]:
    """Detect slender vertical runs likely corresponding to missed barlines.

    The detector scans binary columns for contiguous runs of dark pixels whose
    height matches typical staff spans (≈18–22 px). It merges neighbouring
    columns, filters out candidates close to existing predictions, and returns
    additional bounding boxes in image coordinates.
    """

    cfg = config or ThinBarlineConfig()
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"Failed to load image for thin barline detection: {image_path}")

    # Treat darker pixels (ink) as 1, background as 0.
    binary = (image < cfg.pixel_threshold).astype(np.uint8)
    if cfg.vertical_gap_fill > 0:
        kernel = np.ones((cfg.vertical_gap_fill + 1, 1), dtype=np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    height, width = binary.shape

    runs: List[Tuple[int, int, int]] = []  # (x, y_start, y_end)
    min_height_relaxed = max(cfg.min_height - 1, 1)
    for x in range(width):
        column = binary[:, x]
        y = 0
        while y < height:
            # Skip background
            while y < height and column[y] == 0:
                y += 1
            if y >= height:
                break
            start = y
            while y < height and column[y]:
                y += 1
            run_height = y - start
            if cfg.min_height <= run_height <= cfg.max_height:
                runs.append((x, start, y))
            elif min_height_relaxed <= run_height <= cfg.max_height:
                runs.append((x, start, y))

    if not runs:
        return []

    # Merge adjacent columns that represent the same vertical run.
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
            # Allow a 1 px gap between columns and small vertical wobble.
            if nx - current_x2 <= 1 and abs(ny1 - current_y1) <= cfg.y_merge_tolerance and abs(ny2 - current_y2) <= cfg.y_merge_tolerance:
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

    existing = list(existing_boxes)
    candidates: List[Box] = []
    for box in merged:
        if _is_close(box, existing, cfg=cfg):
            continue
        x1, y1, x2, y2 = box
        cx, _ = _centroid(box)
        if cfg.left_margin_limit > 0 and cx <= cfg.left_margin_limit:
            # Skip left margin artefacts (e.g. gutter pillars)
            continue
        roi = image[y1:y2, x1:x2]
        if roi.size == 0:
            continue
        mean_intensity = float(np.mean(roi))
        if mean_intensity >= cfg.pixel_threshold:
            # Likely background noise; skip.
            continue
        left = image[y1:y2, max(0, x1 - 3) : x1]
        right = image[y1:y2, x2 : min(width, x2 + 3)]
        if left.size == 0 or right.size == 0:
            continue

        def _window_metrics(window: np.ndarray) -> Tuple[float | None, float | None]:
            if window.size == 0:
                return None, None
            mean = float(np.mean(window))
            ratio = float(np.count_nonzero(window < cfg.dark_pixel_threshold)) / window.size
            return mean, ratio

        left_mean, left_dark_ratio = _window_metrics(left)
        right_mean, right_dark_ratio = _window_metrics(right)

        def _relaxed_metrics(is_left: bool) -> Tuple[float | None, float | None]:
            span = max(cfg.adjacent_relaxed_span, 0)
            if span <= 3:
                return None, None
            if is_left:
                start = max(0, x1 - span)
                end = max(0, x1 - 3)
            else:
                start = min(width, x2 + 3)
                end = min(width, x2 + span)
            if end <= start:
                return None, None
            window = image[y1:y2, start:end]
            if window.size == 0:
                return None, None
            return _window_metrics(window)

        left_ok = left_mean is not None and left_mean >= cfg.adjacent_min_intensity
        if not left_ok:
            relaxed_mean, relaxed_dark = _relaxed_metrics(True)
            if (
                relaxed_mean is not None
                and relaxed_mean >= cfg.adjacent_min_intensity
                and (relaxed_dark is None or relaxed_dark <= cfg.adjacent_relaxed_dark_ratio)
            ):
                left_ok = True

        right_ok = right_mean is not None and right_mean >= cfg.adjacent_min_intensity
        if not right_ok:
            relaxed_mean, relaxed_dark = _relaxed_metrics(False)
            if (
                relaxed_mean is not None
                and relaxed_mean >= cfg.adjacent_min_intensity
                and (relaxed_dark is None or relaxed_dark <= cfg.adjacent_relaxed_dark_ratio)
            ):
                right_ok = True

        adjacency_ok = left_ok and right_ok
        single_side_override = False
        if not adjacency_ok and cfg.allow_single_side_bright and (left_ok ^ right_ok):
            failing_ratio = left_dark_ratio if not left_ok else right_dark_ratio
            if failing_ratio is None or failing_ratio <= cfg.single_side_dark_ratio:
                single_side_override = True
        if not adjacency_ok and not single_side_override:
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
        left_dark = bool(left_dark_ratio is not None and left_dark_ratio > cfg.notehead_dark_ratio)
        right_dark = bool(right_dark_ratio is not None and right_dark_ratio > cfg.notehead_dark_ratio)
        reject_notehead = False
        if single_side_override:
            reject_notehead = left_dark and right_dark
        else:
            reject_notehead = left_dark or right_dark
        if reject_notehead and std_intensity >= cfg.notehead_std_floor:
            # Neighbouring regions still contain dense ink (likely noteheads); reject.
            continue
        candidates.append(box)

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
                # Before rejecting, check if the cluster aligns with existing detections.
                # If so, it's likely a valid (but fragmented) barline, not noise.
                is_near_existing = False
                for e_box in existing:
                    e_cx, _ = _centroid(e_box)
                    # The cluster key `key` represents the horizontal center of the bucket.
                    if abs(key - e_cx) < cfg.x_center_tolerance * 2:
                        is_near_existing = True
                        break
                
                if not is_near_existing:
                    # Treat tall multi-staff columns without prior detections as noise.
                    continue
        filtered.extend(bucket_boxes)

    return filtered


__all__ = ["ThinBarlineConfig", "detect_thin_vertical_runs"]
