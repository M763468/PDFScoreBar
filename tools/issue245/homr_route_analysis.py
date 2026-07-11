#!/usr/bin/env python3
"""Detailed comparison helpers for Issue #245 HOMR route experiments."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from tools.issue245.run_focused_homr_probe import normalize_box, vertical_overlap_ratio

PredictionRecord = dict[str, Any]


def load_prediction_records(path: Path) -> list[PredictionRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    predictions = payload.get("predictions", []) if isinstance(payload, dict) else []
    records: list[PredictionRecord] = []
    for index, item in enumerate(predictions):
        if not isinstance(item, dict):
            continue
        box = normalize_box(item.get("orig_bbox") or item.get("pred_bbox"))
        if box is None:
            continue
        records.append(
            {
                "index": index,
                "box": box,
                "system_index": item.get("system_index"),
                "staff_index": item.get("staff_index"),
            }
        )
    return records


def match_prediction_records(
    left: list[PredictionRecord],
    right: list[PredictionRecord],
    *,
    x_distance_threshold: float = 12.0,
    vertical_overlap_threshold: float = 0.5,
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    candidates: list[tuple[float, float, int, int]] = []
    for left_index, left_record in enumerate(left):
        left_box = left_record["box"]
        left_x = (left_box[0] + left_box[2]) / 2.0
        for right_index, right_record in enumerate(right):
            right_box = right_record["box"]
            right_x = (right_box[0] + right_box[2]) / 2.0
            x_distance = abs(left_x - right_x)
            overlap = vertical_overlap_ratio(left_box, right_box)
            if x_distance <= x_distance_threshold and overlap >= vertical_overlap_threshold:
                candidates.append((x_distance, -overlap, left_index, right_index))

    matched_left: set[int] = set()
    matched_right: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for _, _, left_index, right_index in sorted(candidates):
        if left_index in matched_left or right_index in matched_right:
            continue
        matched_left.add(left_index)
        matched_right.add(right_index)
        pairs.append((left_index, right_index))

    left_only = [index for index in range(len(left)) if index not in matched_left]
    right_only = [index for index in range(len(right)) if index not in matched_right]
    return pairs, left_only, right_only


def _numeric_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "max": None}
    return {
        "count": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def summarize_records(records: list[PredictionRecord]) -> dict[str, Any]:
    widths = [float(record["box"][2] - record["box"][0]) for record in records]
    heights = [float(record["box"][3] - record["box"][1]) for record in records]
    system_indices = Counter(str(record.get("system_index")) for record in records)
    staff_indices = Counter(str(record.get("staff_index")) for record in records)
    return {
        "count": len(records),
        "system_index_counts": dict(sorted(system_indices.items())),
        "staff_index_counts": dict(sorted(staff_indices.items())),
        "thin_barline_tagged_count": sum(
            1 for record in records if record.get("system_index") == -2
        ),
        "bbox_width": _numeric_summary(widths),
        "bbox_height": _numeric_summary(heights),
    }


def compare_record_sets(
    left_name: str,
    left: list[PredictionRecord],
    right_name: str,
    right: list[PredictionRecord],
) -> dict[str, Any]:
    pairs, left_only_indices, right_only_indices = match_prediction_records(left, right)
    left_only = [left[index] for index in left_only_indices]
    right_only = [right[index] for index in right_only_indices]
    thin_only_count = sum(1 for record in left_only if record.get("system_index") == -2)
    return {
        "left": left_name,
        "right": right_name,
        "left_summary": summarize_records(left),
        "right_summary": summarize_records(right),
        "matched_count": len(pairs),
        "left_only_summary": summarize_records(left_only),
        "right_only_summary": summarize_records(right_only),
        "left_only_thin_barline_fraction": (
            thin_only_count / len(left_only) if left_only else None
        ),
        "semantic_equal": len(pairs) == len(left) == len(right),
        "left_only_examples": left_only[:20],
        "right_only_examples": right_only[:20],
    }
