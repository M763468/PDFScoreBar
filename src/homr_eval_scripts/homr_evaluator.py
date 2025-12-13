#!/usr/bin/env python3
"""Run homr evaluations and compute barline detection metrics."""

from __future__ import annotations

import argparse
import asyncio
import collections
import csv
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from concurrent.futures import Future

import cv2  # type: ignore
import numpy as np

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python <3.9 fallback
    from backports.zoneinfo import ZoneInfo  # type: ignore

# Ensure the local homr repository is importable before third-party homr installs.
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
HOMR_REPO = REPO_ROOT / "homr"
JST = ZoneInfo("Asia/Tokyo")

# Force paths to front to ensure correct import order
if str(SRC_ROOT) in sys.path:
    sys.path.remove(str(SRC_ROOT))
sys.path.insert(0, str(SRC_ROOT))

if str(HOMR_REPO) in sys.path:
    sys.path.remove(str(HOMR_REPO))
sys.path.insert(0, str(HOMR_REPO))

# pylint: disable=wrong-import-position
from homr import constants  # type: ignore
from homr.main import (  # type: ignore
    ProcessingConfig,
    download_weights,
    load_and_preprocess_predictions,
    parse_staffs,
    predict_symbols,
)
from homr.music_xml_generator import XmlGeneratorArguments, generate_xml  # type: ignore
from homr.resize import calc_target_image_size  # type: ignore
from homr.staff_detection import break_wide_fragments, detect_staff  # type: ignore
from homr.note_detection import combine_noteheads_with_stems, add_notes_to_staffs  # type: ignore
from homr.bar_line_detection import detect_bar_lines  # type: ignore
from homr.brace_dot_detection import (
    find_braces_brackets_and_grand_staff_lines,
    prepare_brace_dot_image,
)  # type: ignore
from homr.bounding_boxes import create_rotated_bounding_boxes  # type: ignore
from homr.title_detection import detect_title  # type: ignore
from homr.simple_logging import eprint  # type: ignore

from common.barline_evaluation import (
    BarlineMatch,
    BarlineMatchResult,
    BarlineSoftMatch,
    apply_left_margin_exclusion,
    greedy_barline_match,
)
from common.thin_barline_finder import detect_thin_vertical_runs, ThinBarlineConfig
from common.preprocessing import apply_advanced_sr

LEFT_MARGIN_FORCE_FP_GT_INDICES: Set[int] = set()
LEFT_MARGIN_FORCE_FP_MAX_WIDTH = 2

# Configuration for stem-context based False Positive reduction heuristics.
# Configuration for stem-context based False Positive reduction heuristics.
# Configuration for stem-context based False Positive reduction heuristics.
STEM_CONTEXT_HEURISTICS = {
    "enabled": True,
    "notehead_proximity_threshold_px": 5,
    "min_overlap_px": 5,
    "max_height_px": 24,
    "max_width_px": 4,
    "staff_crossing_enabled": False,
    "min_staff_crossings": 3,
    "cluster_resolution_dry_run": False,
    "cluster_gap_threshold_px": 15,
    "tight_duplicate_dry_run": False,
    "measure_grid_export": True,
}


@dataclass
class TransformInfo:
    original_shape: Tuple[int, int]  # width, height
    crop_box: Tuple[int, int, int, int]  # x, y, w, h
    resize_shape: Tuple[int, int]
    seg_shape: Tuple[int, int]
    resize_scale: Tuple[float, float]
    seg_scale: Tuple[float, float]

    @property
    def total_scale(self) -> Tuple[float, float]:
        return (
            self.resize_scale[0] * self.seg_scale[0],
            self.resize_scale[1] * self.seg_scale[1],
        )


@dataclass
class BarlinePrediction:
    pred_bbox: Tuple[int, int, int, int]
    orig_bbox: Tuple[int, int, int, int]
    system_index: int
    staff_index: int


@dataclass
class ImageMetrics:
    image: str
    num_predictions: int
    num_ground_truth: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    matches: List[BarlineMatch] = field(default_factory=list)
    soft_matches: List[BarlineSoftMatch] = field(default_factory=list)


@dataclass
class AggregateMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images",
        nargs="+",
        required=True,
        help="List of image files to evaluate",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("logs/homr_eval"),
        help="Root directory for evaluation outputs",
    )
    parser.add_argument(
        "--run-tag",
        type=str,
        help="Optional suffix appended to the run identifier",
    )
    parser.add_argument(
        "--ground-truth",
        action="append",
        default=[],
        help="Mapping of image stem to ground truth JSON, e.g. page_001:data/training/annotations/page_001/boxes_sorted.json",
    )
    parser.add_argument(
        "--ground-truth-dir",
        type=Path,
        help="Directory containing <stem>.json ground truth files",
    )
    parser.add_argument(
        "--iou-threshold",
        type=float,
        default=0.5,
        help="IoU threshold to consider a detection a true positive",
    )
    parser.add_argument(
        "--docker-tag",
        type=str,
        help="Docker image tag recorded in run_config.json",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Enable homr cache file usage",
    )
    parser.add_argument(
        "--write-staff-positions",
        action="store_true",
        help="Persist staff position text files alongside debug outputs",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Timeout (seconds) when waiting for title detection futures",
    )
    parser.add_argument(
        "--baseline-metrics",
        type=Path,
        help="Optional metrics.json from baseline detector for comparison",
    )
    parser.add_argument(
        "--force-run-id",
        type=str,
        help="Override automatically generated run identifier",
    )
    parser.add_argument(
        "--barline-min-height-factor",
        type=float,
        default=1.0,
        help="Scale factor applied to barline minimum height threshold",
    )
    parser.add_argument(
        "--barline-max-width-factor",
        type=float,
        default=1.0,
        help="Scale factor applied to barline maximum width threshold",
    )
    parser.add_argument(
        "--enable-sr",
        action="store_true",
        help="Enable Super-Resolution (Real-ESRGAN x4) preprocessing",
    )
    return parser.parse_args()


