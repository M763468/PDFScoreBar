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


def group_bands_into_systems(bands: List[Tuple[int, int, int, int]], gap_factor: float) -> List[List[int]]:
    if not bands:
        return []
    heights = [b[3] - b[1] for b in bands]
    median_h = float(np.median(heights)) if heights else 1.0
    systems: List[List[int]] = [[0]]
    for i in range(1, len(bands)):
        prev = bands[i - 1]
        curr = bands[i]
        gap = curr[1] - prev[3]
        if gap > median_h * gap_factor:
            systems.append([i])
        else:
            systems[-1].append(i)
    return systems


def assign_boxes_to_bands(boxes: List[Box], bands: List[Tuple[int, int, int, int]]) -> Dict[int, List[int]]:
    per_band: Dict[int, List[int]] = {i: [] for i in range(len(bands))}
    for x1, y1, x2, y2 in boxes:
        cx = int(round((x1 + x2) / 2))
        best_i = None
        best_overlap = 0
        for i, (_, by1, _, by2) in enumerate(bands):
            overlap = max(0, min(y2, by2) - max(y1, by1))
            if overlap > best_overlap:
                best_overlap = overlap
                best_i = i
        if best_i is not None:
            per_band[best_i].append(cx)
    return per_band


def dedupe_x_centers(xs: List[int], min_gap: int) -> List[int]:
    if not xs:
        return []
    xs = sorted(xs)
    deduped = [xs[0]]
    for x in xs[1:]:
        if x - deduped[-1] >= min_gap:
            deduped.append(x)
    return deduped


def resample_positions(xs: List[int], target: int) -> List[int]:
    if target <= 0 or not xs:
        return []
    xs = sorted(xs)
    if len(xs) == target:
        return xs
    if len(xs) > target:
        idxs = np.linspace(0, len(xs) - 1, target).round().astype(int)
        return [xs[i] for i in idxs]
    min_x, max_x = xs[0], xs[-1]
    if target == 1:
        return [int(round((min_x + max_x) / 2))]
    step = (max_x - min_x) / float(target - 1)
    return [int(round(min_x + i * step)) for i in range(target)]


def build_predictions(bands: List[Tuple[int, int, int, int]], per_band_xs: Dict[int, List[int]], width: int) -> List[Box]:
    preds: List[Box] = []
    half = max(1, width // 2)
    for i, (x1, y1, x2, y2) in enumerate(bands):
        for x in per_band_xs.get(i, []):
            preds.append((int(x - half), int(y1), int(x + half), int(y2)))
    return preds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--omr", type=Path, required=True)
    ap.add_argument("--staff-mask", type=Path, required=True)
    ap.add_argument("--min-gap", type=int, default=8)
    ap.add_argument("--gap-factor", type=float, default=1.5)
    ap.add_argument("--width", type=int, default=4)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--metrics", type=Path, required=True)
    args = ap.parse_args()

    omr_boxes = load_omr_boxes(args.omr)
    bands = extract_staff_bands(args.staff_mask)
    per_band_xs = assign_boxes_to_bands(omr_boxes, bands)
    for i in per_band_xs:
        per_band_xs[i] = dedupe_x_centers(per_band_xs[i], args.min_gap)

    systems = group_bands_into_systems(bands, args.gap_factor)
    per_band_preds: Dict[int, List[int]] = {i: [] for i in range(len(bands))}
    system_metrics = []
    for sys_idx, sys_bands in enumerate(systems):
        counts = [len(per_band_xs.get(i, [])) for i in sys_bands]
        target = max(counts) if counts else 0
        union_xs: List[int] = []
        for band_i in sys_bands:
            union_xs.extend(per_band_xs.get(band_i, []))
        union_xs = dedupe_x_centers(union_xs, args.min_gap)
        resampled = resample_positions(union_xs, target)
        for band_i in sys_bands:
            per_band_preds[band_i] = list(resampled)
        system_metrics.append(
            {
                "system_index": sys_idx,
                "band_indices": sys_bands,
                "target_count": target,
                "union_count": len(union_xs),
            }
        )

    preds = build_predictions(bands, per_band_preds, width=args.width)
    metrics = {
        "num_omr_boxes": len(omr_boxes),
        "num_staff_bands": len(bands),
        "num_preds": len(preds),
        "systems": systems,
        "per_band_pred_counts": [len(per_band_preds.get(i, [])) for i in range(len(bands))],
        "system_metrics": system_metrics,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(preds, indent=2))
    args.metrics.write_text(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
