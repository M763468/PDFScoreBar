"""Utilities for comparing barline detections against ground truth boxes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

Box = Tuple[int, int, int, int]

BARLINE_DEFAULT_MIN_WIDTH = 12
BARLINE_X_MARGIN = 3
BARLINE_Y_MARGIN = 3

BARLINE_DUPLICATE_IOU_THRESHOLD = 0.3
BARLINE_DUPLICATE_X_TOLERANCE = 12
BARLINE_REPEAT_X_TOLERANCE = 40
BARLINE_VERTICAL_OVERLAP_THRESHOLD = 0.6
BARLINE_REPEAT_OVERLAP_THRESHOLD = 0.8


def _ensure_ordered(box: Box) -> Box:
    x1, y1, x2, y2 = box
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return x1, y1, x2, y2


def expand_barline_box(
    box: Box,
    *,
    min_width: int = BARLINE_DEFAULT_MIN_WIDTH,
    x_margin: int = BARLINE_X_MARGIN,
    y_margin: int = BARLINE_Y_MARGIN,
    bounds: Optional[Tuple[int, int]] = None,
) -> Box:
    """Pad a barline bounding box so IoU is less sensitive to tiny width offsets.

    The padding keeps the box centred while guaranteeing a minimal width and optional
    margins along X/Y. Bounds can be provided as (width, height) to clamp the result.
    """

    if min_width < 1:
        raise ValueError("min_width must be >= 1")
    x1, y1, x2, y2 = _ensure_ordered(box)
    width = max(1, x2 - x1)
    centre_x = (x1 + x2) / 2.0
    half_width = max(width / 2.0, min_width / 2.0)

    padded_x1 = int(round(centre_x - half_width)) - x_margin
    padded_x2 = int(round(centre_x + half_width)) + x_margin
    padded_y1 = y1 - y_margin
    padded_y2 = y2 + y_margin

    padded_x1 = max(0, padded_x1)
    padded_y1 = max(0, padded_y1)

    if bounds is not None:
        max_x, max_y = bounds
        if max_x <= 0 or max_y <= 0:
            raise ValueError("bounds must be positive")
        padded_x1 = min(padded_x1, max_x - 1)
        padded_x2 = min(padded_x2, max_x - 1)
        padded_y1 = min(padded_y1, max_y - 1)
        padded_y2 = min(padded_y2, max_y - 1)

    if padded_x2 <= padded_x1:
        padded_x2 = padded_x1 + 1
    if padded_y2 <= padded_y1:
        padded_y2 = padded_y1 + 1

    return padded_x1, padded_y1, padded_x2, padded_y2


def barline_iou(
    box_a: Box,
    box_b: Box,
    *,
    min_width: int = BARLINE_DEFAULT_MIN_WIDTH,
    x_margin: int = BARLINE_X_MARGIN,
    y_margin: int = BARLINE_Y_MARGIN,
    bounds: Optional[Tuple[int, int]] = None,
) -> float:
    """Compute IoU for slender barline boxes with symmetric padding applied."""

    ax1, ay1, ax2, ay2 = expand_barline_box(
        box_a,
        min_width=min_width,
        x_margin=x_margin,
        y_margin=y_margin,
        bounds=bounds,
    )
    bx1, by1, bx2, by2 = expand_barline_box(
        box_b,
        min_width=min_width,
        x_margin=x_margin,
        y_margin=y_margin,
        bounds=bounds,
    )

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
    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def _barline_centroid(box: Box) -> Tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def center_distance_x(box_a: Box, box_b: Box) -> float:
    """Return horizontal distance between centers of two boxes."""
    return abs((box_a[0] + box_a[2]) / 2.0 - (box_b[0] + box_b[2]) / 2.0)


def barline_vertical_overlap(box_a: Box, box_b: Box) -> float:
    """Return vertical overlap ratio between two boxes (range 0..1)."""

    top = max(box_a[1], box_b[1])
    bottom = min(box_a[3], box_b[3])
    if bottom <= top:
        return 0.0

    overlap = bottom - top
    height_a = max(box_a[3] - box_a[1], 1)
    height_b = max(box_b[3] - box_b[1], 1)
    return overlap / max(height_a, height_b)


def is_barline_match(
    pred: Box,
    gt: Box,
    rule_name: str = "baseline_iou",
    *,
    iou_threshold: float = 0.5,
    vov_threshold: float = 0.5,
    xdist_threshold: float = 12.0,
) -> bool:
    """Check if a predicted box matches a ground truth box according to specified rule."""
    if rule_name == "baseline_iou":
        return barline_iou(pred, gt) >= iou_threshold
    if rule_name == "center_anchor":
        vov = barline_vertical_overlap(pred, gt)
        xdist = center_distance_x(pred, gt)
        return vov >= vov_threshold and xdist <= xdist_threshold
    raise ValueError(f"Unknown rule_name: {rule_name}")


def get_barline_match_rank(
    pred: Box,
    gt: Box,
    rule_name: str = "baseline_iou",
) -> Tuple[float, ...]:
    """Return a comparable tuple representing the 'goodness' of a match.
    Higher values are better.
    """
    iou = barline_iou(pred, gt)
    vov = barline_vertical_overlap(pred, gt)
    xdist = center_distance_x(pred, gt)

    if rule_name == "baseline_iou":
        return (iou, vov, -xdist)
    if rule_name == "center_anchor":
        # Primary: vertical overlap, Secondary: horizontal closeness
        return (vov, -xdist, iou)
    raise ValueError(f"Unknown rule_name: {rule_name}")


@dataclass
class BarlineMatch:
    pred_index: int
    gt_index: int
    iou: float
    vov: float = 0.0
    xdist: float = 0.0


@dataclass
class BarlineSoftMatch:
    pred_index: int
    gt_index: Optional[int]
    iou: float
    x_distance: float
    vertical_overlap: float
    reason: str


@dataclass
class BarlineMatchResult:
    matches: List[BarlineMatch]
    false_positive_indices: List[int]
    false_negative_indices: List[int]
    soft_matches: List[BarlineSoftMatch]
    rule_name: str = "baseline_iou"


def expand_barline_boxes(
    boxes: Iterable[Box],
    *,
    min_width: int = BARLINE_DEFAULT_MIN_WIDTH,
    x_margin: int = BARLINE_X_MARGIN,
    y_margin: int = BARLINE_Y_MARGIN,
    bounds: Optional[Tuple[int, int]] = None,
) -> Tuple[Box, ...]:
    """Return a tuple of padded barline boxes for downstream use."""

    return tuple(
        expand_barline_box(
            box,
            min_width=min_width,
            x_margin=x_margin,
            y_margin=y_margin,
            bounds=bounds,
        )
        for box in boxes
    )


def greedy_barline_match(
    predictions: Iterable[Box],
    ground_truth: Iterable[Box],
    *,
    rule_name: str = "baseline_iou",
    iou_threshold: float = 0.5,
    vov_threshold: float = 0.5,
    xdist_threshold: float = 12.0,
    duplicate_iou_threshold: float = BARLINE_DUPLICATE_IOU_THRESHOLD,
    duplicate_x_tolerance: float = BARLINE_DUPLICATE_X_TOLERANCE,
    repeat_x_tolerance: float = BARLINE_REPEAT_X_TOLERANCE,
    vertical_overlap_threshold: float = BARLINE_VERTICAL_OVERLAP_THRESHOLD,
    repeat_vertical_overlap: float = BARLINE_REPEAT_OVERLAP_THRESHOLD,
) -> BarlineMatchResult:
    """Greedy matching based on specified rule (IoU or Center-Anchor)."""

    pred_boxes = list(predictions)
    gt_boxes = list(ground_truth)

    if not pred_boxes and not gt_boxes:
        return BarlineMatchResult([], [], [], [], rule_name=rule_name)

    # Candidate pairs that satisfy the rule
    candidates = []
    # All pairs for soft match / debug info
    best_soft_info = {}

    for p_idx, pred in enumerate(pred_boxes):
        strong_best = (0.0, None, float("inf"), 0.0)  # score, gt_idx, xdist, vov
        for g_idx, gt in enumerate(gt_boxes):
            iou = barline_iou(pred, gt)
            vov = barline_vertical_overlap(pred, gt)
            xdist = center_distance_x(pred, gt)

            # Rule check
            if is_barline_match(
                pred,
                gt,
                rule_name,
                iou_threshold=iou_threshold,
                vov_threshold=vov_threshold,
                xdist_threshold=xdist_threshold,
            ):
                rank = get_barline_match_rank(pred, gt, rule_name)
                candidates.append((rank, p_idx, g_idx, iou, vov, xdist))

            # Track for soft match (legacy logic)
            if strong_best[1] is None or iou > strong_best[0]:
                strong_best = (iou, g_idx, xdist, vov)

        best_soft_info[p_idx] = strong_best

    # Greedy selection
    candidates.sort(key=lambda x: x[0], reverse=True)
    matches: List[BarlineMatch] = []
    used_pred = set()
    used_gt = set()

    for _, p_idx, g_idx, iou, vov, xdist in candidates:
        if p_idx in used_pred or g_idx in used_gt:
            continue
        matches.append(BarlineMatch(p_idx, g_idx, iou, vov, xdist))
        used_pred.add(p_idx)
        used_gt.add(g_idx)

    # FP / FN
    unmatched_preds = set(range(len(pred_boxes))) - used_pred
    unmatched_gts = set(range(len(gt_boxes))) - used_gt

    false_positive_indices: List[int] = []
    soft_matches: List[BarlineSoftMatch] = []

    for pred_idx in sorted(unmatched_preds):
        best_score, best_gt, x_distance, overlap = best_soft_info[pred_idx]
        if best_gt is None:
            false_positive_indices.append(pred_idx)
            continue

        if best_score >= duplicate_iou_threshold and x_distance <= duplicate_x_tolerance:
            soft_matches.append(
                BarlineSoftMatch(
                    pred_index=pred_idx,
                    gt_index=best_gt,
                    iou=best_score,
                    x_distance=x_distance,
                    vertical_overlap=overlap,
                    reason="duplicate",
                )
            )
            continue

        if (
            overlap >= repeat_vertical_overlap
            and x_distance > duplicate_x_tolerance
            and x_distance <= repeat_x_tolerance
        ):
            soft_matches.append(
                BarlineSoftMatch(
                    pred_index=pred_idx,
                    gt_index=best_gt,
                    iou=best_score,
                    x_distance=x_distance,
                    vertical_overlap=overlap,
                    reason="repeat_like",
                )
            )
            continue

        false_positive_indices.append(pred_idx)

    false_negative_indices = sorted(unmatched_gts)

    return BarlineMatchResult(
        matches,
        false_positive_indices,
        false_negative_indices,
        soft_matches,
        rule_name=rule_name,
    )



def apply_left_margin_exclusion(
    match_result: BarlineMatchResult,
    predictions: Sequence[Box],
    ground_truth: Sequence[Box],
    *,
    margin_x: Optional[float] = None,
    max_width: Optional[int] = None,
    force_fp_predicate: Optional[callable[[int, Box, int, Box], bool]] = None,
) -> BarlineMatchResult:
    """Reclassify matches whose centres fall within a left margin as false positives."""

    if margin_x is None and force_fp_predicate is None:
        return match_result

    fp_indices = set(match_result.false_positive_indices)
    fn_indices = set(match_result.false_negative_indices)
    removed_preds = set()
    adjusted_matches: List[BarlineMatch] = []

    for match in match_result.matches:
        pred_box = predictions[match.pred_index]
        gt_box = ground_truth[match.gt_index]
        pred_center = (pred_box[0] + pred_box[2]) / 2.0
        gt_center = (gt_box[0] + gt_box[2]) / 2.0
        pred_width = max(pred_box[2] - pred_box[0], 1)

        force_fp = False
        if force_fp_predicate and force_fp_predicate(
            match.pred_index, pred_box, match.gt_index, gt_box
        ):
            force_fp = True

        if not force_fp and margin_x is not None:
            force_fp = (
                pred_center < margin_x
                and gt_center < margin_x
                and (max_width is None or pred_width <= max_width)
            )

        if force_fp:
            fp_indices.add(match.pred_index)
            fn_indices.add(match.gt_index)
            removed_preds.add(match.pred_index)
        else:
            adjusted_matches.append(match)

    adjusted_soft = [sm for sm in match_result.soft_matches if sm.pred_index not in removed_preds]

    return BarlineMatchResult(
        matches=adjusted_matches,
        false_positive_indices=sorted(fp_indices),
        false_negative_indices=sorted(fn_indices),
        soft_matches=adjusted_soft,
    )
