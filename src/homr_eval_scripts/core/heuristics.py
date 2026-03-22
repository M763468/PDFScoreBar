#!/usr/bin/env python3
from __future__ import annotations

import collections
import csv
import logging
import sys
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


from homr import constants
from homr.bar_line_detection import prepare_bar_line_image
from homr.bounding_boxes import create_rotated_bounding_boxes
from homr.brace_dot_detection import (
    find_braces_brackets_and_grand_staff_lines,
    prepare_brace_dot_image,
)
from homr.main import ProcessingConfig, load_and_preprocess_predictions, predict_symbols
from homr.note_detection import add_notes_to_staffs, combine_noteheads_with_stems
from homr.resize import calc_target_image_size
from homr.staff_detection import break_wide_fragments, detect_staff
from homr.title_detection import detect_title

REPO_ROOT = Path(__file__).resolve().parents[2]
if __name__ != "__main__":
    REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
_HOMR_CANDIDATES = (REPO_ROOT / "homr", REPO_ROOT / "external" / "homr")
HOMR_REPO = next((p for p in _HOMR_CANDIDATES if (p / "homr").exists()), _HOMR_CANDIDATES[1])
JST = ZoneInfo("Asia/Tokyo")

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

logger = logging.getLogger("homr_evaluator")

from src.homr_eval_scripts.core.metrics import BarlinePrediction
from src.homr_eval_scripts.core.utils import Box, TransformInfo, eprint


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


