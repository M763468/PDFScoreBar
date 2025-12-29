#!/usr/bin/env python3
"""Analyze ink-ratio behavior around FN positions for probe-scan."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
Box = tuple[int, int, int, int]


@dataclass
class PageSpec:
    name: str
    image: Path
    staff_mask: Path
    fn_boxes: Path


def load_boxes(path: Path) -> list[Box]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if isinstance(data, list):
        out: list[Box] = []
        for item in data:
            if isinstance(item, list) and len(item) == 4:
                out.append(tuple(map(int, item)))
        return out
    return []


def load_staff_mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Missing staff mask: {path}")
    if mask.shape[:2] != shape:
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return mask


def staff_bands_from_mask(mask: np.ndarray, min_band_height: int = 6) -> list[tuple[int, int]]:
    ys = np.unique(np.where(mask > 0)[0])
    if ys.size == 0:
        return []
    bands: list[tuple[int, int]] = []
    start = ys[0]
    prev = ys[0]
    for y in ys[1:]:
        if y == prev + 1:
            prev = y
            continue
        if prev - start + 1 >= min_band_height:
            bands.append((int(start), int(prev)))
        start = y
        prev = y
    if prev - start + 1 >= min_band_height:
        bands.append((int(start), int(prev)))
    return bands


def select_peaks(
    ratios: np.ndarray,
    min_ratio: float,
    min_peak_distance: int,
    max_per_band: int,
) -> list[int]:
    peaks = np.where(
        (ratios >= min_ratio)
        & (ratios >= np.roll(ratios, 1))
        & (ratios >= np.roll(ratios, -1))
    )[0]
    if peaks.size == 0:
        return []
    scores = [(int(x), float(ratios[x])) for x in peaks]
    scores.sort(key=lambda item: item[1], reverse=True)
    selected: list[int] = []
    for x, _ in scores:
        if any(abs(x - s) < min_peak_distance for s in selected):
            continue
        selected.append(x)
        if len(selected) >= max_per_band:
            break
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--probe-eval-root", type=Path, required=True)
    parser.add_argument("--probe-width", type=int, default=9)
    parser.add_argument("--ink-threshold", type=int, default=180)
    parser.add_argument("--min-ratio", type=float, default=0.85)
    parser.add_argument("--min-peak-distance", type=int, default=6)
    parser.add_argument("--max-per-band", type=int, default=8)
    parser.add_argument("--refine-window", type=int, default=4)
    parser.add_argument("--band-dilate", type=int, default=12)
    parser.add_argument("--band-min-height", type=int, default=6)
    parser.add_argument("--use-fn-height", action="store_true")
    args = parser.parse_args()

    pages = [
        PageSpec(
            name="page_001",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_3_staff.png",
            fn_boxes=args.probe_eval_root / "per_page" / "page_001" / "fn_boxes.json",
        ),
        PageSpec(
            name="page_004",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_3_staff.png",
            fn_boxes=args.probe_eval_root / "per_page" / "page_004" / "fn_boxes.json",
        ),
        PageSpec(
            name="page_10",
            image=REPO_ROOT / "data/training/images/page_10.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_3_staff.png",
            fn_boxes=args.probe_eval_root / "per_page" / "page_10" / "fn_boxes.json",
        ),
        PageSpec(
            name="page_15",
            image=REPO_ROOT / "data/training/images/page_15.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_3_staff.png",
            fn_boxes=args.probe_eval_root / "per_page" / "page_15" / "fn_boxes.json",
        ),
    ]

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    for page in pages:
        base_img = cv2.imread(str(page.image))
        if base_img is None:
            raise FileNotFoundError(f"Missing image: {page.image}")
        gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
        ink = (gray < args.ink_threshold).astype(np.uint8)
        staff_mask = load_staff_mask(page.staff_mask, gray.shape[:2])
        if args.band_dilate > 0:
            kernel = np.ones((args.band_dilate, 1), dtype=np.uint8)
            staff_mask = cv2.dilate(staff_mask, kernel, iterations=1)
        bands = staff_bands_from_mask(staff_mask, min_band_height=args.band_min_height)
        fn_boxes = load_boxes(page.fn_boxes)

        report = []
        for fn_idx, (bx1, by1, bx2, by2) in enumerate(fn_boxes):
            cy = (by1 + by2) / 2.0
            band_idx = None
            band = None
            for idx, (y1, y2) in enumerate(bands):
                if y1 <= cy <= y2:
                    band_idx = idx
                    band = (y1, y2)
                    break
            if band is None:
                report.append(
                    {
                        "fn_index": fn_idx,
                        "fn_bbox": [bx1, by1, bx2, by2],
                        "status": "no_band",
                    }
                )
                continue
            if args.use_fn_height:
                y1, y2 = int(by1), int(by2)
            else:
                y1, y2 = band
            band_h = max(1, y2 - y1 + 1)
            col_sums = ink[y1 : y2 + 1, :].sum(axis=0)
            stripe_sums = np.convolve(col_sums, np.ones(max(1, args.probe_width), dtype=np.int32), mode="same")
            ratios = stripe_sums / float(band_h * max(1, args.probe_width))

            fn_x = int(round((bx1 + bx2) / 2))
            fn_ratio = float(ratios[fn_x]) if 0 <= fn_x < ratios.size else 0.0
            local_left = max(0, fn_x - args.refine_window)
            local_right = min(ratios.size - 1, fn_x + args.refine_window)
            local_max = float(ratios[local_left : local_right + 1].max()) if local_right >= local_left else 0.0
            local_max_x = int(local_left + np.argmax(ratios[local_left : local_right + 1])) if local_right >= local_left else fn_x

            peaks = select_peaks(
                ratios,
                min_ratio=args.min_ratio,
                min_peak_distance=args.min_peak_distance,
                max_per_band=args.max_per_band,
            )
            near_peak = any(abs(fn_x - p) <= args.refine_window for p in peaks)

            reason = "ok"
            if fn_ratio < args.min_ratio and local_max < args.min_ratio:
                reason = "below_threshold"
            elif not peaks:
                reason = "no_peaks"
            elif not near_peak:
                reason = "peak_far_or_filtered"

            report.append(
                {
                    "fn_index": fn_idx,
                    "fn_bbox": [bx1, by1, bx2, by2],
                    "band_idx": band_idx,
                    "band": [y1, y2],
                    "fn_x": fn_x,
                    "fn_ratio": fn_ratio,
                    "local_max": local_max,
                    "local_max_x": local_max_x,
                    "near_peak": near_peak,
                    "selected_peaks": peaks[:10],
                    "reason": reason,
                }
            )

        out_path = output_root / f"{page.name}_fn_probe_report.json"
        out_path.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
