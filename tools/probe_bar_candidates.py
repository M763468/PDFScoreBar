#!/usr/bin/env python3
"""Generate probe-bar candidates using ink ratio scanning within staff bands."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
Box = tuple[int, int, int, int]


@dataclass
class PageSpec:
    name: str
    image: Path
    staff_mask: Path


def load_staff_mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Missing staff mask: {path}")
    if mask.shape[:2] != shape:
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return mask


def staff_bands_from_mask(mask: np.ndarray, min_band_height: int = 6) -> list[tuple[int, int]]:
    ys = np.where(mask > 0)[0]
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


def rolling_sum(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1:
        return values.astype(np.int32)
    kernel = np.ones(width, dtype=np.int32)
    return np.convolve(values, kernel, mode="same")


def local_maxima(values: np.ndarray, min_value: float, min_distance: int) -> list[int]:
    indices = []
    last_idx = -min_distance
    for i in range(1, len(values) - 1):
        if values[i] < min_value:
            continue
        if values[i] >= values[i - 1] and values[i] >= values[i + 1]:
            if i - last_idx >= min_distance:
                indices.append(i)
                last_idx = i
    return indices


def draw_candidates(
    base_img: np.ndarray,
    bands: Iterable[tuple[int, int]],
    candidates: list[dict],
    out_path: Path,
) -> None:
    overlay = base_img.copy()
    h, w = overlay.shape[:2]
    mask_overlay = overlay.copy()
    for y1, y2 in bands:
        cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
    overlay = cv2.addWeighted(mask_overlay, 0.15, overlay, 0.85, 0.0)
    for cand in candidates:
        x1, y1, x2, y2 = cand["bbox"]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 200, 0), 2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), overlay)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--probe-width", type=int, default=4)
    parser.add_argument("--ink-threshold", type=int, default=180)
    parser.add_argument("--min-ratio", type=float, default=0.85)
    parser.add_argument("--min-peak-distance", type=int, default=6)
    parser.add_argument("--staff-mask-mode", choices=["staff", "staffs"], default="staff")
    args = parser.parse_args()

    pages = [
        PageSpec(
            name="page_001",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
            staff_mask=REPO_ROOT
            / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_3_staff.png",
        ),
        PageSpec(
            name="page_004",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
            staff_mask=REPO_ROOT
            / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_3_staff.png",
        ),
        PageSpec(
            name="page_10",
            image=REPO_ROOT / "data/training/images/page_10.png",
            staff_mask=REPO_ROOT
            / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_3_staff.png",
        ),
        PageSpec(
            name="page_15",
            image=REPO_ROOT / "data/training/images/page_15.png",
            staff_mask=REPO_ROOT
            / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_3_staff.png",
        ),
    ]
    if args.staff_mask_mode == "staffs":
        for page in pages:
            page.staff_mask = page.staff_mask.with_name(
                page.staff_mask.name.replace("debug_3_staff", "debug_15_staffs")
            )

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    per_page_root = output_root / "per_page"
    per_page_root.mkdir(parents=True, exist_ok=True)

    for page in pages:
        base_img = cv2.imread(str(page.image))
        if base_img is None:
            raise FileNotFoundError(f"Missing image: {page.image}")
        gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
        ink = (gray < args.ink_threshold).astype(np.uint8)
        staff_mask = load_staff_mask(page.staff_mask, gray.shape[:2])
        bands = staff_bands_from_mask(staff_mask)

        candidates: list[dict] = []
        for band_idx, (y1, y2) in enumerate(bands):
            band = ink[y1 : y2 + 1, :]
            band_h = max(1, y2 - y1 + 1)
            col_sums = band.sum(axis=0)
            stripe_sums = rolling_sum(col_sums, args.probe_width)
            ratios = stripe_sums / float(band_h * max(1, args.probe_width))
            peaks = local_maxima(ratios, args.min_ratio, args.min_peak_distance)
            for x in peaks:
                x1 = max(0, int(round(x - args.probe_width / 2)))
                x2 = min(gray.shape[1] - 1, int(round(x + args.probe_width / 2)))
                candidates.append(
                    {
                        "bbox": [x1, y1, x2, y2],
                        "ratio": float(ratios[x]),
                        "band": band_idx,
                    }
                )

        out_dir = per_page_root / page.name
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "probe_candidates.json").write_text(json.dumps(candidates, indent=2))
        draw_candidates(base_img, bands, candidates, out_dir / "probe_candidates_overlay.png")


if __name__ == "__main__":
    main()
