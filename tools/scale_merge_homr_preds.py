#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import List, Tuple

from src.common.barline_evaluation import barline_iou, greedy_barline_match

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


def scale_boxes(boxes: List[Box], scale: float) -> List[Box]:
    scaled = []
    for x1, y1, x2, y2 in boxes:
        scaled.append(
            (
                int(round(x1 * scale)),
                int(round(y1 * scale)),
                int(round(x2 * scale)),
                int(round(y2 * scale)),
            )
        )
    return scaled


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
    ap.add_argument("--base", type=Path, required=True, help="Base homr detections.json")
    ap.add_argument("--scaled", type=Path, required=True, help="Upscaled homr detections.json")
    ap.add_argument(
        "--scale-factor", type=float, required=True, help="Scale factor to map upscaled -> original"
    )
    ap.add_argument("--cluster-iou", type=float, default=0.5)
    ap.add_argument("--gt", type=Path, help="GT json (optional)")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--metrics", type=Path, required=True)
    args = ap.parse_args()

    base_boxes = load_homr_boxes(args.base)
    scaled_boxes = scale_boxes(load_homr_boxes(args.scaled), args.scale_factor)
    merged = base_boxes + scaled_boxes

    clusters = cluster_boxes(merged, args.cluster_iou)
    final_boxes = [choose_representative(cluster) for cluster in clusters]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(final_boxes, indent=2))

    metrics = {
        "num_base": len(base_boxes),
        "num_scaled": len(scaled_boxes),
        "num_final": len(final_boxes),
    }

    if args.gt and args.gt.exists():
        gt_data = json.loads(args.gt.read_text())
        gt_boxes = [
            tuple(item["barline_location"]) for item in gt_data if "barline_location" in item
        ]
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

    args.metrics.write_text(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