def load_ground_truth_mapping(args: argparse.Namespace) -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    for item in args.ground_truth:
        if ":" not in item:
            raise ValueError(
                f"Invalid ground truth mapping '{item}'. Expected format <stem>:<path>."
            )
        stem, path_str = item.split(":", maxsplit=1)
        path = Path(path_str).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Ground truth file not found: {path}")
        mapping[stem] = path
    return mapping


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def git_info() -> Dict[str, Optional[str]]:
    def run_git(cmd: Sequence[str]) -> Optional[str]:
        try:
            result = subprocess.run(
                cmd,
                cwd=REPO_ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    return {
        "commit": run_git(["git", "rev-parse", "HEAD"]),
        "branch": run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "status": run_git(["git", "status", "-sb"]),
    }


def current_jst() -> datetime:
    return datetime.now(JST)


def timestamp_jst() -> str:
    return current_jst().strftime("%Y-%m-%dT%H:%M:%S") + "JST"


def choose_run_id(args: argparse.Namespace) -> str:
    if args.force_run_id:
        return args.force_run_id
    base = current_jst().strftime("%Y%m%dT%H%M%S") + "JST"
    if args.run_tag:
        return f"{base}_{args.run_tag}"
    return base


def sanitise_images(images: Iterable[str]) -> List[Path]:
    resolved = []
    for item in images:
        path = Path(item).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Image path not found: {path}")
        resolved.append(path)
    return resolved


def autocrop_bounds(image: np.ndarray) -> Tuple[Tuple[int, int, int, int], bool]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([image], [0], None, [256], [0, 256])
    dominant_color_gray_scale = int(max(enumerate(hist), key=lambda x: float(x[1]))[0])
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


def map_pred_to_orig(box: Tuple[int, int, int, int], transform: TransformInfo) -> Tuple[int, int, int, int]:
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


def prepare_working_image(image: Path, dest_dir: Path) -> Path:
    ensure_dir(dest_dir)
    dest_path = dest_dir / image.name
    shutil.copy2(image, dest_path)
    return dest_path


def detect_staffs_with_barlines(
    image_path: str,
    config: ProcessingConfig,
    tuning: Dict[str, float],
) -> Tuple[List[Any], np.ndarray, Any, Future[str], List[Any], np.ndarray, np.ndarray]:
    """
    Runs the core homr staff and symbol detection pipeline.

    Returns:
        A tuple containing the multi-staffs, preprocessed image, debug object,
        title future, detected bar line boxes, the notehead prediction mask,
        and the staff prediction mask.
    """
    predictions, debug = load_and_preprocess_predictions(
        image_path, config.enable_debug, config.enable_cache
    )
    symbols = predict_symbols(debug, predictions)

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

    min_height_factor = tuning.get("barline_min_height_factor", 1.0)
    max_width_factor = tuning.get("barline_max_width_factor", 1.0)
    min_height_threshold = min_height_factor * constants.bar_line_min_height(
        average_note_head_height
    )
    max_width_threshold = max_width_factor * constants.bar_line_max_width(
        average_note_head_height
    )

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
            prev = items[i-1][1]
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
                scored_cluster.append({
                    "pred": pred,
                    "idx": original_idx,
                    "score": score,
                    "height": h,
                    "overlap": overlap_area,
                    "decision": "KEEP", # Default
                    "reason": "SOLITARY" if len(cluster) == 1 else "BEST"
                })
            
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
                 cluster_rows.append({
                     "image": stem,
                     "pred_index": item["idx"],
                     "cluster_id": c_id,
                     "x_center": (item["pred"].orig_bbox[0] + item["pred"].orig_bbox[2]) / 2,
                     "score": item["score"],
                     "height": item["height"],
                     "overlap": item["overlap"],
                     "decision": item["decision"],
                     "reason": item["reason"]
                 })

    # Save CSV
    csv_path = output_dir / f"{stem}_candidate_clusters.csv"
    if not cluster_rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "image", "pred_index", "cluster_id", "x_center", "score", 
            "height", "overlap", "decision", "reason"
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
            prev = items[i-1][1]
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
                rows.append({
                    "image": stem,
                    "pred_index": item[0],
                    "cluster_id": c_id,
                    "x_center": (item[1].orig_bbox[0] + item[1].orig_bbox[2])/2,
                    "decision": "KEEP",
                    "reason": "SOLITARY"
                })
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
                scored_cluster.append({
                    "pred": pred,
                    "idx": original_idx,
                    "score": score,
                    "y_span": (y1, y2)
                })
            
            # Sort by Score Descending
            scored_cluster.sort(key=lambda x: x["score"], reverse=True)
            primary = scored_cluster[0]
            
            # Log Primary
            rows.append({
                 "image": stem,
                 "pred_index": primary["idx"],
                 "cluster_id": c_id,
                 "x_center": (primary["pred"].orig_bbox[0] + primary["pred"].orig_bbox[2])/2,
                 "decision": "KEEP",
                 "reason": "BEST"
            })
            
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
                    
                rows.append({
                     "image": stem,
                     "pred_index": secondary["idx"],
                     "cluster_id": c_id,
                     "x_center": (secondary["pred"].orig_bbox[0] + secondary["pred"].orig_bbox[2])/2,
                     "decision": decision,
                     "reason": reason
                })

    csv_path = output_dir / f"{stem}_tight_duplicates_candidates.csv"
    if not rows:
        return
        
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "image", "pred_index", "cluster_id", "x_center", "decision", "reason"
        ]
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
            
            rows.append({
                "image": stem,
                "pred_index": original_idx,
                "system_index": sys_idx,
                "staff_index": staff_idx,
                "x_center": (x1 + x2) / 2,
                "width": x2 - x1,
                "height": h,
                "overlap": overlap_area,
                "score": score
            })

    csv_path = output_dir / f"{stem}_measure_grid_candidates.csv"
    if not rows:
        return
        
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "image", "pred_index", "system_index", "staff_index", 
            "x_center", "width", "height", "overlap", "score"
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
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        
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
        
        stats_rows.append({
            "image": stem,
            "pred_index": idx,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "width": w,
            "height": h,
            "min_dist_to_notehead": min_dist,
            "overlap_area": overlap_area,
            "num_staff_crossings": num_crossings,
        })
    
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
                prev_pred = items[i-1][1]
                prev_cx = (prev_pred.orig_bbox[0] + prev_pred.orig_bbox[2]) / 2
                gap_to_prev = cx - prev_cx
            else:
                gap_to_prev = -1.0 # Sentinel for "First in staff"
                
            # Gap to next
            if i < len(items) - 1:
                next_pred = items[i+1][1]
                next_cx = (next_pred.orig_bbox[0] + next_pred.orig_bbox[2]) / 2
                gap_to_next = next_cx - cx
            else:
                gap_to_next = -1.0 # Sentinel for "Last in staff"
                
            rows.append({
                "image": stem,
                "pred_index": original_idx,
                "system_index": sys_idx,
                "staff_index": staff_idx,
                "x_center": cx,
                "gap_to_prev": gap_to_prev,
                "gap_to_next": gap_to_next,
                "width": x2 - x1,
                "height": y2 - y1,
            })
            
    csv_path = output_dir / f"{stem}_candidate_gaps.csv"
    if not rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "image", "pred_index", "system_index", "staff_index", 
            "x_center", "gap_to_prev", "gap_to_next", "width", "height"
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def save_debug_staff_overlay(
    image_path: Path,
    staff_mask: np.ndarray,
    output_path: Path,
) -> None:
    original = cv2.imread(str(image_path))
    if original is None:
        return
    
    # Create green overlay for staff lines
    overlay = original.copy()
    overlay[staff_mask > 0] = [0, 255, 0]  # BGR green
    
    # Alpha blend
    alpha = 0.3
    cv2.addWeighted(overlay, alpha, original, 1 - alpha, 0, original)
    
    cv2.imwrite(str(output_path), original)

