"""Hybrid consensus helpers for in-process detection pipeline."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Iterable, List, Sequence

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
            if box[2] <= box[0] or box[3] <= box[1]:
                raise ValueError(f"box {index} has reversed or empty bounds")
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


def apply_hybrid_consensus_filter(
    *,
    baseline_boxes: Iterable[Sequence[int]],
    sr_boxes: Iterable[Sequence[int]],
    omr_boxes: Iterable[Sequence[int]],
    iou_thresh: float = 0.5,
) -> List[List[int]]:
    """Keep baseline boxes that are supported by SR or OMR predictions."""
    sr_list = list(sr_boxes)
    omr_list = list(omr_boxes)
    hybrid: List[List[int]] = []
    for box in baseline_boxes:
        if _has_match(box, sr_list, iou_thresh=iou_thresh) or _has_match(
            box, omr_list, iou_thresh=iou_thresh
        ):
            hybrid.append([int(v) for v in box])
    return hybrid
