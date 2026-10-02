"""Generate barline candidates from segmentation masks and image features.

Candidate generation only: staff assembly, filtering, prediction, and evaluation
remain with their callers. Thresholds and HOMR bounding-box settings preserve the
existing core heuristics contract.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

from homr.bar_line_detection import prepare_bar_line_image
from homr.bounding_boxes import create_rotated_bounding_boxes


def _ensure_mask_shape(mask: np.ndarray, target_shape: Tuple[int, int]) -> np.ndarray:
    if mask.shape[:2] == target_shape:
        return mask
    return cv2.resize(mask, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_NEAREST)


def generate_vertical_run_candidates(
    preprocessed: np.ndarray,
    staff_mask: Optional[np.ndarray],
    *,
    min_run: int = 20,
    dark_threshold: int = 80,
) -> List[Any]:
    gray = cv2.cvtColor(preprocessed, cv2.COLOR_BGR2GRAY)
    dark = (gray < dark_threshold).astype(np.uint8) * 255
    if staff_mask is not None:
        staff_mask = _ensure_mask_shape(staff_mask, gray.shape[:2])
        masked = cv2.bitwise_and(dark, dark, mask=(staff_mask > 0).astype(np.uint8))
    else:
        masked = dark
    kernel = np.ones((min_run, 1), np.uint8)
    vertical = cv2.morphologyEx(masked, cv2.MORPH_OPEN, kernel)
    return create_rotated_bounding_boxes(vertical, skip_merging=True, min_size=(1, min_run))


def generate_vertical_run_candidates_weak(
    preprocessed: np.ndarray,
    staff_mask: Optional[np.ndarray],
) -> List[Any]:
    return generate_vertical_run_candidates(
        preprocessed,
        staff_mask,
        min_run=10,
        dark_threshold=130,
    )


def generate_barline_cc_relaxed(stems_rest_mask: np.ndarray) -> List[Any]:
    bar_line_img = prepare_bar_line_image(stems_rest_mask)
    return create_rotated_bounding_boxes(bar_line_img, skip_merging=True, min_size=(1, 3))


def generate_barline_cc_dilated(stems_rest_mask: np.ndarray) -> List[Any]:
    bar_line_img = prepare_bar_line_image(stems_rest_mask)
    kernel = np.ones((5, 1), np.uint8)
    dilated = cv2.dilate(bar_line_img, kernel, iterations=1)
    return create_rotated_bounding_boxes(dilated, skip_merging=True, min_size=(1, 3))


def generate_barline_cc_tiny(stems_rest_mask: np.ndarray) -> List[Any]:
    bar_line_img = prepare_bar_line_image(stems_rest_mask)
    return create_rotated_bounding_boxes(bar_line_img, skip_merging=True, min_size=(1, 1))


def generate_sobel_vertical_candidates(
    preprocessed: np.ndarray,
    staff_mask: Optional[np.ndarray],
    *,
    sobel_threshold: int = 60,
    min_run: int = 15,
) -> List[Any]:
    gray = cv2.cvtColor(preprocessed, cv2.COLOR_BGR2GRAY)
    sobelx = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3)
    absx = cv2.convertScaleAbs(sobelx)
    edges = (absx > sobel_threshold).astype(np.uint8) * 255
    if staff_mask is not None:
        staff_mask = _ensure_mask_shape(staff_mask, gray.shape[:2])
        masked = cv2.bitwise_and(edges, edges, mask=(staff_mask > 0).astype(np.uint8))
    else:
        masked = edges
    kernel = np.ones((min_run, 1), np.uint8)
    vertical = cv2.morphologyEx(masked, cv2.MORPH_OPEN, kernel)
    return create_rotated_bounding_boxes(vertical, skip_merging=True, min_size=(1, min_run))


def generate_sobel_vertical_candidates_weak(
    preprocessed: np.ndarray,
    staff_mask: Optional[np.ndarray],
) -> List[Any]:
    return generate_sobel_vertical_candidates(
        preprocessed,
        staff_mask,
        sobel_threshold=40,
        min_run=10,
    )


def generate_column_sum_candidates(
    preprocessed: np.ndarray,
    staff_mask: Optional[np.ndarray],
    *,
    min_column_sum: int = 20,
    dark_threshold: int = 120,
) -> List[Any]:
    gray = cv2.cvtColor(preprocessed, cv2.COLOR_BGR2GRAY)
    dark = (gray < dark_threshold).astype(np.uint8) * 255
    if staff_mask is not None:
        staff_mask = _ensure_mask_shape(staff_mask, gray.shape[:2])
        masked = cv2.bitwise_and(dark, dark, mask=(staff_mask > 0).astype(np.uint8))
    else:
        masked = dark
    col_counts = (masked > 0).sum(axis=0)
    active = col_counts >= min_column_sum
    if not np.any(active):
        return []
    vertical = np.zeros_like(masked)
    vertical[:, active] = masked[:, active]
    return create_rotated_bounding_boxes(vertical, skip_merging=True, min_size=(1, min_column_sum))


def generate_hough_vertical_candidates(
    preprocessed: np.ndarray,
    staff_mask: Optional[np.ndarray],
    *,
    canny_low: int = 50,
    canny_high: int = 150,
    hough_threshold: int = 50,
    min_line_length: int = 25,
    max_line_gap: int = 6,
    max_dx_ratio: float = 0.15,
) -> List[Any]:
    gray = cv2.cvtColor(preprocessed, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, canny_low, canny_high)
    if staff_mask is not None:
        staff_mask = _ensure_mask_shape(staff_mask, gray.shape[:2])
        edges = cv2.bitwise_and(edges, edges, mask=(staff_mask > 0).astype(np.uint8))
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180.0,
        threshold=hough_threshold,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )
    if lines is None:
        return []
    line_mask = np.zeros_like(edges)
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        dy = y2 - y1
        dx = x2 - x1
        if abs(dy) < min_line_length:
            continue
        if abs(dx) > max(2, int(abs(dy) * max_dx_ratio)):
            continue
        cv2.line(line_mask, (x1, y1), (x2, y2), 255, 1)
    return create_rotated_bounding_boxes(
        line_mask, skip_merging=True, min_size=(1, min_line_length)
    )
