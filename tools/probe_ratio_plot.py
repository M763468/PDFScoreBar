#!/usr/bin/env python3
"""Plot ink-ratio curves per staff band with GT/FP markers."""
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
    gt: Path


def load_boxes(path: Path) -> list[Box]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if isinstance(data, list):
        out: list[Box] = []
        for item in data:
            if isinstance(item, list) and len(item) == 4:
                out.append(tuple(map(int, item)))
            elif isinstance(item, dict) and "barline_location" in item:
                box = item["barline_location"]
                if isinstance(box, list) and len(box) == 4:
                    out.append(tuple(map(int, box)))
        return out
    return []


def load_staff_mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Missing staff mask: {path}")
    if mask.shape[:2] != shape:
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return mask


def staff_bands_from_mask(mask: np.ndarray, min_band_height: int = 1) -> list[tuple[int, int]]:
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


def rolling_sum(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1:
        return values.astype(np.int32)
    kernel = np.ones(width, dtype=np.int32)
    return np.convolve(values, kernel, mode="same")


def draw_ratio_plot(
    ratios: np.ndarray,
    width: int,
    height: int,
    threshold: float,
    gt_xs: list[int],
    fn_xs: list[int],
    fp_xs: list[int],
) -> np.ndarray:
    plot = np.full((height, width, 3), 255, dtype=np.uint8)
    if ratios.size == 0:
        return plot

    xs = np.arange(width)
    ys = (1.0 - np.clip(ratios, 0.0, 1.0)) * (height - 1)
    pts = np.stack([xs, ys], axis=1).astype(np.int32)
    cv2.polylines(plot, [pts], isClosed=False, color=(40, 90, 200), thickness=1)

    thr_y = int(round((1.0 - threshold) * (height - 1)))
    cv2.line(plot, (0, thr_y), (width - 1, thr_y), (0, 140, 255), 1)

    for x in gt_xs:
        if 0 <= x < width:
            cv2.line(plot, (x, 0), (x, height - 1), (0, 200, 0), 1)
    for x in fn_xs:
        if 0 <= x < width:
            cv2.line(plot, (x, 0), (x, height - 1), (200, 0, 200), 1)
    for x in fp_xs:
        if 0 <= x < width:
            cv2.line(plot, (x, 0), (x, height - 1), (0, 0, 255), 1)

    cv2.putText(plot, "ratio", (6, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    cv2.putText(plot, "GT", (60, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 0), 1)
    cv2.putText(plot, "FN", (90, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 0, 200), 1)
    cv2.putText(plot, "FP", (120, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
    cv2.putText(plot, f"thr={threshold:.2f}", (150, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 140, 255), 1)
    return plot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--probe-width", type=int, default=9)
    parser.add_argument("--ink-threshold", type=int, default=180)
    parser.add_argument("--min-ratio", type=float, default=0.85)
    parser.add_argument("--staff-mask-mode", choices=["staff", "staffs"], default="staff")
    parser.add_argument("--plot-height", type=int, default=220)
    parser.add_argument("--band-min-height", type=int, default=1)
    parser.add_argument("--band-dilate", type=int, default=0)
    parser.add_argument("--only-fn-bands", action="store_true")
    parser.add_argument("--probe-width-mode", choices=["fixed", "median_pred"], default="fixed")
    parser.add_argument("--overlay-score-alpha", type=float, default=0.18)
    args = parser.parse_args()

    pages = [
        PageSpec(
            name="page_001",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_3_staff.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_001_boxes_sorted.json",
        ),
        PageSpec(
            name="page_004",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_3_staff.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_004_boxes_sorted.json",
        ),
        PageSpec(
            name="page_10",
            image=REPO_ROOT / "data/training/images/page_10.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_3_staff.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_10_boxes_sorted.json",
        ),
        PageSpec(
            name="page_15",
            image=REPO_ROOT / "data/training/images/page_15.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_3_staff.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_15_boxes_sorted.json",
        ),
    ]
    if args.staff_mask_mode == "staffs":
        for page in pages:
            page.staff_mask = page.staff_mask.with_name(page.staff_mask.name.replace("debug_3_staff", "debug_15_staffs"))

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    for page in pages:
        base_img = cv2.imread(str(page.image))
        if base_img is None:
            raise FileNotFoundError(f"Missing image: {page.image}")
        gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
        if args.ink_threshold < 0:
            otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            ink = (gray < otsu).astype(np.uint8)
            ink_threshold = int(otsu)
        else:
            ink = (gray < args.ink_threshold).astype(np.uint8)
            ink_threshold = int(args.ink_threshold)
        staff_mask = load_staff_mask(page.staff_mask, gray.shape[:2])
        if args.band_dilate > 0:
            kernel = np.ones((args.band_dilate, 1), dtype=np.uint8)
            staff_mask = cv2.dilate(staff_mask, kernel, iterations=1)
        bands = staff_bands_from_mask(staff_mask, min_band_height=args.band_min_height)

        gt_boxes = load_boxes(page.gt)
        fp_path = args.eval_root / "per_page" / page.name / "fp_boxes.json"
        fp_boxes = load_boxes(fp_path) if fp_path.exists() else []
        fn_path = args.eval_root / "per_page" / page.name / "fn_boxes.json"
        fn_boxes = load_boxes(fn_path) if fn_path.exists() else []
        pred_path = args.eval_root / "per_page" / page.name / "geom_kept.json"
        pred_boxes = load_boxes(pred_path) if pred_path.exists() else []

        width = gray.shape[1]
        per_page_dir = output_root / page.name
        per_page_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "ink_threshold": ink_threshold,
            "probe_width": args.probe_width,
            "min_ratio": args.min_ratio,
            "bands": bands,
            "probe_width_mode": args.probe_width_mode,
            "only_fn_bands": args.only_fn_bands,
            "band_min_height": args.band_min_height,
            "band_dilate": args.band_dilate,
        }
        (per_page_dir / "ratio_meta.json").write_text(json.dumps(meta, indent=2))

        for band_idx, (y1, y2) in enumerate(bands):
            if args.only_fn_bands:
                has_fn = False
                for bx1, by1, bx2, by2 in fn_boxes:
                    cy = (by1 + by2) / 2.0
                    if y1 <= cy <= y2:
                        has_fn = True
                        break
                if not has_fn:
                    continue
            if args.probe_width_mode == "median_pred":
                widths = [
                    abs(bx2 - bx1)
                    for bx1, by1, bx2, by2 in pred_boxes
                    if y1 <= (by1 + by2) / 2.0 <= y2
                ]
                band_width = int(np.median(widths)) if widths else args.probe_width
            else:
                band_width = args.probe_width
            kernel = np.ones(max(1, band_width), dtype=np.int32)
            band = ink[y1 : y2 + 1, :]
            band_h = max(1, y2 - y1 + 1)
            col_sums = band.sum(axis=0)
            stripe_sums = np.convolve(col_sums, kernel, mode="same")
            ratios = stripe_sums / float(band_h * max(1, band_width))

            gt_xs = []
            for bx1, by1, bx2, by2 in gt_boxes:
                cy = (by1 + by2) / 2.0
                if y1 <= cy <= y2:
                    gt_xs.append(int(round((bx1 + bx2) / 2)))
            fn_xs = []
            for bx1, by1, bx2, by2 in fn_boxes:
                cy = (by1 + by2) / 2.0
                if y1 <= cy <= y2:
                    fn_xs.append(int(round((bx1 + bx2) / 2)))
            fp_xs = []
            for bx1, by1, bx2, by2 in fp_boxes:
                cy = (by1 + by2) / 2.0
                if y1 <= cy <= y2:
                    fp_xs.append(int(round((bx1 + bx2) / 2)))

            plot = draw_ratio_plot(
                ratios,
                width=width,
                height=args.plot_height,
                threshold=args.min_ratio,
                gt_xs=gt_xs,
                fn_xs=fn_xs,
                fp_xs=fp_xs,
            )
            # Overlay faint staff image to keep x alignment intuitive.
            band_img = base_img[y1 : y2 + 1, :]
            if band_img.size:
                band_resized = cv2.resize(band_img, (width, args.plot_height), interpolation=cv2.INTER_AREA)
                alpha = min(max(args.overlay_score_alpha, 0.0), 0.9)
                plot = cv2.addWeighted(band_resized, alpha, plot, 1 - alpha, 0.0)
            cv2.putText(
                plot,
                f"band {band_idx:02d} y={y1}-{y2} w={band_width}px",
                (6, args.plot_height - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (40, 40, 40),
                1,
            )
            out_path = per_page_dir / f"ratio_band_{band_idx:02d}.png"
            cv2.imwrite(str(out_path), plot)


if __name__ == "__main__":
    main()