def save_debug_mask_overlay(
    image_path: Path,
    notehead_mask: np.ndarray,
    output_path: Path,
) -> None:
    original = cv2.imread(str(image_path))
    if original is None:
        return
    
    # Create red overlay for mask
    # Mask is uint8 (0 or >0)
    # Resize already matches original shape
    
    overlay = original.copy()
    # Where mask is active, set to Red
    overlay[notehead_mask > 0] = [0, 0, 255]  # BGR
    
    # Alpha blend
    alpha = 0.5
    cv2.addWeighted(overlay, alpha, original, 1 - alpha, 0, original)
    
    cv2.imwrite(str(output_path), original)

def run_homr_on_image(
    image_path: Path,
    config: ProcessingConfig,
    xml_args: XmlGeneratorArguments,
    timeout_s: float,
    tuning: Dict[str, float],
) -> Tuple[List[BarlinePrediction], Optional[Path], Tuple[int, int], float, np.ndarray, np.ndarray]:
    start = time.perf_counter()
    (multi_staffs, preprocessed_image, debug, title_future, bar_line_boxes, notehead_mask, staff_mask) = (
        detect_staffs_with_barlines(str(image_path), config, tuning)
    )

    predictions: List[BarlinePrediction] = []
    for barline_box in bar_line_boxes:
        bbox = barline_box.to_bounding_box()
        x1, y1, x2, y2 = map(int, bbox.box)
        predictions.append(
            BarlinePrediction(
                pred_bbox=(x1, y1, x2, y2),
                orig_bbox=(0, 0, 0, 0),
                system_index=getattr(barline_box, "debug_id", -1),
                staff_index=-1,
            )
        )

    xml_path: Optional[Path] = None
    seg_shape = (debug.original_image.shape[0], debug.original_image.shape[1])

    try:
        result_staffs = parse_staffs(debug, multi_staffs, preprocessed_image, selected_staff=-1)
        try:
            title = title_future.result(timeout_s)
        except Exception:  # pylint: disable=broad-except
            title = ""
        xml = generate_xml(xml_args, result_staffs, title)
        xml_path = Path(str(image_path.with_suffix(".musicxml")))
        xml.write(xml_path)
        teaser_file = Path(str(image_path.with_name(image_path.stem + "_teaser.png")))
        debug.write_teaser(str(teaser_file), multi_staffs)
    finally:
        debug.clean_debug_files_from_previous_runs()

    runtime_s = time.perf_counter() - start
    return predictions, xml_path, seg_shape, runtime_s, notehead_mask, staff_mask


