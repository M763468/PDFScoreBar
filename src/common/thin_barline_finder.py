"""Heuristics for recovering thin vertical barlines missed by primary detectors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import cv2
import numpy as np

from src.common import Box


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

    The original implementation walked every image pixel in Python.  This is
    mechanically equivalent run-boundary detection performed in NumPy.  The
    downstream merge/filter logic remains unchanged, so this helper must retain
    the exact ``(x, y_start, y_end)`` ordering and relaxed-height semantics.
    """

    if binary.ndim != 2:
        raise ValueError(f"Thin-barline binary image must be 2-D, got {binary.shape}")
    if max_height < 1:
        return []

    min_height_relaxed = max(min_height - 1, 1)

    # ``binary`` is 0/1 today, but use truthiness to preserve the old
    # ``while column[y]`` behavior if the representation changes later.  Work
    # in (x, y) order so np.nonzero emits the same ordering as the legacy
    # outer-x / inner-y scan.
    active_xy = np.asarray(binary != 0, dtype=np.int8).T
    padded = np.pad(active_xy, ((0, 0), (1, 1)), mode="constant")
    transitions = np.diff(padded, axis=1)

    start_x, start_y = np.nonzero(transitions == 1)
    end_x, end_y = np.nonzero(transitions == -1)
    if start_x.size == 0:
        return []
    if start_x.shape != end_x.shape or not np.array_equal(start_x, end_x):
        raise RuntimeError("Unbalanced thin-barline vertical run transitions")

    run_heights = end_y - start_y
    keep = (run_heights >= min_height_relaxed) & (run_heights <= max_height)
    return [
        (int(x), int(y1), int(y2)) for x, y1, y2 in zip(start_x[keep], start_y[keep], end_y[keep])
    ]


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
    _, width = binary.shape

    runs = _extract_vertical_runs(
        binary,
        min_height=cfg.min_height,
        max_height=cfg.max_height,
    )

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

    def _vertical_overlap_ratio(box_a: Box, box_b: Box) -> float:
        top = max(box_a[1], box_b[1])
        bottom = min(box_a[3], box_b[3])
        if bottom <= top:
            return 0.0
        overlap = bottom - top
        height_a = max(box_a[3] - box_a[1], 1)
        height_b = max(box_b[3] - box_b[1], 1)
        return overlap / float(max(height_a, height_b))

    paired_boxes: set[Box] = set()
    for i in range(len(merged) - 1):
        a = merged[i]
        for j in range(i + 1, len(merged)):
            b = merged[j]
            gap = b[0] - a[2] if a[2] <= b[0] else a[0] - b[2]
            if gap <= 0:
                continue
            if gap > cfg.double_pair_max_gap:
                break
            overlap = _vertical_overlap_ratio(a, b)
            if overlap < cfg.double_pair_min_overlap:
                continue
            if min(a[3] - a[1], b[3] - b[1]) < cfg.double_pair_min_height:
                continue
            if max(a[2] - a[0], b[2] - b[0]) > cfg.double_pair_max_width:
                continue
            paired_boxes.add(a)
            paired_boxes.add(b)

    existing = list(existing_boxes)
    candidates: List[Box] = []
    for box in merged:
        x1, y1, x2, y2 = box
        box_width = x2 - x1
        box_height = y2 - y1

        # 1. Tighten Height Thresholds: Reject very short vertical fragments for W=1.
        # Restrict min_height_relaxed so it is only applied when width >= 2.
        if box_width < 2 and box_height < cfg.min_height:
            continue

        if box not in paired_boxes and _is_close(box, existing, cfg=cfg):
            continue

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

        # 3. Light Stem-Suppression Heuristic
        # If W=1 AND one side is significantly darker (notehead-side),
        # AND height is relatively short (e.g. < 20), reject.
        if single_side_override and box_width == 1 and box_height < 20:
            continue

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
        right_dark = bool(
            right_dark_ratio is not None and right_dark_ratio > cfg.notehead_dark_ratio
        )
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
                else:
                    # 2. Refine Cluster Guard Rescue Logic
                    # If rescuing, only keep "strong" candidates to avoid rescuing noise.
                    # Criteria: Height >= 20 OR very low std dev (clean line).
                    rescued_boxes = []
                    for box in bucket_boxes:
                        h = box[3] - box[1]
                        # Calculate std again or assume it passed earlier checks.
                        # We don't have std here easily without re-calculating.
                        # Let's rely on height as requested.
                        if h >= 20:
                            rescued_boxes.append(box)
                        else:
                            # Optional: check std if we want to be fancy, but let's stick to height for now.
                            # We can re-calculate std if needed, but it's expensive.
                            # Let's trust the height heuristic.
                            pass
                    bucket_boxes = rescued_boxes
                    if not bucket_boxes:
                        continue

        filtered.extend(bucket_boxes)

    return filtered


__all__ = ["ThinBarlineConfig", "detect_thin_vertical_runs"]
