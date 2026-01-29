#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

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


def group_bands_into_systems(
    bands: List[Tuple[int, int, int, int]], gap_factor: float
) -> List[List[int]]:
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


def dedupe_x_centers(xs: List[int], min_gap: int) -> List[int]:
    if not xs:
        return []
    xs = sorted(xs)
    deduped = [xs[0]]
    for x in xs[1:]:
        if x - deduped[-1] >= min_gap:
            deduped.append(x)
    return deduped


def build_predictions(
    bands: List[Tuple[int, int, int, int]], per_band_xs: Dict[int, List[int]], width: int
) -> List[Box]:
    preds: List[Box] = []
    half = max(1, width // 2)
    for i, (x1, y1, x2, y2) in enumerate(bands):
        for x in per_band_xs.get(i, []):
            preds.append((int(x - half), int(y1), int(x + half), int(y2)))
    return preds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notehead-mask", type=Path, required=True)
    ap.add_argument("--staff-mask", type=Path, required=True)
    ap.add_argument("--min-gap", type=int, default=8)
    ap.add_argument("--gap-factor", type=float, default=1.5)
    ap.add_argument("--percentile", type=float, default=10.0)
    ap.add_argument("--width", type=int, default=4)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--metrics", type=Path, required=True)
    args = ap.parse_args()

    note_mask = cv2.imread(str(args.notehead_mask), cv2.IMREAD_GRAYSCALE)
    if note_mask is None:
        raise SystemExit(f"Failed to load notehead mask: {args.notehead_mask}")
    bands = extract_staff_bands(args.staff_mask)
    systems = group_bands_into_systems(bands, args.gap_factor)

    per_band_preds: Dict[int, List[int]] = {i: [] for i in range(len(bands))}
    system_metrics = []
    for sys_idx, sys_bands in enumerate(systems):
        if not sys_bands:
            continue
        x_min = min(bands[i][0] for i in sys_bands)
        x_max = max(bands[i][2] for i in sys_bands)
        y_min = min(bands[i][1] for i in sys_bands)
        y_max = max(bands[i][3] for i in sys_bands)
        crop = note_mask[y_min:y_max, x_min:x_max]
        if crop.size == 0:
            system_metrics.append({"system_index": sys_idx, "gap_count": 0})
            continue
        col_sum = crop.sum(axis=0).astype(np.float32)
        if col_sum.size == 0:
            system_metrics.append({"system_index": sys_idx, "gap_count": 0})
            continue
        thresh = np.percentile(col_sum, args.percentile)
        gap_xs = [x_min + i for i, v in enumerate(col_sum) if v <= thresh]
        gap_xs = dedupe_x_centers(gap_xs, args.min_gap)
        for band_i in sys_bands:
            per_band_preds[band_i] = list(gap_xs)
        system_metrics.append(
            {
                "system_index": sys_idx,
                "gap_count": len(gap_xs),
                "percentile": args.percentile,
                "threshold": float(thresh),
            }
        )

    preds = build_predictions(bands, per_band_preds, width=args.width)
    metrics = {
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
