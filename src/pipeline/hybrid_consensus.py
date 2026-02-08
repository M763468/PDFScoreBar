"""Hybrid consensus helpers for in-process detection pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from src.common.barline_evaluation import barline_iou

Box = Tuple[int, int, int, int]
logger = logging.getLogger(__name__)


def load_json_boxes(path: Path) -> List[Box]:
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


def phase4_hybrid_consensus(
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
