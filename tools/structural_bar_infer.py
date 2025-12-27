#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np


Box = Tuple[int, int, int, int]


def load_omr_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return [tuple(map(int, box)) for box in data if len(box) == 4]
    return []


def load_gt_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    return [tuple(item["barline_location"]) for item in data if "barline_location" in item]


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


def dedupe_x_centers(xs: List[int], min_gap: int) -> List[int]:
    if not xs:
        return []
    xs = sorted(xs)
    deduped = [xs[0]]
    for x in xs[1:]:
        if x - deduped[-1] >= min_gap:
            deduped.append(x)
    return deduped


def assign_boxes_to_bands(boxes: List[Box], bands: List[Tuple[int, int]]) -> Dict[int, List[Box]]:
    band_map: Dict[int, List[Box]] = {i: [] for i in range(len(bands))}
    for box in boxes:
        x1, y1, x2, y2 = box
        best_i = None
        best_overlap = 0
        for i, (by1, by2) in enumerate(bands):
            overlap = max(0, min(y2, by2) - max(y1, by1))
            if overlap > best_overlap:
                best_overlap = overlap
                best_i = i
        if best_i is not None:
            band_map[best_i].append(box)
    return band_map


def build_predictions(bands: List[Tuple[int, int]], xs: List[int], width: int = 4) -> List[Box]:
    preds: List[Box] = []
    half = max(1, width // 2)
    for y1, y2 in bands:
        for x in xs:
            preds.append((int(x - half), int(y1), int(x + half), int(y2)))
    return preds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--omr", type=Path, required=True)
    ap.add_argument("--staff-mask", type=Path, required=True)
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--min-gap", type=int, default=5)
    ap.add_argument("--width", type=int, default=4)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--metrics", type=Path, required=True)
    args = ap.parse_args()

    omr_boxes = load_omr_boxes(args.omr)
    gt_boxes = load_gt_boxes(args.gt)
    bands = extract_staff_bands(args.staff_mask)

    xs = []
    for x1, _, x2, _ in omr_boxes:
        xs.append(int(round((x1 + x2) / 2)))
    xs = dedupe_x_centers(xs, args.min_gap)

    preds = build_predictions(bands, xs, width=args.width)

    gt_by_band = assign_boxes_to_bands(gt_boxes, bands)
    pred_by_band = assign_boxes_to_bands(preds, bands)

    per_band = []
    match_count = 0
    for i in range(len(bands)):
        gt_count = len(gt_by_band.get(i, []))
        pred_count = len(pred_by_band.get(i, []))
        if gt_count == pred_count:
            match_count += 1
        per_band.append({"band_index": i, "gt_count": gt_count, "pred_count": pred_count})

    metrics = {
        "num_omr_boxes": len(omr_boxes),
        "num_unique_x": len(xs),
        "num_staff_bands": len(bands),
        "num_preds": len(preds),
        "staff_count_matches": match_count,
        "staff_count_total": len(bands),
        "per_band_counts": per_band,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(preds, indent=2))
    args.metrics.write_text(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
