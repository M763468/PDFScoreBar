"""Map segmentation predictions to the original page coordinates."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import cv2
import numpy as np

from homr.resize import calc_target_image_size

from .types import TransformInfo


def autocrop_bounds(image: np.ndarray) -> Tuple[Tuple[int, int, int, int], bool]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([image], [0], None, [256], [0, 256])
    dominant_color_gray_scale = int(
        max(enumerate(hist), key=lambda x: float(x[1].item() if hasattr(x[1], "item") else x[1]))[0]
    )
    threshold_value = max(dominant_color_gray_scale - 30, 0)
    thresh = cv2.threshold(gray, threshold_value, 255, cv2.THRESH_BINARY)[1]

    kernel = np.ones((7, 7), np.uint8)
    morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    kernel = np.ones((9, 9), np.uint8)
    morph = cv2.morphologyEx(morph, cv2.MORPH_ERODE, kernel)

    contours_tuple = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours_tuple[0] if len(contours_tuple) == 2 else contours_tuple[1]
    area_thresh = 0.0
    big_contour = None
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > area_thresh:
            area_thresh = area
            big_contour = contour

    h, w = image.shape[:2]
    if big_contour is None:
        return (0, 0, w, h), False

    x, y, width, height = cv2.boundingRect(big_contour)
    is_full_page_view = x < w * 0.25 or y < h * 0.25
    if is_full_page_view:
        return (0, 0, w, h), False
    return (x, y, width, height), True


def compute_transform_info(image_path: Path, seg_shape: Tuple[int, int]) -> TransformInfo:
    original = cv2.imread(str(image_path))
    if original is None:
        raise RuntimeError(f"Failed to load image for transform computation: {image_path}")

    crop_box, cropped = autocrop_bounds(original)
    crop_x, crop_y, crop_w, crop_h = crop_box
    if not cropped:
        crop_x = crop_y = 0
        crop_w = original.shape[1]
        crop_h = original.shape[0]

    target_w, target_h = calc_target_image_size(crop_w, crop_h)
    resize_scale_x = target_w / crop_w
    resize_scale_y = target_h / crop_h

    seg_height, seg_width = seg_shape
    seg_scale_x = seg_width / target_w
    seg_scale_y = seg_height / target_h

    return TransformInfo(
        original_shape=(original.shape[1], original.shape[0]),
        crop_box=(crop_x, crop_y, crop_w, crop_h),
        resize_shape=(target_w, target_h),
        seg_shape=(seg_width, seg_height),
        resize_scale=(resize_scale_x, resize_scale_y),
        seg_scale=(seg_scale_x, seg_scale_y),
    )


def map_pred_to_orig(
    box: Tuple[int, int, int, int], transform: TransformInfo
) -> Tuple[int, int, int, int]:
    crop_x, crop_y, *_ = transform.crop_box
    scale_x, scale_y = transform.total_scale
    inv_scale_x = 1.0 / scale_x if scale_x != 0 else 0.0
    inv_scale_y = 1.0 / scale_y if scale_y != 0 else 0.0
    orig_w, orig_h = transform.original_shape

    x1, y1, x2, y2 = box
    x1_orig = int(round(x1 * inv_scale_x + crop_x))
    y1_orig = int(round(y1 * inv_scale_y + crop_y))
    x2_orig = int(round(x2 * inv_scale_x + crop_x))
    y2_orig = int(round(y2 * inv_scale_y + crop_y))

    x1_clamped = max(0, min(orig_w - 1, x1_orig))
    y1_clamped = max(0, min(orig_h - 1, y1_orig))
    x2_clamped = max(0, min(orig_w - 1, x2_orig))
    y2_clamped = max(0, min(orig_h - 1, y2_orig))

    if x2_clamped < x1_clamped:
        x2_clamped = x1_clamped
    if y2_clamped < y1_clamped:
        y2_clamped = y1_clamped

    return (x1_clamped, y1_clamped, x2_clamped, y2_clamped)
