"""Barline override helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.common.barline_evaluation import (
    BARLINE_DEFAULT_MIN_WIDTH,
    BARLINE_X_MARGIN,
    BARLINE_Y_MARGIN,
    barline_iou,
)


def normalize_barlines(raw_data: Any) -> List[List[int]]:
    if isinstance(raw_data, dict) and "predictions" in raw_data:
        records = raw_data.get("predictions", [])
    else:
        records = raw_data
    boxes: List[List[int]] = []
    if not isinstance(records, list):
        return boxes
    for item in records:
        if isinstance(item, dict):
            loc = item.get("barline_location") or item.get("orig_bbox") or item.get("pred_bbox")
        else:
            loc = item
        if not isinstance(loc, list) or len(loc) != 4:
            continue
        boxes.append([int(v) for v in loc])
    return boxes


def apply_barline_overrides(
    boxes: List[List[int]],
    overrides: List[Dict[str, Any]],
    *,
    page_index: int,
    iou_threshold: float = 0.5,
    min_width: int = BARLINE_DEFAULT_MIN_WIDTH,
    x_margin: int = BARLINE_X_MARGIN,
    y_margin: int = BARLINE_Y_MARGIN,
) -> Tuple[List[List[int]], Dict[str, int]]:
    removed_indices: set[int] = set()
    add_count = 0
    remove_requests = 0
    unmatched_remove = 0

    for item in overrides:
        if item.get("page") != page_index:
            continue
        op = item.get("op")
        bbox = item.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        bbox = [int(v) for v in bbox]
        if op == "remove":
            remove_requests += 1
            matched = False
            for idx, existing in enumerate(boxes):
                if idx in removed_indices:
                    continue
                iou = barline_iou(
                    tuple(existing),
                    tuple(bbox),
                    min_width=min_width,
                    x_margin=x_margin,
                    y_margin=y_margin,
                )
                if iou >= iou_threshold:
                    removed_indices.add(idx)
                    matched = True
            if not matched:
                unmatched_remove += 1
        elif op == "add":
            boxes.append(bbox)
            add_count += 1

    kept = [box for idx, box in enumerate(boxes) if idx not in removed_indices]
    stats = {
        "removed": len(removed_indices),
        "added": add_count,
        "remove_requests": remove_requests,
        "unmatched_remove": unmatched_remove,
    }
    return kept, stats


def merge_measure_overrides(
    *overrides_payloads: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged: Dict[str, Any] = {"overrides": []}
    for payload in overrides_payloads:
        if not payload:
            continue
        overrides = payload.get("overrides", [])
        if isinstance(overrides, list):
            merged["overrides"].extend(overrides)
    return merged
