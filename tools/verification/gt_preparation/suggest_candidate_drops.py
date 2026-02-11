#!/usr/bin/env python3
"""Suggest likely false-positive probe candidates with conservative heuristics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload = json.loads(path.read_text())
    records: Any = payload
    if isinstance(payload, dict) and "predictions" in payload:
        records = payload["predictions"]

    boxes: list[tuple[int, int, int, int]] = []
    if not isinstance(records, list):
        return boxes

    for item in records:
        if isinstance(item, list) and len(item) == 4:
            boxes.append(tuple(int(v) for v in item))
            continue
        if isinstance(item, dict):
            bbox = item.get("bbox", item.get("pred_bbox"))
            if bbox and len(bbox) == 4:
                boxes.append(tuple(int(v) for v in bbox))
    return boxes


def _median(vals: list[int]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _build_page_mask(gray: Any, *, paper_threshold: int) -> Any:
    """Return binary mask of the paper area (largest bright connected component)."""
    _, bright = cv2.threshold(gray, paper_threshold, 255, cv2.THRESH_BINARY)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bright, 8)
    if n_labels <= 1:
        return bright

    best_label = 1
    best_area = int(stats[1, cv2.CC_STAT_AREA])
    for i in range(2, n_labels):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area > best_area:
            best_area = area
            best_label = i
    page_mask = (labels == best_label).astype("uint8") * 255
    return page_mask


def _page_bbox_from_mask(mask: Any) -> tuple[int, int, int, int]:
    ys, xs = (mask > 0).nonzero()
    if len(xs) == 0 or len(ys) == 0:
        h, w = mask.shape[:2]
        return (0, 0, w - 1, h - 1)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


def _box_mask_overlap_ratio(mask: Any, box: tuple[int, int, int, int]) -> float:
    h_img, w_img = mask.shape[:2]
    x1, y1, x2, y2 = box
    y_lo, y_hi = max(0, min(y1, y2)), min(h_img, max(y1, y2))
    x_lo, x_hi = max(0, min(x1, x2)), min(w_img, max(x1, x2))
    if y_hi <= y_lo or x_hi <= x_lo:
        return 0.0
    crop = mask[y_lo:y_hi, x_lo:x_hi]
    return float((crop > 0).sum()) / float(crop.size)


def _center_in_bbox(box: tuple[int, int, int, int], bbox: tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = box
    cx = int(round((x1 + x2) / 2.0))
    cy = int(round((y1 + y2) / 2.0))
    bx1, by1, bx2, by2 = bbox
    return bx1 <= cx <= bx2 and by1 <= cy <= by2


def suggest_candidate_drops(
    *,
    image_path: Path,
    candidates_path: Path,
    existing_path: Path,
    staff_mask_path: Path | None,
    clef_mask_path: Path | None,
    left_margin_ratio: float,
    clef_left_ratio: float,
    min_height_median_ratio: float,
    ink_threshold: int,
    min_ink_ratio: float,
    paper_threshold: int,
    min_paper_overlap_ratio: float,
    min_staff_overlap_ratio: float,
) -> dict[str, Any]:
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"failed to load image: {image_path}")

    candidates = _load_boxes(candidates_path)
    existing = _load_boxes(existing_path)

    h_img, w_img = image.shape[:2]
    left_margin_px = int(w_img * left_margin_ratio)
    clef_left_px = int(w_img * clef_left_ratio)
    page_mask = _build_page_mask(image, paper_threshold=paper_threshold)
    page_bbox = _page_bbox_from_mask(page_mask)

    staff_mask = None
    if staff_mask_path:
        staff_mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
        if staff_mask is None:
            raise FileNotFoundError(f"failed to load staff mask: {staff_mask_path}")
        if staff_mask.shape[:2] != image.shape[:2]:
            staff_mask = cv2.resize(staff_mask, (w_img, h_img), interpolation=cv2.INTER_NEAREST)

    clef_mask = None
    if clef_mask_path:
        clef_mask = cv2.imread(str(clef_mask_path), cv2.IMREAD_GRAYSCALE)
        if clef_mask is None:
            raise FileNotFoundError(f"failed to load clef mask: {clef_mask_path}")
        if clef_mask.shape[:2] != image.shape[:2]:
            clef_mask = cv2.resize(clef_mask, (w_img, h_img), interpolation=cv2.INTER_NEAREST)

    existing_heights = [abs(b[3] - b[1]) for b in existing]
    median_h = _median(existing_heights)
    min_h_px = int(median_h * min_height_median_ratio) if median_h > 0 else 0

    keep: list[dict[str, Any]] = []
    drop: list[dict[str, Any]] = []

    for b in candidates:
        x1, y1, x2, y2 = [int(v) for v in b]
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        reasons: list[str] = []

        if max(x1, x2) <= left_margin_px:
            reasons.append("left_margin_zone")

        if clef_mask is not None and max(x1, x2) <= clef_left_px:
            clef_overlap = _box_mask_overlap_ratio(clef_mask, (x1, y1, x2, y2))
            if clef_overlap > 0.01:
                reasons.append("clef_mask_overlap")

        if min_h_px > 0 and h < min_h_px:
            reasons.append("too_short_vs_existing_median")

        center_in_page = _center_in_bbox((x1, y1, x2, y2), page_bbox)
        if not center_in_page:
            reasons.append("outside_page_region")

        staff_overlap = None
        if staff_mask is not None:
            staff_overlap = _box_mask_overlap_ratio(staff_mask, (x1, y1, x2, y2))
            if staff_overlap < min_staff_overlap_ratio:
                reasons.append("no_staff_overlap")

        y_lo, y_hi = max(0, min(y1, y2)), min(h_img, max(y1, y2))
        x_lo, x_hi = max(0, min(x1, x2)), min(w_img, max(x1, x2))
        ink_ratio = 0.0
        if y_hi > y_lo and x_hi > x_lo:
            crop = image[y_lo:y_hi, x_lo:x_hi]
            ink_ratio = float((crop < ink_threshold).sum()) / float(crop.size)
            if ink_ratio < min_ink_ratio:
                reasons.append("low_ink_ratio")

        item = {
            "bbox": [x1, y1, x2, y2],
            "width": w,
            "height": h,
            "ink_ratio": ink_ratio,
            "center_in_page": center_in_page,
            "staff_overlap": staff_overlap,
            "reasons": reasons,
        }
        if reasons:
            drop.append(item)
        else:
            keep.append(item)

    out = {
        "input": {
            "image": str(image_path),
            "candidates": str(candidates_path),
            "existing": str(existing_path),
            "staff_mask": str(staff_mask_path) if staff_mask_path else None,
            "clef_mask": str(clef_mask_path) if clef_mask_path else None,
        },
        "rules": {
            "left_margin_ratio": left_margin_ratio,
            "left_margin_px": left_margin_px,
            "clef_left_ratio": clef_left_ratio,
            "clef_left_px": clef_left_px,
            "min_height_median_ratio": min_height_median_ratio,
            "median_existing_height": median_h,
            "min_height_px": min_h_px,
            "ink_threshold": ink_threshold,
            "min_ink_ratio": min_ink_ratio,
            "paper_threshold": paper_threshold,
            "min_paper_overlap_ratio": min_paper_overlap_ratio,
            "min_staff_overlap_ratio": min_staff_overlap_ratio,
            "page_bbox": list(page_bbox),
        },
        "counts": {
            "candidates": len(candidates),
            "keep": len(keep),
            "drop_suggested": len(drop),
        },
        "drop_suggested": drop,
        "keep": keep,
    }
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--existing", type=Path, required=True)
    parser.add_argument("--staff-mask", type=Path, default=None)
    parser.add_argument("--clef-mask", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--left-margin-ratio", type=float, default=0.12)
    parser.add_argument("--clef-left-ratio", type=float, default=0.25)
    parser.add_argument("--min-height-median-ratio", type=float, default=0.6)
    parser.add_argument("--ink-threshold", type=int, default=180)
    parser.add_argument("--min-ink-ratio", type=float, default=0.18)
    parser.add_argument("--paper-threshold", type=int, default=200)
    parser.add_argument("--min-paper-overlap-ratio", type=float, default=0.6)
    parser.add_argument("--min-staff-overlap-ratio", type=float, default=0.01)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = suggest_candidate_drops(
        image_path=args.image,
        candidates_path=args.candidates,
        existing_path=args.existing,
        staff_mask_path=args.staff_mask,
        clef_mask_path=args.clef_mask,
        left_margin_ratio=args.left_margin_ratio,
        clef_left_ratio=args.clef_left_ratio,
        min_height_median_ratio=args.min_height_median_ratio,
        ink_threshold=args.ink_threshold,
        min_ink_ratio=args.min_ink_ratio,
        paper_threshold=args.paper_threshold,
        min_paper_overlap_ratio=args.min_paper_overlap_ratio,
        min_staff_overlap_ratio=args.min_staff_overlap_ratio,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps(out["counts"]))


if __name__ == "__main__":
    main()
