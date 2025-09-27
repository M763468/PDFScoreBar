#!/usr/bin/env python3
"""Run the oemer pipeline and emit barline detections/metrics for evaluation."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Sequence, Tuple

import cv2

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover (Python <3.9)
    from backports.zoneinfo import ZoneInfo  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

OEMER_SRC = REPO_ROOT / "src/archive/oemer/oemer_src"
if str(OEMER_SRC) not in sys.path:
    sys.path.insert(0, str(OEMER_SRC))

from oemer import layers  # type: ignore
from oemer.ete import clear_data, extract, teaser  # type: ignore

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_IOU = 0.5


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


@dataclass
class BarlinePrediction:
    orig_bbox: Tuple[int, int, int, int]


def timestamp_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%SJST")


def run_id(prefix: str) -> str:
    return datetime.now(JST).strftime("%Y%m%dT%H%M%S%Z_" + prefix)


def load_ground_truth(path: Path) -> List[Tuple[int, int, int, int]]:
    records = json.loads(path.read_text())
    boxes: List[Tuple[int, int, int, int]] = []
    for record in records:
        loc = record.get("barline_location")
        if not loc or len(loc) != 4:
            continue
        boxes.append(tuple(int(v) for v in loc))
    return boxes


def extract_barline_boxes() -> List[Tuple[int, int, int, int]]:
    barlines = layers.get_layer("barlines")
    boxes: List[Tuple[int, int, int, int]] = []
    for barline in barlines:
        bbox = getattr(barline, "bbox", None)
        if bbox is None:
            continue
        boxes.append(tuple(int(v) for v in bbox))
    boxes.sort(key=lambda item: (item[1], item[0]))
    return boxes


def save_overlay(image_path: Path, boxes: Sequence[Tuple[int, int, int, int]], output_path: Path) -> None:
    base = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if base is None:
        raise RuntimeError(f"Failed to load base image: {image_path}")
    overlay = base.copy()
    color = (0, 0, 255)
    for (x1, y1, x2, y2) in boxes:
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
    blended = cv2.addWeighted(overlay, 0.65, base, 0.35, 0.0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), blended):
        raise RuntimeError(f"Failed to write overlay: {output_path}")


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

    scores = {}
    for pred_idx, pred in enumerate(predictions):
        for gt_idx, gt in enumerate(ground_truth):
            score = iou(pred, gt)
            if score >= threshold:
                scores[(pred_idx, gt_idx)] = score

    while scores:
        (best_pred, best_gt), best_score = max(scores.items(), key=lambda item: item[1])
        matches.append(MatchRecord(pred_index=best_pred, gt_index=best_gt, iou=best_score))
        unmatched_preds.discard(best_pred)
        unmatched_gts.discard(best_gt)
        scores = {
            key: value
            for key, value in scores.items()
            if key[0] != best_pred and key[1] != best_gt
        }

    return matches, sorted(unmatched_preds), sorted(unmatched_gts)


def compute_metrics(
    predictions: Sequence[BarlinePrediction],
    ground_truth: Sequence[Tuple[int, int, int, int]],
    threshold: float,
) -> ImageMetrics:
    boxes = [pred.orig_bbox for pred in predictions]
    matches, unmatched_preds, unmatched_gts = match_detections(boxes, ground_truth, threshold)
    tp = len(matches)
    fp = len(unmatched_preds)
    fn = len(unmatched_gts)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return ImageMetrics(
        image="",
        num_predictions=len(boxes),
        num_ground_truth=len(ground_truth),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        matches=matches,
    )


def aggregate_metrics(per_image: Sequence[ImageMetrics]) -> AggregateMetrics:
    tp = sum(metric.true_positives for metric in per_image)
    fp = sum(metric.false_positives for metric in per_image)
    fn = sum(metric.false_negatives for metric in per_image)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return AggregateMetrics(tp, fp, fn, precision, recall, f1)


def main() -> None:
    image_dir = Path("/workspace/data/evaluation/images")
    gt_path = Path("/workspace/data/evaluation/annotations/page_003/boxes_sorted.json")
    target_pages = [3]

    run_root = REPO_ROOT / "logs/oemer_eval" / run_id("baseline")
    run_root.mkdir(parents=True, exist_ok=True)

    gt_boxes = load_ground_truth(gt_path)
    per_image_metrics: List[ImageMetrics] = []

    for page in target_pages:
        image_path = image_dir / f"page_{page}.png"
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        page_dir = run_root / image_path.stem
        page_dir.mkdir(parents=True, exist_ok=True)

        clear_data()
        args = type("Args", (), {
            "img_path": str(image_path),
            "output_path": str(page_dir / f"{image_path.stem}.musicxml"),
            "use_tf": False,
            "save_cache": False,
            "without_deskew": False,
        })()

        musicxml_path = Path(extract(args))
        teaser_image = teaser()
        teaser_path = page_dir / f"{image_path.stem}_teaser.png"
        teaser_image.save(teaser_path)

        boxes = extract_barline_boxes()
        processed_image = layers.get_layer("original_image")
        base_image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if base_image is None:
            raise RuntimeError(f"Failed to load base image: {image_path}")
        proc_h, proc_w = processed_image.shape[:2]
        base_h, base_w = base_image.shape[:2]
        scale_x = base_w / float(proc_w)
        scale_y = base_h / float(proc_h)

        scaled_boxes = [
            (
                int(round(x1 * scale_x)),
                int(round(y1 * scale_y)),
                int(round(x2 * scale_x)),
                int(round(y2 * scale_y)),
            )
            for (x1, y1, x2, y2) in boxes
        ]

        predictions = [BarlinePrediction(orig_bbox=box) for box in scaled_boxes]

        detection_payload = {
            "predictions": [
                {
                    "barline_location": list(scaled),
                    "source_bbox": list(raw),
                }
                for scaled, raw in zip(scaled_boxes, boxes)
            ],
            "meta": {
                "detector": "oemer",
                "image": str(image_path),
                "timestamp": timestamp_jst(),
                "scale": {"x": scale_x, "y": scale_y},
            },
        }
        (page_dir / f"{image_path.stem}_detections.json").write_text(
            json.dumps(detection_payload, indent=2, ensure_ascii=False)
        )

        save_overlay(image_path, scaled_boxes, page_dir / f"{image_path.stem}_overlay.png")

        metric = compute_metrics(predictions, gt_boxes, DEFAULT_IOU)
        metric.image = image_path.stem
        per_image_metrics.append(metric)

        if musicxml_path.exists() and musicxml_path.parent != page_dir:
            target_path = page_dir / musicxml_path.name
            target_path.write_bytes(musicxml_path.read_bytes())

    aggregate = aggregate_metrics(per_image_metrics)
    payload = {
        "run_id": run_root.name,
        "timestamp": timestamp_jst(),
        "images": [
            {
                **asdict(metric),
                "matches": [asdict(match) for match in metric.matches],
            }
            for metric in per_image_metrics
        ],
        "aggregate": asdict(aggregate),
        "extra": {
            "detector": "oemer",
            "ground_truth": {metric.image: str(gt_path) for metric in per_image_metrics},
            "iou_threshold": DEFAULT_IOU,
        },
    }
    (run_root / "metrics.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    csv_lines = [
        "image,num_predictions,num_ground_truth,true_positives,false_positives,false_negatives,precision,recall,f1",
    ]
    for metric in per_image_metrics:
        csv_lines.append(
            f"{metric.image},{metric.num_predictions},{metric.num_ground_truth},{metric.true_positives},{metric.false_positives},{metric.false_negatives},{metric.precision:.6f},{metric.recall:.6f},{metric.f1:.6f}"
        )
    csv_lines.append(
        f"aggregate,-,-,{aggregate.true_positives},{aggregate.false_positives},{aggregate.false_negatives},{aggregate.precision:.6f},{aggregate.recall:.6f},{aggregate.f1:.6f}"
    )
    (run_root / "metrics.csv").write_text("\n".join(csv_lines) + "\n")

    summary = [
        "# oemer Evaluation Run",
        f"- Run ID: {run_root.name}",
        f"- Timestamp: {timestamp_jst()}",
        f"- Images processed: {len(per_image_metrics)}",
        f"- Ground truth: {gt_path}",
        "",
        "Outputs are stored per image under this directory.",
    ]
    (run_root / "README.md").write_text("\n".join(summary) + "\n")

    print(f"oemer evaluation artifacts written to {run_root}")


if __name__ == "__main__":
    main()