def detect_staffs_with_barlines(
    image_path: str,
    config: ProcessingConfig,
    tuning: Dict[str, float],
    use_gpu_inference: bool,
) -> Tuple[List[Any], np.ndarray, Any, Future[str], List[Any], np.ndarray, np.ndarray]:
    """
    Runs the core homr staff and symbol detection pipeline.

    Returns:
        A tuple containing the multi-staffs, preprocessed image, debug object,
        title future, detected bar line boxes, the notehead prediction mask,
        and the staff prediction mask.
    """
    predictions, debug = load_and_preprocess_predictions(
        image_path, config.enable_debug, config.enable_cache, use_gpu_inference
    )
    symbols = predict_symbols(debug, predictions)

    extra_bar_lines: List[Any] = []
    if tuning.get("gen_vertical_run"):
        extra_bar_lines.extend(
            generate_vertical_run_candidates(predictions.preprocessed, predictions.staff)
        )
    if tuning.get("gen_vertical_run_weak"):
        extra_bar_lines.extend(
            generate_vertical_run_candidates_weak(predictions.preprocessed, predictions.staff)
        )
    if tuning.get("gen_barline_cc_relaxed"):
        extra_bar_lines.extend(generate_barline_cc_relaxed(predictions.stems_rest))
    if tuning.get("gen_barline_cc_dilated"):
        extra_bar_lines.extend(generate_barline_cc_dilated(predictions.stems_rest))
    if tuning.get("gen_sobel_vertical"):
        extra_bar_lines.extend(
            generate_sobel_vertical_candidates(predictions.preprocessed, predictions.staff)
        )
    if tuning.get("gen_sobel_vertical_weak"):
        extra_bar_lines.extend(
            generate_sobel_vertical_candidates_weak(predictions.preprocessed, predictions.staff)
        )
    if tuning.get("gen_column_sum_staff"):
        extra_bar_lines.extend(
            generate_column_sum_candidates(predictions.preprocessed, predictions.staff)
        )
    if tuning.get("gen_column_sum_weak"):
        extra_bar_lines.extend(
            generate_column_sum_candidates(
                predictions.preprocessed,
                predictions.staff,
                min_column_sum=12,
                dark_threshold=140,
            )
        )
    if tuning.get("gen_hough_vertical"):
        extra_bar_lines.extend(
            generate_hough_vertical_candidates(predictions.preprocessed, predictions.staff)
        )
    if tuning.get("gen_hough_vertical_weak"):
        extra_bar_lines.extend(
            generate_hough_vertical_candidates(
                predictions.preprocessed,
                predictions.staff,
                canny_low=30,
                canny_high=120,
                hough_threshold=30,
                min_line_length=15,
                max_line_gap=8,
                max_dx_ratio=0.2,
            )
        )
    if tuning.get("gen_vertical_run_no_staff"):
        extra_bar_lines.extend(generate_vertical_run_candidates(predictions.preprocessed, None))
    if tuning.get("gen_barline_cc_tiny"):
        extra_bar_lines.extend(generate_barline_cc_tiny(predictions.stems_rest))
    if tuning.get("gen_sobel_no_staff"):
        extra_bar_lines.extend(generate_sobel_vertical_candidates(predictions.preprocessed, None))
    if tuning.get("gen_column_sum_no_staff"):
        extra_bar_lines.extend(generate_column_sum_candidates(predictions.preprocessed, None))
    if extra_bar_lines:
        symbols.bar_lines.extend(extra_bar_lines)
        debug.write_bounding_boxes_alternating_colors("bar_lines_extra", extra_bar_lines)
        eprint(f"Added {len(extra_bar_lines)} extra bar line candidates")

    # The notehead and staff masks are crucial for context-based filtering.
    # The `predictions` object from load_and_preprocess_predictions contains the raw numpy arrays.
    notehead_mask = predictions.notehead
    staff_mask = predictions.staff

    symbols.staff_fragments = break_wide_fragments(symbols.staff_fragments)
    debug.write_bounding_boxes("staff_fragments", symbols.staff_fragments)
    eprint("Found " + str(len(symbols.staff_fragments)) + " staff line fragments")

    noteheads_with_stems = combine_noteheads_with_stems(symbols.noteheads, symbols.stems_rest)
    debug.write_bounding_boxes_alternating_colors("notehead_with_stems", noteheads_with_stems)
    eprint("Found " + str(len(noteheads_with_stems)) + " noteheads")
    if len(noteheads_with_stems) == 0:
        raise RuntimeError("No noteheads found")

    average_note_head_height = float(
        np.median([notehead.notehead.size[1] for notehead in noteheads_with_stems])
    )
    eprint("Average note head height: " + str(average_note_head_height))

    all_noteheads = [notehead.notehead for notehead in noteheads_with_stems]
    all_stems = [note.stem for note in noteheads_with_stems if note.stem is not None]
    bar_lines_or_rests = [
        line
        for line in symbols.bar_lines
        if not line.is_overlapping_with_any(all_noteheads)
        and not line.is_overlapping_with_any(all_stems)
    ]

    staff_overlap_min = tuning.get("barline_staff_overlap_min", 0.0)
    edge_margin_x = int(tuning.get("barline_edge_margin_x", 0))
    edge_margin_y = int(tuning.get("barline_edge_margin_y", 0))
    if staff_overlap_min > 0.0 or edge_margin_x > 0 or edge_margin_y > 0:
        filtered_lines = []
        dropped = 0
        mask_h = staff_mask.shape[0] if staff_mask is not None else 0
        mask_w = staff_mask.shape[1] if staff_mask is not None else 0
        for line in bar_lines_or_rests:
            x1, y1, x2, y2 = map(int, line.to_bounding_box().box)
            if edge_margin_x > 0 and mask_w > 0:
                if x1 < edge_margin_x or x2 > (mask_w - edge_margin_x):
                    dropped += 1
                    continue
            if edge_margin_y > 0 and mask_h > 0:
                if y1 < edge_margin_y or y2 > (mask_h - edge_margin_y):
                    dropped += 1
                    continue
            if staff_overlap_min > 0.0 and staff_mask is not None:
                x1c = max(0, min(mask_w, x1))
                x2c = max(0, min(mask_w, x2))
                y1c = max(0, min(mask_h, y1))
                y2c = max(0, min(mask_h, y2))
                if x2c <= x1c or y2c <= y1c:
                    dropped += 1
                    continue
                area = (x2c - x1c) * (y2c - y1c)
                overlap = int(staff_mask[y1c:y2c, x1c:x2c].sum())
                ratio = overlap / float(area) if area > 0 else 0.0
                if ratio < staff_overlap_min:
                    dropped += 1
                    continue
            filtered_lines.append(line)
        bar_lines_or_rests = filtered_lines
        eprint(
            f"Barline staff-overlap/edge filter kept {len(bar_lines_or_rests)} candidates, "
            f"dropped {dropped}"
        )

    min_height_factor = tuning.get("barline_min_height_factor", 1.0)
    max_width_factor = tuning.get("barline_max_width_factor", 1.0)
    min_height_threshold = min_height_factor * constants.bar_line_min_height(
        average_note_head_height
    )
    max_width_threshold = max_width_factor * constants.bar_line_max_width(average_note_head_height)

    bar_line_boxes = []
    for line in bar_lines_or_rests:
        if line.size[1] < min_height_threshold:
            continue
        if line.size[0] > max_width_threshold:
            continue
        bar_line_boxes.append(line)
    debug.write_bounding_boxes_alternating_colors("bar_lines", bar_line_boxes)

    debug.write_bounding_boxes(
        "anchor_input", symbols.staff_fragments + bar_line_boxes + symbols.clefs_keys
    )
    staffs = detect_staff(
        debug, predictions.staff, symbols.staff_fragments, symbols.clefs_keys, bar_line_boxes
    )
    if len(staffs) == 0:
        raise RuntimeError("No staffs found")

    title_future = detect_title(debug, staffs[0])
    debug.write_bounding_boxes_alternating_colors("staffs", staffs)

    brace_dot_img = prepare_brace_dot_image(predictions.symbols, predictions.staff)
    debug.write_threshold_image("brace_dot", brace_dot_img)
    brace_dot = create_rotated_bounding_boxes(brace_dot_img, skip_merging=True, max_size=(100, -1))

    notes = add_notes_to_staffs(
        staffs, noteheads_with_stems, predictions.symbols, predictions.notehead
    )

    multi_staffs = find_braces_brackets_and_grand_staff_lines(debug, staffs, brace_dot)
    eprint(
        "Found",
        len(multi_staffs),
        "connected staffs (after merging grand staffs, multiple voices): ",
        [len(staff.staffs) for staff in multi_staffs],
    )
    debug.write_all_bounding_boxes_alternating_colors("notes", multi_staffs, notes)

    return (
        multi_staffs,
        predictions.preprocessed,
        debug,
        title_future,
        bar_line_boxes,
        notehead_mask,
        staff_mask,
    )


