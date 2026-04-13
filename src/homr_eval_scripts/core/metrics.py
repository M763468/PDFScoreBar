#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


from src.common.barline_evaluation import (
    BarlineMatch,
    BarlineMatchResult,
    BarlineSoftMatch,
    apply_left_margin_exclusion,
    greedy_barline_match,
)

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

from src.homr_eval_scripts.core.utils import (
    LEFT_MARGIN_FORCE_FP_GT_INDICES,
    LEFT_MARGIN_FORCE_FP_MAX_WIDTH,
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

    def _force_fp(
        pred_index: int,
        pred_box: Tuple[int, int, int, int],
        gt_index: int,
        gt_box: Tuple[int, int, int, int],
    ) -> bool:
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
