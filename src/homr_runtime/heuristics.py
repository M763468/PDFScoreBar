"""Assemble HOMR staffs and symbols; callable bindings remain compatibility patch points."""

#!/usr/bin/env python3
from __future__ import annotations

from concurrent.futures import Future
from typing import Any, Dict, List, Tuple

import numpy as np

from homr import constants
from homr.bounding_boxes import create_rotated_bounding_boxes
from homr.brace_dot_detection import (
    find_braces_brackets_and_grand_staff_lines,
    prepare_brace_dot_image,
)
from homr.main import ProcessingConfig, load_and_preprocess_predictions, predict_symbols
from homr.note_detection import add_notes_to_staffs, combine_noteheads_with_stems
from homr.staff_detection import break_wide_fragments, detect_staff
from homr.title_detection import detect_title
from src.homr_runtime.barline_candidates import (
    _ensure_mask_shape as _ensure_mask_shape,
)
from src.homr_runtime.barline_candidates import (
    generate_barline_cc_dilated as generate_barline_cc_dilated,
)
from src.homr_runtime.barline_candidates import (
    generate_barline_cc_relaxed as generate_barline_cc_relaxed,
)
from src.homr_runtime.barline_candidates import (
    generate_barline_cc_tiny as generate_barline_cc_tiny,
)
from src.homr_runtime.barline_candidates import (
    generate_column_sum_candidates as generate_column_sum_candidates,
)
from src.homr_runtime.barline_candidates import (
    generate_hough_vertical_candidates as generate_hough_vertical_candidates,
)
from src.homr_runtime.barline_candidates import (
    generate_sobel_vertical_candidates as generate_sobel_vertical_candidates,
)
from src.homr_runtime.barline_candidates import (
    generate_sobel_vertical_candidates_weak as generate_sobel_vertical_candidates_weak,
)
from src.homr_runtime.barline_candidates import (
    generate_vertical_run_candidates as generate_vertical_run_candidates,
)
from src.homr_runtime.barline_candidates import (
    generate_vertical_run_candidates_weak as generate_vertical_run_candidates_weak,
)
from src.homr_runtime.end_barlines import recover_end_barlines as recover_end_barlines
from src.homr_runtime.filtering import count_staff_crossings as count_staff_crossings
from src.homr_runtime.filtering import (
    filter_detections_by_notehead_proximity as filter_detections_by_notehead_proximity,
)
from src.homr_runtime.transforms import autocrop_bounds as autocrop_bounds
from src.homr_runtime.transforms import compute_transform_info as compute_transform_info
from src.homr_runtime.utils import eprint


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