def filter_detections_by_notehead_proximity(
    detections: List[BarlinePrediction],
    notehead_mask: np.ndarray,
    proximity_threshold_px: int,
    min_overlap_px: int,
    max_height_px: int,
    max_width_px: int,
    staff_mask: Optional[np.ndarray] = None,
    min_staff_crossings: int = 0,
    check_staff_crossing: bool = False,
) -> Tuple[List[BarlinePrediction], List[BarlinePrediction]]:
    """
    Filters barline detections that are horizontally close to noteheads, which
    are likely to be stems.

    This heuristic is designed to be conservative to avoid creating False Negatives.
    It only rejects a candidate if it matches ALL of the following:
      1. Within `proximity_threshold_px` of a notehead.
      2. Pixel overlap with notehead mask >= `min_overlap_px`.
      3. Height < `max_height_px` (short stems).
      4. Width < `max_width_px` (thin stems).

    Args:
        detections: List of detected barline boxes in original image coordinates.
        notehead_mask: Binary (0/255) or (0/1) mask of notehead locations in original image coordinates.
        proximity_threshold_px: The horizontal distance in pixels to check for noteheads.
        min_overlap_px: Minimum intersection area to consider a rejection.
        max_height_px: Maximum height to consider a rejection.
        max_width_px: Maximum width to consider a rejection.

        check_staff_crossing: If True, `staff_mask` and `min_staff_crossings` are used to reject low-crossing candidates.
        staff_mask: Binary (0/255) mask of staff lines. Required if `check_staff_crossing` is True.
        min_staff_crossings: Minimum crossings required to KEEP a candidate IF overlap is low.

    Returns:
        A tuple containing (kept_detections, rejected_detections).
    """
    kept_detections = []
    rejected_detections = []
    mask_h, mask_w = notehead_mask.shape

    for pred in detections:
        x1, y1, x2, y2 = pred.orig_bbox
        width = x2 - x1
        height = y2 - y1

        # Check dimensions first (fastest)
        # Note: These criteria are for REJECTION.
        # Original Heuristic 1 ("Safe Filter"):
        # REJECT if (Dist < 5) AND (Height < 24) AND (Width < 4) AND (Overlap >= 5)

        # Dimensions check allows us to skip Heuristic 1 if dimensions don't match FP profile
        is_small_candidate = (height < max_height_px) and (width < max_width_px)

        # Define a horizontal search window around the detection
        search_x1 = max(0, x1 - proximity_threshold_px)
        search_x2 = min(mask_w, x2 + proximity_threshold_px)

        # Clamp vertical coordinates to mask boundaries
        y1_clamped = max(0, min(mask_h, y1))
        y2_clamped = max(0, min(mask_h, y2))

        if y1_clamped >= y2_clamped or search_x1 >= search_x2:
            kept_detections.append(pred)
            continue

        # Extract regions
        box_x1 = max(0, min(mask_w, x1))
        box_x2 = max(0, min(mask_w, x2))

        # Proximity check window
        search_window = notehead_mask[y1_clamped:y2_clamped, search_x1:search_x2]
        is_proximal = np.any(search_window)

        if not is_proximal:
            kept_detections.append(pred)
            continue

        # Overlap check
        if box_x1 >= box_x2:
            overlap_area = 0
        else:
            box_window = notehead_mask[y1_clamped:y2_clamped, box_x1:box_x2]
            overlap_area = np.count_nonzero(box_window)

        # --- Heuristic 1: Safe Filter (Small + High Overlap) ---
        if is_small_candidate and overlap_area >= min_overlap_px:
            rejected_detections.append(pred)
            continue

        # --- Heuristic 2: Staff-Crossing Validation (Low Overlap + Low Crossing) ---
        # Only check if it wasn't already rejected by Heuristic 1, and heuristic 2 IS enabled.
        # Note: We are currently inside a block where is_proximal is True.
        # Heuristic 2 targets candidates that have LOW overlap (< min_overlap_px) but ARE proximal.

        if check_staff_crossing and staff_mask is not None and overlap_area < min_overlap_px:
            num_crossings = count_staff_crossings(pred.orig_bbox, staff_mask)
            if num_crossings < min_staff_crossings:
                rejected_detections.append(pred)
                continue

        kept_detections.append(pred)

    return kept_detections, rejected_detections


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

        x_bin_width = 8
        min_bin_count = 2
        max_x_gap_px = 40
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

        if any(abs(((box[0] + box[2]) / 2.0) - x_ref) <= x_tolerance_px for box in cluster_boxes):
            continue

        candidate = _scan_vertical_line(
            gray,
            y_top,
            y_bottom,
            x_ref,
            search_half_width=search_half_width,
            dark_threshold=120,
            min_dark_ratio=0.5,
            right_band_px=4,
            right_dark_ratio_max=0.25,
            line_width=2,
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


def count_staff_crossings(
    bbox: Tuple[int, int, int, int],
    staff_mask: np.ndarray,
) -> int:
    """
    Counts the number of staff line crossings for a vertical barline candidate.

    A "crossing" is defined as a transition from background -> staff -> background
    along the vertical slice at the candidate's x-coordinate.

    Args:
        bbox: Bounding box (x1, y1, x2, y2) in original image coordinates.
        staff_mask: Binary (0/255) staff mask in original image coordinates.

    Returns:
        Number of distinct staff line crossings.
    """
    x1, y1, x2, y2 = bbox
    mask_h, mask_w = staff_mask.shape

    # Use center x-coordinate
    cx = (x1 + x2) // 2
    if cx < 0 or cx >= mask_w:
        return 0

    # Clamp y range
    y1_clamped = max(0, min(mask_h, y1))
    y2_clamped = max(0, min(mask_h, y2))

    if y1_clamped >= y2_clamped:
        return 0

    # Extract vertical slice
    vertical_slice = staff_mask[y1_clamped:y2_clamped, cx]

    # Binarize (in case it's 0/1 instead of 0/255)
    binary_slice = (vertical_slice > 0).astype(np.uint8)

    # Count transitions: 0->1 (entering staff line)
    # A crossing is a contiguous run of 1s
    crossings = 0
    in_staff = False

    for val in binary_slice:
        if val == 1 and not in_staff:
            crossings += 1
            in_staff = True
        elif val == 0:
            in_staff = False

    return crossings

    return crossings


def resolve_clusters_dry_run(
    predictions: List[BarlinePrediction],
    notehead_mask: np.ndarray,
    stem: str,
    output_dir: Path,
    base_gap_threshold: int = 15,
) -> None:
    """
    Dry-run implementation of Cluster Resolution Heuristic.
    Groups barline candidates by proximity and determines which ones WOULD be removed.
    Writes decisions to candidate_clusters.csv.

    Logic:
    1. Group by Staff.
    2. Cluster by horizontal distance (gap <= 15px).
    3. Score each candidate (Strength = Height + Overlap*2).
    4. Resolve:
       - Tight (<4px): Keep Best (Duplicate).
       - Medium (4-15px): Keep Both if Double Barline (Strong+Strong), else Keep Strongest.
    """
    mask_h, mask_w = notehead_mask.shape

    # 1. Group by Staff
    grouped = collections.defaultdict(list)
    for idx, pred in enumerate(predictions):
        key = (pred.system_index, pred.staff_index)
        grouped[key].append((idx, pred))

    cluster_rows = []

    for (sys_idx, staff_idx), items in grouped.items():
        # Sort by x-center
        items.sort(key=lambda item: (item[1].orig_bbox[0] + item[1].orig_bbox[2]) / 2)

        # 2. Form Clusters
        clusters = []
        if not items:
            continue

        current_cluster = [items[0]]

        for i in range(1, len(items)):
            prev = items[i - 1][1]
            curr = items[i][1]

            prev_cx = (prev.orig_bbox[0] + prev.orig_bbox[2]) / 2
            curr_cx = (curr.orig_bbox[0] + curr.orig_bbox[2]) / 2
            gap = curr_cx - prev_cx

            if gap <= base_gap_threshold:
                current_cluster.append(items[i])
            else:
                clusters.append(current_cluster)
                current_cluster = [items[i]]
        clusters.append(current_cluster)

        # 3. Resolve Clusters
        for c_id, cluster in enumerate(clusters):
            # Calculate scores for all in cluster
            scored_cluster = []
            for original_idx, pred in cluster:
                x1, y1, x2, y2 = pred.orig_bbox
                h = y2 - y1

                # Re-calculate overlap (expensive but necessary if not passed)
                # Optimization: Could pass pre-computed stats, but for dry run this is fine.
                y1_c = max(0, min(mask_h, y1))
                y2_c = max(0, min(mask_h, y2))
                x1_c = max(0, min(mask_w, x1))
                x2_c = max(0, min(mask_w, x2))

                if x1_c >= x2_c or y1_c >= y2_c:
                    overlap_area = 0.0
                else:
                    box_window = notehead_mask[y1_c:y2_c, x1_c:x2_c]
                    overlap_area = float(np.count_nonzero(box_window))

                # SCORE FORMULA
                score = float(h) + (overlap_area * 2.0)
                scored_cluster.append(
                    {
                        "pred": pred,
                        "idx": original_idx,
                        "score": score,
                        "height": h,
                        "overlap": overlap_area,
                        "decision": "KEEP",  # Default
                        "reason": "SOLITARY" if len(cluster) == 1 else "BEST",
                    }
                )

            # Resolution Logic
            if len(scored_cluster) > 1:
                # Sort by Score Descending
                scored_cluster.sort(key=lambda x: x["score"], reverse=True)
                primary = scored_cluster[0]
                primary["decision"] = "KEEP"
                primary["reason"] = "BEST"

                prim_cx = (primary["pred"].orig_bbox[0] + primary["pred"].orig_bbox[2]) / 2

                for secondary in scored_cluster[1:]:
                    sec_cx = (secondary["pred"].orig_bbox[0] + secondary["pred"].orig_bbox[2]) / 2
                    dist = abs(sec_cx - prim_cx)

                    if dist < 4.0:
                        # TIGHT CLUSTER -> Duplicate -> Remove Weaker
                        secondary["decision"] = "REMOVE"
                        secondary["reason"] = "DUPLICATE"
                    else:
                        # MEDIUM CLUSTER (4-15px) -> Potential Double Barline
                        # Check Strength Profile
                        # Double Barline Candidates passed Safe Filter, so H>=24 or Ov>=5 if small.
                        # Score Threshold: > 25 (e.g. H=25, Ov=0 OR H=15, Ov=5 -> Score 25)

                        is_strong = secondary["score"] > 25.0
                        primary_is_strong = primary["score"] > 25.0

                        if is_strong and primary_is_strong:
                            secondary["decision"] = "KEEP"
                            secondary["reason"] = "DOUBLE_BARLINE"
                        else:
                            secondary["decision"] = "REMOVE"
                            secondary["reason"] = "WEAK_NEIGHBOR"

            # 4. Log Decisions
            for item in scored_cluster:
                cluster_rows.append(
                    {
                        "image": stem,
                        "pred_index": item["idx"],
                        "cluster_id": c_id,
                        "x_center": (item["pred"].orig_bbox[0] + item["pred"].orig_bbox[2]) / 2,
                        "score": item["score"],
                        "height": item["height"],
                        "overlap": item["overlap"],
                        "decision": item["decision"],
                        "reason": item["reason"],
                    }
                )

    # Save CSV
    csv_path = output_dir / f"{stem}_candidate_clusters.csv"
    if not cluster_rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "image",
            "pred_index",
            "cluster_id",
            "x_center",
            "score",
            "height",
            "overlap",
            "decision",
            "reason",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cluster_rows)


