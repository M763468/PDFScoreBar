#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

from src.common.barline_evaluation import greedy_barline_match


Box = Tuple[int, int, int, int]


def load_omr_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return [tuple(map(int, box)) for box in data if len(box) == 4]
    return []


def extract_staff_bands(mask_path: Path, min_height: int = 10) -> List[Tuple[int, int]]:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return []
    mask_bin = (mask > 0).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15))
    merged = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, kernel)
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
    bands = []
    for i in range(1, num_labels):
        x, y, w, h, _ = stats[i]
        if h < min_height:
            continue
        bands.append((y, y + h))
    bands.sort()
    return bands


def dedupe_x_centers(boxes: List[Box], min_gap: int = 3) -> List[int]:
    xs = sorted({int(round((x1 + x2) / 2)) for x1, _, x2, _ in boxes})
    if not xs:
        return []
    deduped = [xs[0]]
    for x in xs[1:]:
        if x - deduped[-1] >= min_gap:
            deduped.append(x)
    return deduped


def build_staff_barlines(xs: List[int], bands: List[Tuple[int, int]], width: int = 4) -> List[Box]:
    preds: List[Box] = []
    half = max(1, width // 2)
    for y1, y2 in bands:
        for x in xs:
            preds.append((int(x - half), int(y1), int(x + half), int(y2)))
    return preds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--omr", type=Path, required=True, help="omr-dln predictions.json")
    ap.add_argument("--staff-mask", type=Path, required=True, help="homr staff mask image (debug_3_staff.png)")
    ap.add_argument("--gt", type=Path, help="GT json (optional)")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--metrics", type=Path, required=True)
    args = ap.parse_args()

    omr_boxes = load_omr_boxes(args.omr)
    xs = dedupe_x_centers(omr_boxes)
    bands = extract_staff_bands(args.staff_mask)
    preds = build_staff_barlines(xs, bands)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(preds, indent=2))

    metrics = {
        "num_omr_boxes": len(omr_boxes),
        "num_unique_x": len(xs),
        "num_staff_bands": len(bands),
        "num_preds": len(preds),
    }

    if args.gt and args.gt.exists():
        gt_data = json.loads(args.gt.read_text())
        gt_boxes = [tuple(item["barline_location"]) for item in gt_data if "barline_location" in item]
        match = greedy_barline_match(preds, gt_boxes)
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
