from __future__ import annotations

import random

import numpy as np
import pytest

from src.common.thin_barline_finder import (
    ThinBarlineConfig,
    _centroid,
    _filter_candidates,
    _find_double_pairs,
    _is_close,
)

Box = tuple[int, int, int, int]


def _legacy_vertical_overlap_ratio(box_a: Box, box_b: Box) -> float:
    top = max(box_a[1], box_b[1])
    bottom = min(box_a[3], box_b[3])
    if bottom <= top:
        return 0.0
    overlap = bottom - top
    height_a = max(box_a[3] - box_a[1], 1)
    height_b = max(box_b[3] - box_b[1], 1)
    return overlap / float(max(height_a, height_b))


def _legacy_find_double_pairs(merged: list[Box], cfg: ThinBarlineConfig) -> set[Box]:
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
            overlap = _legacy_vertical_overlap_ratio(a, b)
            if overlap < cfg.double_pair_min_overlap:
                continue
            if min(a[3] - a[1], b[3] - b[1]) < cfg.double_pair_min_height:
                continue
            if max(a[2] - a[0], b[2] - b[0]) > cfg.double_pair_max_width:
                continue
            paired_boxes.add(a)
            paired_boxes.add(b)
    return paired_boxes


def _legacy_filter_candidates(
    image: np.ndarray,
    merged: list[Box],
    paired_boxes: set[Box],
    existing: list[Box],
    cfg: ThinBarlineConfig,
) -> list[Box]:
    _, width = image.shape
    candidates: list[Box] = []
    for box in merged:
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
        roi = image[y1:y2, x1:x2]
        if roi.size == 0:
            continue
        mean_intensity = float(np.mean(roi))
        if mean_intensity >= cfg.pixel_threshold:
            continue
        left = image[y1:y2, max(0, x1 - 3) : x1]
        right = image[y1:y2, x2 : min(width, x2 + 3)]
        if left.size == 0 or right.size == 0:
            continue

        def window_metrics(window: np.ndarray) -> tuple[float | None, float | None]:
            if window.size == 0:
                return None, None
            mean = float(np.mean(window))
            ratio = float(np.count_nonzero(window < cfg.dark_pixel_threshold)) / window.size
            return mean, ratio

        left_mean, left_dark_ratio = window_metrics(left)
        right_mean, right_dark_ratio = window_metrics(right)

        def relaxed_metrics(is_left: bool) -> tuple[float | None, float | None]:
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
            return window_metrics(window)

        left_ok = left_mean is not None and left_mean >= cfg.adjacent_min_intensity
        if not left_ok:
            relaxed_mean, relaxed_dark = relaxed_metrics(True)
            if (
                relaxed_mean is not None
                and relaxed_mean >= cfg.adjacent_min_intensity
                and (relaxed_dark is None or relaxed_dark <= cfg.adjacent_relaxed_dark_ratio)
            ):
                left_ok = True

        right_ok = right_mean is not None and right_mean >= cfg.adjacent_min_intensity
        if not right_ok:
            relaxed_mean, relaxed_dark = relaxed_metrics(False)
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
        reject_notehead = (
            left_dark and right_dark if single_side_override else left_dark or right_dark
        )
        if reject_notehead and std_intensity >= cfg.notehead_std_floor:
            continue
        candidates.append(box)
    return candidates


@pytest.mark.parametrize("seed", range(12))
def test_double_pair_sweep_matches_legacy(seed: int) -> None:
    rng = random.Random(seed)
    merged: list[Box] = []
    for _ in range(250):
        x1 = rng.randrange(0, 140)
        width = rng.randrange(1, 9)
        y1 = rng.randrange(0, 180)
        height = rng.randrange(10, 70)
        merged.append((x1, y1, x1 + width, y1 + height))
    merged.sort()
    cfg = ThinBarlineConfig()

    assert _find_double_pairs(merged, cfg=cfg) == _legacy_find_double_pairs(merged, cfg)


@pytest.mark.parametrize("seed", range(10))
def test_batched_candidate_filter_matches_legacy(seed: int) -> None:
    rng = np.random.default_rng(seed)
    image = rng.integers(0, 256, size=(220, 260), dtype=np.uint8)
    cfg = ThinBarlineConfig(left_margin_limit=0)

    merged: list[Box] = []
    for _ in range(180):
        x1 = int(rng.integers(1, image.shape[1] - 7))
        width = int(rng.integers(1, 5))
        y1 = int(rng.integers(0, image.shape[0] - 35))
        height = int(rng.integers(17, 34))
        merged.append((x1, y1, x1 + width, y1 + height))
    merged.sort()

    paired_boxes = {box for index, box in enumerate(merged) if index % 7 == 0}
    existing = [merged[index] for index in range(0, len(merged), 41)]

    assert _filter_candidates(
        image,
        merged,
        paired_boxes,
        existing,
        cfg=cfg,
    ) == _legacy_filter_candidates(image, merged, paired_boxes, existing, cfg)
