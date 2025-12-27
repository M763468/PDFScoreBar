#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import List, Tuple, Optional

import cv2
import numpy as np

from src.common.barline_evaluation import greedy_barline_match, barline_iou


Box = Tuple[int, int, int, int]


def load_homr_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    preds = data.get("predictions", [])
    boxes = []
    for pred in preds:
        bbox = pred.get("orig_bbox")
        if bbox and len(bbox) == 4:
            boxes.append(tuple(map(int, bbox)))
    return boxes


def load_omr_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return [tuple(map(int, box)) for box in data if len(box) == 4]
    return []


def filter_by_staff_mask(
    boxes: List[Box],
    staff_mask_path: Optional[Path],
    min_overlap: float,
) -> List[Box]:
    if staff_mask_path is None:
        return boxes
    mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return boxes
    mask_bin = (mask > 0).astype(np.uint8)
    h, w = mask_bin.shape
    kept = []
    for x1, y1, x2, y2 in boxes:
        x1c = max(0, min(w, x1))
        x2c = max(0, min(w, x2))
        y1c = max(0, min(h, y1))
        y2c = max(0, min(h, y2))
        if x2c <= x1c or y2c <= y1c:
            continue
        area = (x2c - x1c) * (y2c - y1c)
        overlap = int(mask_bin[y1c:y2c, x1c:x2c].sum())
        ratio = overlap / float(area) if area > 0 else 0.0
        if ratio >= min_overlap:
            kept.append((x1, y1, x2, y2))
    return kept


def normalize_boxes_to_staff_mask(
    boxes: List[Box],
    staff_mask_path: Optional[Path],
) -> List[Box]:
    if staff_mask_path is None:
        return boxes
    mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return boxes
    mask_bin = (mask > 0).astype(np.uint8)
    h, w = mask_bin.shape
    normalized: List[Box] = []
    for x1, y1, x2, y2 in boxes:
        width = max(1, x2 - x1)
        x_center = int(round((x1 + x2) / 2))
        x_left = max(0, x_center - 1)
        x_right = min(w, x_center + 2)
        column = mask_bin[:, x_left:x_right]
        ys = np.where(column > 0)[0]
        if ys.size == 0:
            normalized.append((x1, y1, x2, y2))
            continue
        y_min = int(ys.min())
        y_max = int(ys.max())
        new_x1 = max(0, x_center - width // 2)
        new_x2 = min(w - 1, new_x1 + width)
        normalized.append((new_x1, y_min, new_x2, y_max))
    return normalized


def cluster_boxes(boxes: List[Box], iou_thresh: float) -> List[List[Box]]:
    clusters: List[List[Box]] = []
    for box in boxes:
        matched = None
        for cluster in clusters:
            if any(barline_iou(box, other) > iou_thresh for other in cluster):
                matched = cluster
                break
        if matched is None:
            clusters.append([box])
        else:
            matched.append(box)
    return clusters


def choose_representative(cluster: List[Box]) -> Box:
    best_box = cluster[0]
    best_score = -1.0
    for box in cluster:
        score = sum(barline_iou(box, other) for other in cluster)
        if score > best_score:
            best_score = score
            best_box = box
    return best_box


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--homr", type=Path, required=True, help="homr detections.json (per page)")
    ap.add_argument("--omr", type=Path, required=True, help="omr-dln predictions.json")
    ap.add_argument("--staff-mask", type=Path, help="homr staff mask image (debug_3_staff.png)")
    ap.add_argument("--min-staff-overlap", type=float, default=0.1)
    ap.add_argument("--cluster-iou", type=float, default=0.5)
    ap.add_argument("--normalize-omr-to-staff", action="store_true")
    ap.add_argument("--gt", type=Path, help="GT json (optional)")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--metrics", type=Path, required=True)
    args = ap.parse_args()

    homr_boxes = load_homr_boxes(args.homr)
    omr_boxes = load_omr_boxes(args.omr)
    if args.normalize_omr_to_staff:
        omr_boxes = normalize_boxes_to_staff_mask(omr_boxes, args.staff_mask)
    omr_filtered = filter_by_staff_mask(omr_boxes, args.staff_mask, args.min_staff_overlap)

    merged = homr_boxes + omr_filtered
    clusters = cluster_boxes(merged, args.cluster_iou)
    final_boxes = [choose_representative(cluster) for cluster in clusters]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w") as f:
        json.dump(final_boxes, f, indent=2)

    metrics = {
        "num_homr": len(homr_boxes),
        "num_omr": len(omr_boxes),
        "num_omr_after_staff": len(omr_filtered),
        "num_final": len(final_boxes),
    }

    if args.gt and args.gt.exists():
        gt_data = json.loads(args.gt.read_text())
        if isinstance(gt_data, list):
            gt_boxes = [tuple(item["barline_location"]) for item in gt_data if "barline_location" in item]
        else:
            gt_boxes = []
        match = greedy_barline_match(final_boxes, gt_boxes)
        tp = len(match.matches)
        fp = len(match.false_positive_indices)
        fn = len(match.false_negative_indices)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        metrics.update(
            {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "num_gt": len(gt_boxes),
            }
        )

    with args.metrics.open("w") as f:
        json.dump(metrics, f, indent=2)


if __name__ == "__main__":
    main()
