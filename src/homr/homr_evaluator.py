#!/usr/bin/env python3
"""Run homr evaluations and compute barline detection metrics."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from concurrent.futures import Future

import cv2  # type: ignore
import numpy as np

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python <3.9 fallback
    from backports.zoneinfo import ZoneInfo  # type: ignore

# Ensure the local homr repository is importable before third-party homr installs.
REPO_ROOT = Path(__file__).resolve().parents[2]
HOMR_REPO = REPO_ROOT / "homr"
JST = ZoneInfo("Asia/Tokyo")
if str(HOMR_REPO) not in sys.path:
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


@dataclass
class TransformInfo:
    original_shape: Tuple[int, int]
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
class MatchRecord:
    pred_index: int
    gt_index: int
    iou: float


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
    matches: List[MatchRecord] = field(default_factory=list)


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
) -> Tuple[List[Any], np.ndarray, Any, Future[str], List[Any]]:
    predictions, debug = load_and_preprocess_predictions(
        image_path, config.enable_debug, config.enable_cache
    )
    symbols = predict_symbols(debug, predictions)

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

    return multi_staffs, predictions.preprocessed, debug, title_future, bar_line_boxes


def run_homr_on_image(
    image_path: Path,
    config: ProcessingConfig,
    xml_args: XmlGeneratorArguments,
    timeout_s: float,
    tuning: Dict[str, float],
) -> Tuple[List[BarlinePrediction], Optional[Path], Tuple[int, int], float]:
    start = time.perf_counter()
    (multi_staffs, preprocessed_image, debug, title_future, bar_line_boxes) = (
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
    return predictions, xml_path, seg_shape, runtime_s


def draw_overlay(
    original_image_path: Path,
    predictions: Sequence[BarlinePrediction],
    output_path: Path,
    color: Tuple[int, int, int] = (0, 0, 255),
    thickness: int = 2,
) -> None:
    image = cv2.imread(str(original_image_path))
    if image is None:
        raise RuntimeError(f"Failed to read image for overlay: {original_image_path}")
    for pred in predictions:
        x1, y1, x2, y2 = pred.orig_bbox
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
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


def iou(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(inter_x2 - inter_x1, 0)
    inter_h = max(inter_y2 - inter_y1, 0)
    inter_area = inter_w * inter_h

    area_a = max(ax2 - ax1, 0) * max(ay2 - ay1, 0)
    area_b = max(bx2 - bx1, 0) * max(by2 - by1, 0)

    union_area = area_a + area_b - inter_area
    if union_area == 0:
        return 0.0
    return inter_area / union_area


def match_detections(
    predictions: Sequence[Tuple[int, int, int, int]],
    ground_truth: Sequence[Tuple[int, int, int, int]],
    threshold: float,
) -> Tuple[List[MatchRecord], List[int], List[int]]:
    matches: List[MatchRecord] = []
    unmatched_preds = set(range(len(predictions)))
    unmatched_gts = set(range(len(ground_truth)))

    if not predictions or not ground_truth:
        return matches, sorted(unmatched_preds), sorted(unmatched_gts)

    iou_matrix: Dict[Tuple[int, int], float] = {}
    for pred_idx, pred in enumerate(predictions):
        for gt_idx, gt in enumerate(ground_truth):
            iou_value = iou(pred, gt)
            if iou_value >= threshold:
                iou_matrix[(pred_idx, gt_idx)] = iou_value

    while iou_matrix:
        best_pair = max(iou_matrix.items(), key=lambda item: item[1])[0]
        pred_idx, gt_idx = best_pair
        iou_value = iou_matrix.pop(best_pair)
        matches.append(MatchRecord(pred_index=pred_idx, gt_index=gt_idx, iou=iou_value))
        unmatched_preds.discard(pred_idx)
        unmatched_gts.discard(gt_idx)

        to_delete = [key for key in iou_matrix if pred_idx in key or gt_idx in key]
        for key in to_delete:
            iou_matrix.pop(key, None)

    return matches, sorted(unmatched_preds), sorted(unmatched_gts)


def compute_metrics(
    predictions: Sequence[BarlinePrediction],
    ground_truth_boxes: Sequence[Tuple[int, int, int, int]],
    threshold: float,
) -> ImageMetrics:
    pred_boxes = [pred.orig_bbox for pred in predictions]
    matches, unmatched_preds, unmatched_gts = match_detections(pred_boxes, ground_truth_boxes, threshold)

    tp = len(matches)
    fp = len(unmatched_preds)
    fn = len(unmatched_gts)

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
        matches=matches,
    )


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

        config = ProcessingConfig(
            True,
            args.cache,
            args.write_staff_positions,
            False,
            -1,
        )
        xml_args = XmlGeneratorArguments(False, None, None)

        predictions, xml_path, seg_shape, runtime_s = run_homr_on_image(
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

        overlay_path = image_run_dir / f"{stem}_barline_overlay.png"
        draw_overlay(working_image, mapped_predictions, overlay_path)

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
        )
        if ground_truth_path:
            gt_boxes = load_ground_truth_boxes(ground_truth_path)
            metric = compute_metrics(mapped_predictions, gt_boxes, args.iou_threshold)
            metric.image = stem
        else:
            metric.image = stem
        per_image_metrics.append(metric)

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
                        for pred in mapped_predictions
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
