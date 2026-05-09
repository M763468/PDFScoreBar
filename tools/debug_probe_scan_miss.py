#!/usr/bin/env python3
"""Verify Issue 120 probe-scan low-ratio x-peak rescue on a target GT box."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from src.pipeline.probe_detector import detect_probe_scan
from src.pipeline.probe_detector.bands import BandSelectionConfig, resolve_bands

DEFAULT_IMAGE = Path("data/evaluation2/images/Shostakovich-Festival_Overture_Va/page_008.png")
DEFAULT_STAFF_MASK = Path(
    "logs/hybrid_generalization/verification_full_v12_restore/"
    "Shostakovich-Festival_Overture_Va/baseline/batch/page_008/page_008_staff_mask.png"
)
DEFAULT_GT_BOX = (1045, 3669, 1049, 3786)
DEFAULT_OUTPUT_DIR = Path("logs/issue120_probe_scan_xpeak_low_ratio/page_008_gt0")


def _parse_box(value: str) -> tuple[int, int, int, int]:
    parts = [int(v.strip()) for v in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--gt-box must be x1,y1,x2,y2")
    return tuple(parts)  # type: ignore[return-value]


def _center(box: Sequence[int]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _candidate_hits_gt(candidates: Sequence[Sequence[int]], gt_box: Sequence[int]) -> bool:
    gt_cx, _ = _center(gt_box)
    for cand in candidates:
        cx, _ = _center(cand)
        vertical_overlap = max(0, min(cand[3], gt_box[3]) - max(cand[1], gt_box[1]))
        if abs(cx - gt_cx) <= 20 and vertical_overlap > 0:
            return True
    return False


def _load_existing_boxes(path: Path | None) -> list[tuple[int, int, int, int]]:
    if path is None or not path.exists():
        return []
    data = json.loads(path.read_text())
    boxes = []
    for item in data:
        box = item.get("box", item.get("bbox")) if isinstance(item, dict) else item
        if isinstance(box, list) and len(box) == 4:
            boxes.append(tuple(int(v) for v in box))
    return boxes


def _ratio_snapshot(
    *,
    image: np.ndarray,
    band: tuple[int, int],
    gt_box: Sequence[int],
    ink_threshold: int,
    probe_width: int,
) -> dict[str, object]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ink = (gray < ink_threshold).astype(np.uint8)
    y1, y2 = band
    band_h = max(1, y2 - y1 + 1)
    col_sums = ink[y1 : y2 + 1, :].sum(axis=0)
    stripe_sums = np.convolve(col_sums, np.ones(probe_width, dtype=np.int32), mode="same")
    ratios = stripe_sums / float(band_h * probe_width)

    gt_cx, _ = _center(gt_box)
    gt_col = int(round(gt_cx))
    left = max(0, gt_col - 12)
    right = min(len(ratios) - 1, gt_col + 12)
    neighbor_vals = [ratios[i] for i in range(left, right + 1) if i != gt_col]
    neighbor_median = float(np.median(neighbor_vals)) if neighbor_vals else 0.0
    xpeak = float(ratios[gt_col] / neighbor_median) if neighbor_median > 0 else None
    return {
        "gt_col": gt_col,
        "band": [int(y1), int(y2)],
        "band_height": int(band_h),
        "gt_height": int(abs(gt_box[3] - gt_box[1])),
        "ratio_at_gt": float(ratios[gt_col]),
        "neighbor_median": neighbor_median,
        "xpeak_at_gt": xpeak,
    }


def run_case(
    *,
    image: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[tuple[int, int, int, int]],
    gt_box: Sequence[int],
    output_dir: Path,
    label: str,
    enable_low_ratio_rescue: bool,
    min_ratio: float,
    low_ratio_min: float,
    xpeak_min: float,
    min_run_ratio: float,
    ink_threshold: int,
    probe_width: int,
    band_source: str,
) -> dict[str, object]:
    debug_path = output_dir / f"{label}_debug.png"
    candidates = detect_probe_scan(
        base_img=image,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        band_source=band_source,
        ink_threshold=ink_threshold,
        min_ratio=min_ratio,
        probe_width=probe_width,
        max_per_band=100,
        save_row_profile=True,
        scan_x_peak_low_ratio_rescue=enable_low_ratio_rescue,
        scan_x_peak_low_ratio_min=low_ratio_min,
        scan_x_peak_low_ratio_min_run_ratio=min_run_ratio,
        scan_x_peak_ratio_min=xpeak_min,
        debug_path=debug_path,
    )
    debug_json = debug_path.with_suffix(".json")
    statuses: dict[str, int] = {}
    if debug_json.exists():
        records = json.loads(debug_json.read_text()).get("records", [])
        for rec in records:
            status = str(rec.get("status"))
            statuses[status] = statuses.get(status, 0) + 1
    return {
        "label": label,
        "candidate_count": len(candidates),
        "target_gt_hit": _candidate_hits_gt(candidates, gt_box),
        "debug_json": str(debug_json),
        "debug_png": str(debug_path),
        "statuses": statuses,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--staff-mask", type=Path, default=DEFAULT_STAFF_MASK)
    parser.add_argument("--existing-boxes", type=Path)
    parser.add_argument("--gt-box", type=_parse_box, default=DEFAULT_GT_BOX)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--band-source", default="staff_mask")
    parser.add_argument("--ink-threshold", type=int, default=180)
    parser.add_argument("--min-ratio", type=float, default=0.85)
    parser.add_argument("--low-ratio-min", type=float, default=0.30)
    parser.add_argument("--xpeak-min", type=float, default=1.5)
    parser.add_argument("--min-run-ratio", type=float, default=0.0)
    parser.add_argument("--probe-width", type=int, default=4)
    args = parser.parse_args()

    image = cv2.imread(str(args.image))
    if image is None:
        raise FileNotFoundError(args.image)
    staff_mask = cv2.imread(str(args.staff_mask), cv2.IMREAD_GRAYSCALE)
    if staff_mask is None:
        raise FileNotFoundError(args.staff_mask)
    if staff_mask.shape[:2] != image.shape[:2]:
        staff_mask = cv2.resize(
            staff_mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST
        )

    existing_boxes = _load_existing_boxes(args.existing_boxes)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    bands = resolve_bands(
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        row_stats=None,
        config=BandSelectionConfig(
            band_source=args.band_source,
            band_cluster_max_dist=None,
            band_min_row_count=3,
        ),
    )
    _, gt_cy = _center(args.gt_box)
    target_band = next((band for band in bands if band[0] <= gt_cy <= band[1]), None)
    if target_band is None:
        raise RuntimeError(f"GT center y={gt_cy} did not fall in any resolved band.")

    summary = {
        "inputs": {
            "image": str(args.image),
            "staff_mask": str(args.staff_mask),
            "existing_boxes": str(args.existing_boxes) if args.existing_boxes else None,
            "gt_box": list(args.gt_box),
            "band_source": args.band_source,
            "ink_threshold": args.ink_threshold,
            "min_ratio": args.min_ratio,
            "low_ratio_min": args.low_ratio_min,
            "xpeak_min": args.xpeak_min,
            "min_run_ratio": args.min_run_ratio,
            "probe_width": args.probe_width,
        },
        "ratio_snapshot": _ratio_snapshot(
            image=image,
            band=target_band,
            gt_box=args.gt_box,
            ink_threshold=args.ink_threshold,
            probe_width=args.probe_width,
        ),
        "runs": [
            run_case(
                image=image,
                staff_mask=staff_mask,
                existing_boxes=existing_boxes,
                gt_box=args.gt_box,
                output_dir=args.output_dir,
                label="baseline",
                enable_low_ratio_rescue=False,
                min_ratio=args.min_ratio,
                low_ratio_min=args.low_ratio_min,
                xpeak_min=args.xpeak_min,
                min_run_ratio=args.min_run_ratio,
                ink_threshold=args.ink_threshold,
                probe_width=args.probe_width,
                band_source=args.band_source,
            ),
            run_case(
                image=image,
                staff_mask=staff_mask,
                existing_boxes=existing_boxes,
                gt_box=args.gt_box,
                output_dir=args.output_dir,
                label="xpeak_low_ratio_rescue",
                enable_low_ratio_rescue=True,
                min_ratio=args.min_ratio,
                low_ratio_min=args.low_ratio_min,
                xpeak_min=args.xpeak_min,
                min_run_ratio=args.min_run_ratio,
                ink_threshold=args.ink_threshold,
                probe_width=args.probe_width,
                band_source=args.band_source,
            ),
        ],
    }
    out_path = args.output_dir / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
