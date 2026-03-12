"""Shared helpers for scale-aware wide-candidate splitting."""

from __future__ import annotations

from typing import Any, Sequence, Tuple

import cv2
import numpy as np

from src.common import Box


def estimate_unit_size_from_box_height(box: Sequence[int | float]) -> float:
    """Approximate unit_size from barline bbox height (staff height ~= 4 * unit)."""
    _, y1, _, y2 = box
    h = max(1.0, abs(float(y2) - float(y1)))
    return max(1.0, h / 4.0)


def extract_x_profile_peaks(
    gray_crop: Any,
    smooth_window: int = 5,
    prominence_ratio: float = 0.15,
    min_peak_distance: int = 3,
) -> list[int]:
    """Find horizontal ink-profile peaks."""
    if np is None or cv2 is None:
        return []
    if gray_crop.size == 0:
        return []
    if len(gray_crop.shape) == 3:
        gray_crop = cv2.cvtColor(gray_crop, cv2.COLOR_BGR2GRAY)
    profile = (255.0 - gray_crop.astype(np.float32)).sum(axis=0)
    if profile.size < 3:
        return []
    if smooth_window > 1:
        k = int(max(1, smooth_window))
        if k % 2 == 0:
            k += 1
        kernel = np.ones(k, dtype=np.float32) / k
        profile = np.convolve(profile, kernel, mode="same")
    pmax = float(profile.max()) if profile.size else 0.0
    if pmax <= 0:
        return []
    threshold = pmax * float(prominence_ratio)
    idxs = []
    for i in range(1, len(profile) - 1):
        if (
            profile[i] >= threshold
            and profile[i] >= profile[i - 1]
            and profile[i] >= profile[i + 1]
        ):
            idxs.append(i)
    if not idxs:
        return []
    idxs = sorted(idxs, key=lambda i: float(profile[i]), reverse=True)
    kept: list[int] = []
    min_dist = int(max(1, min_peak_distance))
    for i in idxs:
        if all(abs(i - j) >= min_dist for j in kept):
            kept.append(i)
    kept.sort()
    return kept


def _clip_box(box: Box, img_w: int, img_h: int) -> Box | None:
    x1, y1, x2, y2 = box
    x1 = max(0, min(img_w - 1, int(round(x1))))
    x2 = max(0, min(img_w, int(round(x2))))
    y1 = max(0, min(img_h - 1, int(round(y1))))
    y2 = max(0, min(img_h, int(round(y2))))
    if x2 <= x1:
        x2 = min(img_w, x1 + 1)
    if y2 <= y1:
        y2 = min(img_h, y1 + 1)
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def split_wide_candidates(
    *,
    boxes: Sequence[Box],
    img: Any,
    min_split_width_unit_ratio: float = 1.0,
    split_box_width_unit_ratio: float = 0.8,
    split_peak_distance_unit_ratio: float = 0.4,
    peak_prominence_ratio: float = 0.15,
    require_exactly_two_peaks: bool = False,
    recenter_single_peak: bool = False,
    emit_merged_two_peak_box: bool = False,
    merged_two_peak_pad_unit_ratio: float = 0.4,
    keep_original_when_not_split: bool = True,
) -> tuple[list[Box], dict[str, int]]:
    """Split wide candidates based on x-profile peaks with configurable behavior."""
    normalized_boxes = [tuple(int(v) for v in b) for b in boxes if len(b) == 4]
    if np is None or cv2 is None:
        return (
            list(normalized_boxes) if keep_original_when_not_split else [],
            {"split_applied": 0, "split_examined": 0},
        )

    img_h, img_w = img.shape[:2]
    out: list[Box] = []
    split_applied = 0
    split_examined = 0

    for box in normalized_boxes:
        x1, y1, x2, y2 = box
        bx1, bx2 = sorted((max(0, x1), min(img_w - 1, x2)))
        by1, by2 = sorted((max(0, y1), min(img_h - 1, y2)))
        if bx2 <= bx1 or by2 <= by1:
            if keep_original_when_not_split:
                out.append(box)
            continue

        unit_size = estimate_unit_size_from_box_height(box)
        min_split_width = max(2, int(round(unit_size * float(min_split_width_unit_ratio))))
        width = abs(x2 - x1)
        if width < min_split_width:
            if keep_original_when_not_split:
                out.append(box)
            continue

        split_examined += 1
        crop = img[by1:by2, bx1:bx2]
        min_peak_distance = max(1, int(round(unit_size * float(split_peak_distance_unit_ratio))))
        peaks = extract_x_profile_peaks(
            crop,
            prominence_ratio=peak_prominence_ratio,
            min_peak_distance=min_peak_distance,
        )

        is_split_case = len(peaks) == 2 if require_exactly_two_peaks else len(peaks) >= 2
        if not is_split_case:
            if recenter_single_peak and len(peaks) == 1:
                px = peaks[0]
                cx = bx1 + int(px)
                new_w = max(2, int(round(unit_size * float(split_box_width_unit_ratio))))
                nb = _clip_box(
                    (
                        int(round(cx - new_w / 2.0)),
                        by1,
                        int(round(cx + new_w / 2.0)),
                        by2,
                    ),
                    img_w,
                    img_h,
                )
                if nb is not None:
                    out.append(nb)
                elif keep_original_when_not_split:
                    out.append(box)
            elif keep_original_when_not_split:
                out.append(box)
            continue

        new_w = max(2, int(round(unit_size * float(split_box_width_unit_ratio))))
        split_boxes: list[Box] = []
        for px in peaks:
            cx = bx1 + int(px)
            nb = _clip_box(
                (
                    int(round(cx - new_w / 2.0)),
                    by1,
                    int(round(cx + new_w / 2.0)),
                    by2,
                ),
                img_w,
                img_h,
            )
            if nb is not None:
                split_boxes.append(nb)

        split_boxes = sorted(set(split_boxes))
        if len(split_boxes) < 2:
            if keep_original_when_not_split:
                out.append(box)
            continue

        print(f"DEBUG: Splitting {box} into {split_boxes}")
        out.extend(split_boxes)
        if emit_merged_two_peak_box and len(peaks) == 2:
            pad = max(1, int(round(unit_size * float(merged_two_peak_pad_unit_ratio))))
            peak_xs = [bx1 + int(px) for px in peaks]
            merged = _clip_box((min(peak_xs) - pad, by1, max(peak_xs) + pad, by2), img_w, img_h)
            if merged is not None:
                out.append(merged)
        split_applied += 1

    return sorted(set(out)), {"split_applied": split_applied, "split_examined": split_examined}