def draw_overlay(
    original_image_path: Path,
    predictions: Sequence[BarlinePrediction],
    output_path: Path,
    *,
    matches: Optional[Sequence[BarlineMatch]] = None,
    soft_matches: Optional[Sequence[BarlineSoftMatch]] = None,
    rejected_detections: Optional[Sequence[BarlinePrediction]] = None,
    false_positive_indices: Optional[Sequence[int]] = None,
    thickness: int = 2,
) -> None:
    image = cv2.imread(str(original_image_path))
    if image is None:
        raise RuntimeError(f"Failed to read image for overlay: {original_image_path}")
    matched_pred_indices = {m.pred_index for m in matches} if matches else set()
    soft_lookup = {sm.pred_index: sm for sm in soft_matches} if soft_matches else {}
    fp_indices = set(false_positive_indices or [])

    for idx, pred in enumerate(predictions):
        x1, y1, x2, y2 = pred.orig_bbox
        if idx in matched_pred_indices:
            color = (0, 255, 0)
            label = f"TP#{idx}"
        elif idx in soft_lookup:
            reason = soft_lookup[idx].reason
            marker = "dup" if reason == "duplicate" else "rep"
            color = (255, 165, 0)
            label = f"OK#{idx}:{marker}"
        elif fp_indices:
            color = (0, 0, 255)
            label = f"FP#{idx}"
        else:
            color = (0, 0, 255)
            label = f"P#{idx}"

        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
        cv2.putText(
            image,
            label,
            (x1, max(12, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )

    if rejected_detections:
        for pred in rejected_detections:
            x1, y1, x2, y2 = pred.orig_bbox
            color = (128, 0, 128)  # Purple for rejected stems
            label = "REJECTED_STEM"
            cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
            cv2.putText(
                image, label, (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA
            )

    ensure_dir(output_path.parent)
    if not cv2.imwrite(str(output_path), image):
        raise RuntimeError(f"Failed to write overlay image: {output_path}")


def load_ground_truth_boxes(path: Path) -> List[Tuple[int, int, int, int]]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    boxes = []
    for entry in data:
        if "barline_location" in entry:
            boxes.append(tuple(map(int, entry["barline_location"])))
        elif "bbox" in entry:
            boxes.append(tuple(map(int, entry["bbox"])))
    return boxes


def compute_metrics(
    predictions: Sequence[BarlinePrediction],
    ground_truth_boxes: Sequence[Tuple[int, int, int, int]],
    threshold: float,
) -> Tuple[ImageMetrics, BarlineMatchResult]:
    pred_boxes = [pred.orig_bbox for pred in predictions]
    match_result = greedy_barline_match(pred_boxes, ground_truth_boxes, iou_threshold=threshold)

    def _force_fp(pred_index: int, pred_box: Tuple[int, int, int, int], gt_index: int, gt_box: Tuple[int, int, int, int]) -> bool:
        if gt_index not in LEFT_MARGIN_FORCE_FP_GT_INDICES:
            return False
        width = max(pred_box[2] - pred_box[0], 1)
        return width <= LEFT_MARGIN_FORCE_FP_MAX_WIDTH

    match_result = apply_left_margin_exclusion(
        match_result,
        pred_boxes,
        ground_truth_boxes,
        force_fp_predicate=_force_fp,
    )

    tp = len(match_result.matches)
    fp = len(match_result.false_positive_indices)
    fn = len(match_result.false_negative_indices)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return ImageMetrics(
        image="",
        num_predictions=len(pred_boxes),
        num_ground_truth=len(ground_truth_boxes),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        matches=match_result.matches,
        soft_matches=match_result.soft_matches,
    ), match_result


def aggregate_metrics(per_image: Sequence[ImageMetrics]) -> AggregateMetrics:
    tp = sum(item.true_positives for item in per_image)
    fp = sum(item.false_positives for item in per_image)
    fn = sum(item.false_negatives for item in per_image)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return AggregateMetrics(tp, fp, fn, precision, recall, f1)


def write_metrics_json(
    run_dir: Path,
    run_id: str,
    per_image: Sequence[ImageMetrics],
    aggregate: AggregateMetrics,
    extra: Dict[str, Any],
) -> Path:
    payload = {
        "run_id": run_id,
        "timestamp": timestamp_jst(),
        "images": [
            {
                **asdict(metric),
                "matches": [asdict(match) for match in metric.matches],
                "soft_matches": [asdict(sm) for sm in metric.soft_matches],
            }
            for metric in per_image
        ],
        "aggregate": asdict(aggregate),
        "extra": extra,
    }
    path = run_dir / "metrics.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return path


def write_metrics_csv(run_dir: Path, per_image: Sequence[ImageMetrics], aggregate: AggregateMetrics) -> Path:
    path = run_dir / "metrics.csv"
    fieldnames = [
        "image",
        "num_predictions",
        "num_ground_truth",
        "true_positives",
        "false_positives",
        "false_negatives",
        "precision",
        "recall",
        "f1",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for metric in per_image:
            row = {key: getattr(metric, key) for key in fieldnames}
            writer.writerow(row)
        writer.writerow(
            {
                "image": "aggregate",
                "num_predictions": "-",
                "num_ground_truth": "-",
                "true_positives": aggregate.true_positives,
                "false_positives": aggregate.false_positives,
                "false_negatives": aggregate.false_negatives,
                "precision": aggregate.precision,
                "recall": aggregate.recall,
                "f1": aggregate.f1,
            }
        )
    return path


def write_run_config(
    run_dir: Path,
    run_id: str,
    args: argparse.Namespace,
    git_meta: Dict[str, Optional[str]],
    images: Sequence[Path],
) -> Path:
    payload = {
        "run_id": run_id,
        "timestamp": timestamp_jst(),
        "command": " ".join(shlex.quote(str(arg)) for arg in sys.argv),
        "docker_tag": args.docker_tag,
        "git": git_meta,
        "images": [str(path) for path in images],
        "parameters": {
            "iou_threshold": args.iou_threshold,
            "cache": args.cache,
            "write_staff_positions": args.write_staff_positions,
            "timeout": args.timeout,
            "barline_min_height_factor": args.barline_min_height_factor,
            "barline_max_width_factor": args.barline_max_width_factor,
        },
    }
    path = run_dir / "run_config.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return path


def write_readme(
    run_dir: Path,
    run_id: str,
    per_image: Sequence[ImageMetrics],
    aggregate: AggregateMetrics,
    args: argparse.Namespace,
    ground_truth_summary: Dict[str, Optional[Path]],
) -> Path:
    lines = [
        f"# homr Evaluation Run {run_id}",
        "",
        f"- Timestamp: {timestamp_jst()}",
        f"- Images: {len(per_image)}",
        f"- IoU threshold: {args.iou_threshold}",
        "",
        "## Aggregate Metrics",
        "",
        f"- True Positives: {aggregate.true_positives}",
        f"- False Positives: {aggregate.false_positives}",
        f"- False Negatives: {aggregate.false_negatives}",
        f"- Precision: {aggregate.precision:.4f}",
        f"- Recall: {aggregate.recall:.4f}",
        f"- F1: {aggregate.f1:.4f}",
        "",
        "## Per-image Metrics",
        "",
    ]
    for metric in per_image:
        gt_path = ground_truth_summary.get(metric.image)
        lines.extend(
            [
                f"### {metric.image}",
                f"- Ground truth: {gt_path if gt_path else 'None'}",
                f"- Predictions: {metric.num_predictions}",
                f"- Ground truth boxes: {metric.num_ground_truth}",
                f"- TP/FP/FN: {metric.true_positives}/{metric.false_positives}/{metric.false_negatives}",
                f"- Precision: {metric.precision:.4f}",
                f"- Recall: {metric.recall:.4f}",
                f"- F1: {metric.f1:.4f}",
                "",
            ]
        )
    readme_path = run_dir / "README.md"
    with readme_path.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return readme_path


def write_compare_md(
    run_dir: Path,
    per_image: Sequence[ImageMetrics],
    aggregate: AggregateMetrics,
    baseline_path: Optional[Path],
) -> Path:
    compare_path = run_dir / "compare.md"
    if not baseline_path or not baseline_path.exists():
        with compare_path.open("w", encoding="utf-8") as fh:
            fh.write("# Comparison\n\nBaseline metrics not provided; cannot generate comparison table.\n")
        return compare_path

    with baseline_path.open("r", encoding="utf-8") as fh:
        baseline = json.load(fh)

    baseline_images = {item["image"]: item for item in baseline.get("images", [])}
    baseline_agg = baseline.get("aggregate", {})

    lines = ["# Comparison", ""]
    lines.append("| Image | Precision (baseline → homr) | Recall (baseline → homr) | F1 (baseline → homr) |")
    lines.append("| --- | --- | --- | --- |")
    for metric in per_image:
        base = baseline_images.get(metric.image, {})
        lines.append(
            f"| {metric.image} | {base.get('precision', 'n/a')} → {metric.precision:.4f} | "
            f"{base.get('recall', 'n/a')} → {metric.recall:.4f} | {base.get('f1', 'n/a')} → {metric.f1:.4f} |"
        )

    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    lines.append(
        "| Metric | Baseline | homr |\n| --- | --- | --- |\n"
        f"| Precision | {baseline_agg.get('precision', 'n/a')} | {aggregate.precision:.4f} |\n"
        f"| Recall | {baseline_agg.get('recall', 'n/a')} | {aggregate.recall:.4f} |\n"
        f"| F1 | {baseline_agg.get('f1', 'n/a')} | {aggregate.f1:.4f} |"
    )

    with compare_path.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    return compare_path


def write_run_sh(run_dir: Path) -> Path:
    path = run_dir / "run.sh"
    with path.open("w", encoding="utf-8") as fh:
        fh.write("#!/usr/bin/env bash\n")
        fh.write("set -euo pipefail\n")
        fh.write("cd \"$(dirname \"${BASH_SOURCE[0]}\")/../..\"\n")
        fh.write("python src/homr/homr_evaluator.py " + " ".join(shlex.quote(arg) for arg in sys.argv[1:]) + "\n")
    os.chmod(path, 0o755)
    return path


def main() -> None:
    args = parse_args()
    images = sanitise_images(args.images)
    ground_truth_map = load_ground_truth_mapping(args)

    run_id = choose_run_id(args)
    run_dir = args.output_root / run_id
    ensure_dir(run_dir)

    write_run_sh(run_dir)

    git_meta = git_info()
    write_run_config(run_dir, run_id, args, git_meta, images)

    download_weights()

    per_image_metrics: List[ImageMetrics] = []
    ground_truth_summary: Dict[str, Optional[Path]] = {}
    tuning = {
        "barline_min_height_factor": args.barline_min_height_factor,
        "barline_max_width_factor": args.barline_max_width_factor,
    }

    for image_path in images:
        stem = image_path.stem
        image_run_dir = run_dir / stem
        working_image = prepare_working_image(image_path, image_run_dir)

        sr_scale = 1
        if args.enable_sr:
            sr_scale = 4
            eprint(f"Applying Super-Resolution (x{sr_scale}) to {stem}...")
            img_bgr = cv2.imread(str(working_image))
            if img_bgr is not None:
                upscaled = apply_advanced_sr(img_bgr, model_name='RealESRGAN_x4plus', scale=sr_scale)
                cv2.imwrite(str(working_image), upscaled)
            else:
                eprint(f"Warning: Failed to load {working_image} for SR.")

        config = ProcessingConfig(
            True,
            args.cache,
            args.write_staff_positions,
            False,
            -1,
        )
        xml_args = XmlGeneratorArguments(False, None, None)

        predictions, xml_path, seg_shape, runtime_s, notehead_mask, staff_mask = run_homr_on_image(
            working_image, config, xml_args, args.timeout, tuning
        )
        transform = compute_transform_info(working_image, seg_shape)
        
        mapped_predictions: List[BarlinePrediction] = []
        for pred in predictions:
            orig_bbox = map_pred_to_orig(pred.pred_bbox, transform)
            mapped_predictions.append(
                BarlinePrediction(
                    pred_bbox=pred.pred_bbox,
                    orig_bbox=orig_bbox,
                    system_index=pred.system_index,
                    staff_index=pred.staff_index,
                )
            )

        # Scale ThinBarlineConfig if SR is enabled
        tb_config = ThinBarlineConfig()
        if sr_scale > 1:
            tb_config = ThinBarlineConfig(
                min_height=tb_config.min_height * sr_scale,
                max_height=tb_config.max_height * sr_scale,
                max_width=tb_config.max_width * sr_scale,
                y_merge_tolerance=tb_config.y_merge_tolerance * sr_scale,
                y_center_tolerance=tb_config.y_center_tolerance * sr_scale,
                x_center_tolerance=tb_config.x_center_tolerance * sr_scale,
                adjacent_relaxed_span=tb_config.adjacent_relaxed_span * sr_scale,
                vertical_gap_fill=tb_config.vertical_gap_fill * sr_scale,
                left_margin_limit=tb_config.left_margin_limit * sr_scale,
                cluster_x_tolerance=tb_config.cluster_x_tolerance * sr_scale,
                cluster_reject_span=tb_config.cluster_reject_span * sr_scale,
                # Intensity / Ratio thresholds remain same
                pixel_threshold=tb_config.pixel_threshold,
                dark_pixel_threshold=tb_config.dark_pixel_threshold,
                adjacent_min_intensity=tb_config.adjacent_min_intensity,
                adjacent_relaxed_dark_ratio=tb_config.adjacent_relaxed_dark_ratio,
                max_intensity_std=tb_config.max_intensity_std,
                max_intensity_std_relaxed=tb_config.max_intensity_std_relaxed,
                notehead_dark_ratio=tb_config.notehead_dark_ratio,
                notehead_std_floor=tb_config.notehead_std_floor,
                allow_single_side_bright=tb_config.allow_single_side_bright,
                single_side_dark_ratio=tb_config.single_side_dark_ratio,
                cluster_reject_count=tb_config.cluster_reject_count,
            )

        extra_barlines = detect_thin_vertical_runs(
            working_image,
            [prediction.orig_bbox for prediction in mapped_predictions],
            config=tb_config,
        )

        def _centre(box: Tuple[int, int, int, int]) -> Tuple[float, float]:
            x1, y1, x2, y2 = box
            return (x1 + x2) / 2.0, (y1 + y2) / 2.0

        def _vertical_overlap_fraction(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> float:
            top = max(box_a[1], box_b[1])
            bottom = min(box_a[3], box_b[3])
            if bottom <= top:
                return 0.0
            overlap = bottom - top
            height_a = max(box_a[3] - box_a[1], 1)
            height_b = max(box_b[3] - box_b[1], 1)
            return overlap / float(max(height_a, height_b))

        for box in extra_barlines:
            cx_extra, cy_extra = _centre(box)
            box_height = max(box[3] - box[1], 1)
            replaced = False
            for idx, pred in enumerate(mapped_predictions):
                existing_box = pred.orig_bbox
                cx_existing, cy_existing = _centre(existing_box)
                if abs(cx_existing - cx_extra) > 2:
                    continue

                existing_height = max(existing_box[3] - existing_box[1], 1)
                centre_gap = abs(cy_existing - cy_extra)
                vertical_overlap = _vertical_overlap_fraction(existing_box, box)

                if vertical_overlap >= 0.6:
                    if box_height > existing_height:
                        mapped_predictions[idx] = BarlinePrediction(
                            pred_bbox=box,
                            orig_bbox=box,
                            system_index=-2,
                            staff_index=-1,
                        )
                    replaced = True
                    break

                max_height = max(box_height, existing_height)
                if centre_gap <= max_height:
                    if box_height >= existing_height:
                        mapped_predictions[idx] = BarlinePrediction(
                            pred_bbox=box,
                            orig_bbox=box,
                            system_index=-2,
                            staff_index=-1,
                        )
                    replaced = True
                    break

                # Same X column but belonging to a different staff system; keep scanning.

            if not replaced:
                mapped_predictions.append(
                    BarlinePrediction(
                        pred_bbox=box,
                        orig_bbox=box,
                        system_index=-2,
                        staff_index=-1,
                    )
                )

        # --- Heuristic 1: Notehead Proximity Rejection ---
        rejected_by_heuristic: List[BarlinePrediction] = []

        eprint(f"DEBUG: notehead_mask shape={notehead_mask.shape} dtype={notehead_mask.dtype}")
        eprint(f"DEBUG: notehead_mask min={notehead_mask.min()} max={notehead_mask.max()} unique={np.unique(notehead_mask)[:10]}")
        eprint(f"DEBUG: staff_mask shape={staff_mask.shape} dtype={staff_mask.dtype}")
        eprint(f"DEBUG: staff_mask min={staff_mask.min()} max={staff_mask.max()} unique={np.unique(staff_mask)[:10]}")
        
        # FIX: content is 0/1. Scale to 0/255 for correct bitwise operations and resize interpolation
        notehead_mask_255 = (notehead_mask * 255).astype(np.uint8)
        staff_mask_255 = (staff_mask * 255).astype(np.uint8)

        # Always compute resized masks for diagnostics/stats
        notehead_mask_resized = cv2.resize(
            notehead_mask_255,
            dsize=transform.original_shape,
            interpolation=cv2.INTER_NEAREST,
        )
        
        staff_mask_resized = cv2.resize(
            staff_mask_255,
            dsize=transform.original_shape,
            interpolation=cv2.INTER_NEAREST,
        )

        # DIAGNOSTICS: Save mask overlays (ENABLED for data collection)
        save_debug_mask_overlay(
            working_image, 
            notehead_mask_resized, 
            image_run_dir / f"{stem}_debug_notehead_resized_overlay.png"
        )
        
        save_debug_staff_overlay(
            working_image,
            staff_mask_resized,
            image_run_dir / f"{stem}_debug_staff_resized_overlay.png"
        )

        # DIAGNOSTICS: Compute and save stats for ALL candidates (ENABLED for data collection)
        compute_candidate_stats(
            mapped_predictions,
            notehead_mask_resized,
            staff_mask_resized,
            stem,
            image_run_dir
        )

        if STEM_CONTEXT_HEURISTICS["enabled"]:
            # Scale heuristics parameters if SR is enabled
            h_config = STEM_CONTEXT_HEURISTICS.copy()
            if sr_scale > 1:
                h_config["notehead_proximity_threshold_px"] *= sr_scale
                # Area overlap scales quadratically (sr_scale^2)
                h_config["min_overlap_px"] *= (sr_scale * sr_scale)
                h_config["max_height_px"] *= sr_scale
                h_config["max_width_px"] *= sr_scale
                h_config["cluster_gap_threshold_px"] *= sr_scale
            
            mapped_predictions, rejected_by_heuristic = filter_detections_by_notehead_proximity(
                mapped_predictions,
                notehead_mask_resized,
                h_config["notehead_proximity_threshold_px"],
                h_config["min_overlap_px"],
                h_config["max_height_px"],
                h_config["max_width_px"],
                staff_mask_resized,
                h_config["min_staff_crossings"],
                h_config["staff_crossing_enabled"],
            )
        # --- End Heuristic 1 ---

        # DIAGNOSTICS: Compute gaps (Phase 10)
        compute_and_save_gap_stats(mapped_predictions, stem, image_run_dir)

        # DIAGNOSTICS: Cluster Resolution Dry Run (Phase 11)
        if STEM_CONTEXT_HEURISTICS.get("cluster_resolution_dry_run", False):
            resolve_clusters_dry_run(
                mapped_predictions, 
                notehead_mask_resized, 
                stem, 
                image_run_dir,
                STEM_CONTEXT_HEURISTICS.get("cluster_gap_threshold_px", 15)
            )

        # DIAGNOSTICS: Tight Duplicate Dry Run (Phase 12)
        if STEM_CONTEXT_HEURISTICS.get("tight_duplicate_dry_run", False):
            resolve_tight_duplicates_dry_run(
                mapped_predictions,
                notehead_mask_resized,
                stem,
                image_run_dir
            )

        # DIAGNOSTICS: Measure Grid Export (Phase 13)
        if STEM_CONTEXT_HEURISTICS.get("measure_grid_export", False):
            export_measure_grid_candidates(
                mapped_predictions,
                notehead_mask_resized,
                stem,
                image_run_dir
            )

        ground_truth_path: Optional[Path] = None
        if stem in ground_truth_map:
            ground_truth_path = ground_truth_map[stem]
        elif args.ground_truth_dir:
            candidate = args.ground_truth_dir / f"{stem}.json"
            if candidate.exists():
                ground_truth_path = candidate
        else:
            auto_candidate = REPO_ROOT / "data" / f"ground_truth_{stem}.json"
            if auto_candidate.exists():
                ground_truth_path = auto_candidate

        ground_truth_summary[stem] = ground_truth_path

        metric = ImageMetrics(
            image=stem,
            num_predictions=len(mapped_predictions),
            num_ground_truth=0,
            true_positives=0,
            false_positives=len(mapped_predictions),
            false_negatives=0,
            precision=0.0,
            recall=0.0,
            f1=0.0,
            matches=[],
            soft_matches=[],
        )
        per_image_metrics.append(metric)

        # Scale predictions back to 1x for JSON export and correct metric calculation logic if external tools use it
        # BUT wait: compute_metrics logic (above) assumes pred_boxes are compatible with gt_boxes.
        # If we passed UP-SCALED mapped_predictions to compute_metrics, we would have 0 matches.
        # FIX: We need a separate list for metrics calculation that is scaled down.
        
        # Retroactive fix: The metric calculation above (lines 1830) used `mapped_predictions` (Upscaled).
        # We must re-do the metric calc with scaled-down predictions.
        
        metrics_predictions: List[BarlinePrediction] = []
        for pred in mapped_predictions:
            # Scale down bbox to original 1x coords
            orig_1x = tuple(int(c / sr_scale) for c in pred.orig_bbox)
            metrics_predictions.append(BarlinePrediction(
                pred_bbox=pred.pred_bbox, # This is internal homr bbox
                orig_bbox=orig_1x,
                system_index=pred.system_index,
                staff_index=pred.staff_index
            ))
            
        # Re-compute metrics with 1x predictions
        metric = ImageMetrics(
            image=stem,
            num_predictions=len(metrics_predictions),
            num_ground_truth=0,
            true_positives=0,
            false_positives=len(metrics_predictions),
            false_negatives=0,
            precision=0.0,
            recall=0.0,
            f1=0.0,
            matches=[],
            soft_matches=[]
        )
        match_result = None
        if ground_truth_path:
            gt_boxes = load_ground_truth_boxes(ground_truth_path)
            metric, match_result = compute_metrics(metrics_predictions, gt_boxes, args.iou_threshold)
            metric.image = stem
        else:
            metric.image = stem
            
        # Replace the last appended metric
        per_image_metrics[-1] = metric

        overlay_path = image_run_dir / f"{stem}_barline_overlay.png"
        draw_overlay(
            working_image,
            mapped_predictions, # Draw on UPSCALED image with UPSCALED preds
            overlay_path,
            matches=match_result.matches if match_result else None,
            soft_matches=match_result.soft_matches if match_result else None,
            rejected_detections=rejected_by_heuristic,
            false_positive_indices=match_result.false_positive_indices if match_result else None,
        )

        detections_path = image_run_dir / f"{stem}_detections.json"
        with detections_path.open("w", encoding="utf-8") as fh:
            json.dump(
                {
                    "image": str(image_path),
                    "predictions": [
                        {
                            "pred_bbox": pred.pred_bbox,
                            "orig_bbox": pred.orig_bbox,
                            "system_index": pred.system_index,
                            "staff_index": pred.staff_index,
                        }
                        for pred in metrics_predictions # Save 1x predictions
                    ],
                },
                fh,
                indent=2,
            )

    aggregate = aggregate_metrics(per_image_metrics)

    extra = {
        "ground_truth": {image: str(path) if path else None for image, path in ground_truth_summary.items()},
        "tuning": tuning,
    }
    write_metrics_json(run_dir, run_id, per_image_metrics, aggregate, extra)
    write_metrics_csv(run_dir, per_image_metrics, aggregate)
    write_readme(run_dir, run_id, per_image_metrics, aggregate, args, ground_truth_summary)
    write_compare_md(run_dir, per_image_metrics, aggregate, args.baseline_metrics)


if __name__ == "__main__":
    main()
