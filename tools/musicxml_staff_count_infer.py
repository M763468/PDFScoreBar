#!/usr/bin/env python3
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]


def extract_staff_bands(mask_path: Path, min_height: int = 10) -> List[Tuple[int, int, int, int]]:
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
        bands.append((x, y, x + w, y + h))
    bands.sort(key=lambda b: b[1])
    return bands


def load_gt_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    return [tuple(item["barline_location"]) for item in data if "barline_location" in item]


def assign_boxes_to_bands(boxes: List[Box], bands: List[Tuple[int, int, int, int]]) -> List[int]:
    counts = [0 for _ in bands]
    for x1, y1, x2, y2 in boxes:
        best_i = None
        best_overlap = 0
        for i, (_, by1, _, by2) in enumerate(bands):
            overlap = max(0, min(y2, by2) - max(y1, by1))
            if overlap > best_overlap:
                best_overlap = overlap
                best_i = i
        if best_i is not None:
            counts[best_i] += 1
    return counts


def count_measures(xml_path: Path) -> int:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    # MusicXML namespace handling
    ns = {"m": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
    measures = root.findall(".//m:measure", ns) if ns else root.findall(".//measure")
    return len(measures)


def build_predictions(
    bands: List[Tuple[int, int, int, int]],
    count: int,
    width: int = 4,
) -> List[Box]:
    preds: List[Box] = []
    if count <= 0:
        return preds
    half = max(1, width // 2)
    for x1, y1, x2, y2 in bands:
        span = max(1, x2 - x1)
        step = span / float(count - 1) if count > 1 else span
        xs = [int(round(x1 + i * step)) for i in range(count)]
        for x in xs:
            preds.append((int(x - half), int(y1), int(x + half), int(y2)))
    return preds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--musicxml", type=Path, required=True)
    ap.add_argument("--staff-mask", type=Path, required=True)
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--width", type=int, default=4)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--metrics", type=Path, required=True)
    args = ap.parse_args()

    bands = extract_staff_bands(args.staff_mask)
    measure_count = count_measures(args.musicxml)
    pred_count = measure_count + 1 if measure_count > 0 else 0

    preds = build_predictions(bands, pred_count, width=args.width)
    gt_boxes = load_gt_boxes(args.gt)
    gt_counts = assign_boxes_to_bands(gt_boxes, bands)
    pred_counts = [pred_count for _ in bands]

    match_count = sum(1 for gt, pr in zip(gt_counts, pred_counts) if gt == pr)
    per_band = [
        {"band_index": i, "gt_count": gt_counts[i], "pred_count": pred_counts[i]}
        for i in range(len(bands))
    ]

    metrics = {
        "measure_count": measure_count,
        "pred_count_per_staff": pred_count,
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