def resolve_tight_duplicates_dry_run(
    predictions: List[BarlinePrediction],
    notehead_mask: np.ndarray,
    stem: str,
    output_dir: Path,
) -> None:
    """
    Phase 12: Tight Duplicate Merging (Dry Run).
    Groups candidates on same staff with gap <= 3px AND Vertical IoU >= 0.5.
    Keeps the Strongest. Output to tight_duplicates_candidates.csv.
    """
    mask_h, mask_w = notehead_mask.shape

    # 1. Group by Staff
    grouped = collections.defaultdict(list)
    for idx, pred in enumerate(predictions):
        key = (pred.system_index, pred.staff_index)
        grouped[key].append((idx, pred))

    rows = []

    for (sys_idx, staff_idx), items in grouped.items():
        # Sort by x-center
        items.sort(key=lambda item: (item[1].orig_bbox[0] + item[1].orig_bbox[2]) / 2)

        # 2. Form Clusters (Gap <= 3px)
        clusters = []
        if not items:
            continue

        current_cluster = [items[0]]

        for i in range(1, len(items)):
            prev = items[i - 1][1]
            curr = items[i][1]

            prev_cx = (prev.orig_bbox[0] + prev.orig_bbox[2]) / 2
            curr_cx = (curr.orig_bbox[0] + curr.orig_bbox[2]) / 2
            gap = curr_cx - prev_cx

            if gap <= 3.0:
                current_cluster.append(items[i])
            else:
                clusters.append(current_cluster)
                current_cluster = [items[i]]
        clusters.append(current_cluster)

        # 3. Resolve & Filter by Vertical IoU
        for c_id, cluster in enumerate(clusters):
            if len(cluster) == 1:
                # Log Solitary
                item = cluster[0]
                rows.append(
                    {
                        "image": stem,
                        "pred_index": item[0],
                        "cluster_id": c_id,
                        "x_center": (item[1].orig_bbox[0] + item[1].orig_bbox[2]) / 2,
                        "decision": "KEEP",
                        "reason": "SOLITARY",
                    }
                )
                continue

            # Check vertical overlaps in cluster pairwise or group-wise
            # Simplification: In a tight cluster <3px, we assume transitivity if sorted
            # Verify adjacent pairs have Y-IoU >= 0.5. If not, split cluster?
            # For simplicity: Keep the whole cluster together, but only mark removal if IoU holds.
            # Actually, standard logic: Find Best in cluster. Remove others ONLY IF they overlap vertically with Best.

            # Score first
            scored_cluster = []
            for original_idx, pred in cluster:
                x1, y1, x2, y2 = pred.orig_bbox
                h = y2 - y1
                # Overlap
                y1_c = max(0, min(mask_h, y1))
                y2_c = max(0, min(mask_h, y2))
                x1_c = max(0, min(mask_w, x1))
                x2_c = max(0, min(mask_w, x2))
                if x1_c >= x2_c or y1_c >= y2_c:
                    overlap_area = 0.0
                else:
                    box_window = notehead_mask[y1_c:y2_c, x1_c:x2_c]
                    overlap_area = float(np.count_nonzero(box_window))

                score = float(h) + (overlap_area * 2.0)
                scored_cluster.append(
                    {"pred": pred, "idx": original_idx, "score": score, "y_span": (y1, y2)}
                )

            # Sort by Score Descending
            scored_cluster.sort(key=lambda x: x["score"], reverse=True)
            primary = scored_cluster[0]

            # Log Primary
            rows.append(
                {
                    "image": stem,
                    "pred_index": primary["idx"],
                    "cluster_id": c_id,
                    "x_center": (primary["pred"].orig_bbox[0] + primary["pred"].orig_bbox[2]) / 2,
                    "decision": "KEEP",
                    "reason": "BEST",
                }
            )

            # Check others
            py1, py2 = primary["y_span"]

            for secondary in scored_cluster[1:]:
                sy1, sy2 = secondary["y_span"]

                # Vertical IoU
                inter_y1 = max(py1, sy1)
                inter_y2 = min(py2, sy2)
                inter_h = max(0, inter_y2 - inter_y1)

                union_h = (py2 - py1) + (sy2 - sy1) - inter_h
                iou_y = inter_h / union_h if union_h > 0 else 0.0

                if iou_y >= 0.5:
                    decision = "REMOVE"
                    reason = "DUPLICATE"
                else:
                    decision = "KEEP"
                    reason = "NO_OVERLAP"

                rows.append(
                    {
                        "image": stem,
                        "pred_index": secondary["idx"],
                        "cluster_id": c_id,
                        "x_center": (
                            secondary["pred"].orig_bbox[0] + secondary["pred"].orig_bbox[2]
                        )
                        / 2,
                        "decision": decision,
                        "reason": reason,
                    }
                )

    csv_path = output_dir / f"{stem}_tight_duplicates_candidates.csv"
    if not rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = ["image", "pred_index", "cluster_id", "x_center", "decision", "reason"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_measure_grid_candidates(
    predictions: List[BarlinePrediction],
    notehead_mask: np.ndarray,
    stem: str,
    output_dir: Path,
) -> None:
    """
    Phase 13: Export data for Measure Grid Consistency (DP) validation.
    Saves candidate stats + score + gaps to measure_grid_candidates.csv.
    """
    mask_h, mask_w = notehead_mask.shape

    # Group by Staff
    grouped = collections.defaultdict(list)
    for idx, pred in enumerate(predictions):
        key = (pred.system_index, pred.staff_index)
        grouped[key].append((idx, pred))

    rows = []

    for (sys_idx, staff_idx), items in grouped.items():
        # Sort by x-center
        items.sort(key=lambda item: (item[1].orig_bbox[0] + item[1].orig_bbox[2]) / 2)

        for original_idx, pred in items:
            x1, y1, x2, y2 = pred.orig_bbox
            h = y2 - y1

            # Recalculate overlap for scoring
            y1_c = max(0, min(mask_h, y1))
            y2_c = max(0, min(mask_h, y2))
            x1_c = max(0, min(mask_w, x1))
            x2_c = max(0, min(mask_w, x2))

            if x1_c >= x2_c or y1_c >= y2_c:
                overlap_area = 0.0
            else:
                box_window = notehead_mask[y1_c:y2_c, x1_c:x2_c]
                overlap_area = float(np.count_nonzero(box_window))

            # Score
            score = float(h) + (overlap_area * 2.0)

            rows.append(
                {
                    "image": stem,
                    "pred_index": original_idx,
                    "system_index": sys_idx,
                    "staff_index": staff_idx,
                    "x_center": (x1 + x2) / 2,
                    "width": x2 - x1,
                    "height": h,
                    "overlap": overlap_area,
                    "score": score,
                }
            )

    csv_path = output_dir / f"{stem}_measure_grid_candidates.csv"
    if not rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "image",
            "pred_index",
            "system_index",
            "staff_index",
            "x_center",
            "width",
            "height",
            "overlap",
            "score",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def compute_candidate_stats(
    predictions: List[BarlinePrediction],
    notehead_mask: np.ndarray,
    staff_mask: np.ndarray,
    stem: str,
    output_dir: Path,
) -> None:
    """
    Computes and saves statistics for each candidate barline to a CSV file.
    Stats include: width, height, distance to nearest notehead, intersection w/ notehead,
    and number of staff line crossings.
    """
    mask_h, mask_w = notehead_mask.shape
    stats_rows = []

    # Pre-compute distance transform for fast distance queries
    # dist_map[y, x] = distance to nearest zero pixel.
    # So we invert the mask: noteheads are 1 (non-zero), background 0.
    # We want distance to nearest Notehead (non-zero).
    # Invert: noteheads=0, background=1.
    # cv2.distanceTransform calculates distance to nearest ZERO pixel.
    # So we want noteheads to be 0.
    inverted_mask = cv2.bitwise_not(notehead_mask)
    dist_map = cv2.distanceTransform(inverted_mask, cv2.DIST_L2, 5)

    for idx, pred in enumerate(predictions):
        x1, y1, x2, y2 = pred.orig_bbox
        w = x2 - x1
        h = y2 - y1
        (x1 + x2) // 2
        (y1 + y2) // 2

        # Clamp to mask bounds
        c_y1 = max(0, min(mask_h - 1, y1))
        c_y2 = max(0, min(mask_h - 1, y2))
        c_x1 = max(0, min(mask_w - 1, x1))
        c_x2 = max(0, min(mask_w - 1, x2))

        if c_y1 >= c_y2 or c_x1 >= c_x2:
            min_dist = 9999.0
            overlap_area = 0
        else:
            # 1. Distance to nearest notehead
            # Extract distance map region
            dist_region = dist_map[c_y1:c_y2, c_x1:c_x2]
            min_dist = float(np.min(dist_region))

            # 2. Intersection (direct overlap)
            # Mask region is > 0 where noteheads are.
            mask_region = notehead_mask[c_y1:c_y2, c_x1:c_x2]
            overlap_count = np.count_nonzero(mask_region)
            overlap_area = float(overlap_count)

        # Count staff crossings
        num_crossings = count_staff_crossings(pred.orig_bbox, staff_mask)

        stats_rows.append(
            {
                "image": stem,
                "pred_index": idx,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width": w,
                "height": h,
                "min_dist_to_notehead": min_dist,
                "overlap_area": overlap_area,
                "num_staff_crossings": num_crossings,
            }
        )

    csv_path = output_dir / f"{stem}_candidate_stats.csv"
    if not stats_rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=stats_rows[0].keys())
        writer.writeheader()
        writer.writerows(stats_rows)


