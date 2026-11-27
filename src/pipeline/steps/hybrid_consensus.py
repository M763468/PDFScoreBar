"""Hybrid consensus helpers for in-process detection pipeline."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Iterable, List, Sequence

from src.common import Box, barline_iou

logger = logging.getLogger(__name__)


def load_json_boxes(path: Path, *, strict: bool = True) -> List[Box]:
    """Read supported detection schemas; strict mode distinguishes corruption from empty results."""
    if not strict:
        return _load_json_boxes_tolerant(path)
    try:
        payload = json.loads(path.read_text())
        if isinstance(payload, list):
            rows = payload
            kind = "coordinates" if not rows or isinstance(rows[0], list) else "barline_location"
        elif isinstance(payload, dict) and isinstance(payload.get("predictions"), list):
            rows = payload["predictions"]
            kind = "orig_bbox"
        else:
            raise ValueError("expected a box list or predictions list")
        boxes = []
        for index, row in enumerate(rows):
            if kind == "coordinates":
                box = row if isinstance(row, list) else None
            else:
                box = row.get(kind) if isinstance(row, dict) else None
            if not isinstance(box, list) or len(box) != 4:
                raise ValueError(f"box {index} requires four coordinates")
            if any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in box
            ):
                raise ValueError(f"box {index} has non-finite or non-numeric coordinates")
            # Existing HOMR clipping can produce zero-width/height boxes at
            # image edges. Preserve their historical conversion and consensus behavior.
            if box[2] < box[0] or box[3] < box[1]:
                raise ValueError(f"box {index} has reversed bounds")
            boxes.append(tuple(int(v) for v in box))
        return boxes
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid detection JSON at {path}: {exc}") from exc


def _load_json_boxes_tolerant(path: Path) -> List[Box]:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        logger.warning("Invalid JSON: %s", path)
        return []
    if isinstance(payload, list):
        if not payload:
            return []
        if isinstance(payload[0], list):
            return [
                tuple(int(v) for v in row)
                for row in payload
                if isinstance(row, list) and len(row) == 4
            ]
        if isinstance(payload[0], dict) and "barline_location" in payload[0]:
            return [
                tuple(int(v) for v in row["barline_location"])
                for row in payload
                if isinstance(row, dict) and isinstance(row.get("barline_location"), list)
            ]
        return []
    if isinstance(payload, dict) and "predictions" in payload:
        boxes: List[Box] = []
        for pred in payload["predictions"]:
            if isinstance(pred, dict):
                bbox = pred.get("orig_bbox")
                if isinstance(bbox, list) and len(bbox) == 4:
                    boxes.append(tuple(int(v) for v in bbox))
        return boxes
    return []


def _has_match(
    query_box: Sequence[int], references: Iterable[Sequence[int]], iou_thresh: float = 0.5
) -> bool:
    return any(barline_iou(query_box, ref) > iou_thresh for ref in references)


# x4 staff-piece support (Issue #522) ------------------------------------------------
#
# Supports long original-HOMR barlines that span two or more staves (formerly
# supported by the removed OMR-DLN measure detector).  Such a box rarely reaches IoU>0.5 with the per-staff x4 HOMR
# strokes, although x4 HOMR independently detects each staff piece.  The box is
# supported only when *every* staff piece has its own x4 stroke, so a stroke seen on
# a single staff is never propagated to other staves.  Thresholds are expressed in
# the staff's ``unit_size``; detector and CNN thresholds are unchanged.

X4_PIECE_CENTER_UNITS = 0.5
X4_PIECE_MIN_HEIGHT_UNITS = 2.0
X4_PIECE_MIN_CONTAINED = 0.8


def _x4_supports_piece(
    piece: Sequence[int], sr_boxes: Sequence[Sequence[int]], unit: float
) -> bool:
    center = (piece[0] + piece[2]) / 2
    for stroke in sr_boxes:
        height = stroke[3] - stroke[1]
        if height < X4_PIECE_MIN_HEIGHT_UNITS * unit:
            continue
        if abs((stroke[0] + stroke[2]) / 2 - center) > X4_PIECE_CENTER_UNITS * unit:
            continue
        overlap = min(piece[3], stroke[3]) - max(piece[1], stroke[1])
        if overlap >= X4_PIECE_MIN_CONTAINED * height:
            return True
    return False


def x4_staff_piece_support(
    box: Sequence[int], sr_boxes: Sequence[Sequence[int]], staves: Sequence[Any]
) -> bool:
    """True when a multi-staff box has an x4 stroke inside every staff piece."""
    from src.common.barline_strokes import normalize_staff_stroke

    box = tuple(int(v) for v in box)
    pieces = normalize_staff_stroke(box, staves)
    if pieces == [(-1, box)]:
        return False
    return all(_x4_supports_piece(piece, sr_boxes, staves[i].unit_size) for i, piece in pieces)


def apply_x4_staff_piece_consensus_filter(
    *,
    baseline_boxes: Iterable[Sequence[int]],
    sr_boxes: Iterable[Sequence[int]],
    staves: Sequence[Any],
    iou_thresh: float = 0.5,
) -> List[List[int]]:
    """Keep baseline boxes supported by x4 HOMR IoU or by x4 staff-piece support."""
    sr_list = list(sr_boxes)
    hybrid: List[List[int]] = []
    for box in baseline_boxes:
        if _has_match(box, sr_list, iou_thresh=iou_thresh) or x4_staff_piece_support(
            box, sr_list, staves
        ):
            hybrid.append([int(v) for v in box])
    return hybrid


def staff_regions_from_mask(staff_mask: Path, image_path: Path) -> list[Any]:
    """Staff regions with unit sizes, extracted exactly as staff-stroke normalization does."""
    import cv2

    from src.common.barline_strokes import StaffRegion
    from src.measure_numbering.pipeline import StaffExtractor

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    height, width = image.shape[:2]
    return [
        StaffRegion((s.bbox.x1, s.bbox.y1, s.bbox.x2, s.bbox.y2), s.unit_size)
        for s in StaffExtractor().extract(staff_mask, (width, height))
        if s.unit_size
    ]


def apply_x4_iou_consensus_filter(
    *,
    baseline_boxes: Iterable[Sequence[int]],
    sr_boxes: Iterable[Sequence[int]],
    iou_thresh: float = 0.5,
) -> List[List[int]]:
    """Keep baseline boxes matched by an x4 HOMR box (staff-stroke seed agreement)."""
    sr_list = list(sr_boxes)
    return [
        [int(v) for v in box]
        for box in baseline_boxes
        if _has_match(box, sr_list, iou_thresh=iou_thresh)
    ]
