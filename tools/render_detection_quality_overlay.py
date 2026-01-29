#!/usr/bin/env python3
"""Render TP/FP/FN overlays for barline detections."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Set, Tuple

import cv2

Color = Tuple[int, int, int]

TP_COLOR: Color = (0, 255, 0)  # Green
FP_COLOR: Color = (0, 0, 255)  # Red
FN_COLOR: Color = (255, 0, 255)  # Magenta (more visible on white)


def load_boxes(json_path: Path) -> List[Tuple[int, int, int, int]]:
    with json_path.open() as handle:
        payload = json.load(handle)
    boxes: List[Tuple[int, int, int, int]] = []
    for record in payload:
        loc = record.get("barline_location")
        if not loc or len(loc) != 4:
            continue
        boxes.append(tuple(int(v) for v in loc))
    return boxes


def load_detections(json_path: Path) -> List[Tuple[int, int, int, int]]:
    with json_path.open() as handle:
        payload = json.load(handle)
    records = payload.get("predictions", [])
    boxes: List[Tuple[int, int, int, int]] = []
    for record in records:
        loc = record.get("barline_location") or record.get("orig_bbox")
        if not loc or len(loc) != 4:
            continue
        boxes.append(tuple(int(v) for v in loc))
    return boxes


def load_matches(metrics_path: Path, image_key: str) -> Tuple[Set[int], Set[int]]:
    with metrics_path.open() as handle:
        payload = json.load(handle)
    images = payload.get("images", [])
    if not images:
        return set(), set()
    target = next((img for img in images if img.get("image") == image_key), None)
    if not target:
        return set(), set()
    matches = target.get("matches", [])
    matched_preds = {int(m["pred_index"]) for m in matches}
    matched_gts = {int(m["gt_index"]) for m in matches}
    return matched_preds, matched_gts


def draw_boxes(
    image,
    boxes: List[Tuple[int, int, int, int]],
    indices: Set[int],
    color: Color,
    thickness: int,
    label: str,
) -> None:
    for idx in indices:
        if idx < 0 or idx >= len(boxes):
            continue
        x1, y1, x2, y2 = boxes[idx]
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
        cv2.putText(
            image,
            f"{label}{idx}",
            (x1, max(0, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--detections", required=True, type=Path)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--image-key", required=True, help="Image key in metrics.json (e.g., page_001)"
    )
    parser.add_argument("--thickness", type=int, default=2)
    args = parser.parse_args()

    base = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load image: {args.image}")

    det_boxes = load_detections(args.detections)
    gt_boxes = load_boxes(args.ground_truth)
    matched_preds, matched_gts = load_matches(args.metrics, args.image_key)

    all_pred_indices = set(range(len(det_boxes)))
    all_gt_indices = set(range(len(gt_boxes)))
    fp_indices = all_pred_indices - matched_preds
    fn_indices = all_gt_indices - matched_gts

    overlay = base.copy()
    draw_boxes(overlay, det_boxes, matched_preds, TP_COLOR, args.thickness, "TP#")
    draw_boxes(overlay, det_boxes, fp_indices, FP_COLOR, args.thickness, "FP#")
    draw_boxes(overlay, gt_boxes, fn_indices, FN_COLOR, args.thickness, "FN#")

    blended = cv2.addWeighted(overlay, 0.6, base, 0.4, 0.0)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), blended):
        raise SystemExit(f"Failed to write output: {args.output}")


if __name__ == "__main__":
    main()