def compute_and_save_gap_stats(
    predictions: List[BarlinePrediction],
    stem: str,
    output_dir: Path,
) -> None:
    """
    Computes horizontal gaps between adjacent barlines on the same staff/system
    and saves to CSV.
    """
    # Group by staff/system
    # Structure: { (system_idx, staff_idx): [ (pred_idx, pred_obj), ... ] }
    grouped = collections.defaultdict(list)
    for idx, pred in enumerate(predictions):
        key = (pred.system_index, pred.staff_index)
        grouped[key].append((idx, pred))

    rows = []

    for (sys_idx, staff_idx), items in grouped.items():
        # Sort by x-center
        items.sort(key=lambda item: (item[1].orig_bbox[0] + item[1].orig_bbox[2]) / 2)

        for i, (original_idx, pred) in enumerate(items):
            x1, y1, x2, y2 = pred.orig_bbox
            cx = (x1 + x2) / 2

            # Gap to prev
            if i > 0:
                prev_pred = items[i - 1][1]
                prev_cx = (prev_pred.orig_bbox[0] + prev_pred.orig_bbox[2]) / 2
                gap_to_prev = cx - prev_cx
            else:
                gap_to_prev = -1.0  # Sentinel for "First in staff"

            # Gap to next
            if i < len(items) - 1:
                next_pred = items[i + 1][1]
                next_cx = (next_pred.orig_bbox[0] + next_pred.orig_bbox[2]) / 2
                gap_to_next = next_cx - cx
            else:
                gap_to_next = -1.0  # Sentinel for "Last in staff"

            rows.append(
                {
                    "image": stem,
                    "pred_index": original_idx,
                    "system_index": sys_idx,
                    "staff_index": staff_idx,
                    "x_center": cx,
                    "gap_to_prev": gap_to_prev,
                    "gap_to_next": gap_to_next,
                    "width": x2 - x1,
                    "height": y2 - y1,
                }
            )

    csv_path = output_dir / f"{stem}_candidate_gaps.csv"
    if not rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "image",
            "pred_index",
            "system_index",
            "staff_index",
            "x_center",
            "gap_to_prev",
            "gap_to_next",
            "width",
            "height",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
