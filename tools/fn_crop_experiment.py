#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]


def load_gt_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    boxes = []
    for item in data:
        bbox = item.get("barline_location")
        if bbox and len(bbox) == 4:
            boxes.append(tuple(map(int, bbox)))
    return boxes


def load_pred_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "predictions" in data:
        records = data["predictions"]
    else:
        records = data
    boxes = []
    for rec in records:
        if isinstance(rec, list) and len(rec) == 4:
            boxes.append(tuple(map(int, rec)))
            continue
        if isinstance(rec, dict):
            bbox = rec.get("orig_bbox") or rec.get("pred_bbox") or rec.get("barline_location")
            if bbox and len(bbox) == 4:
                boxes.append(tuple(map(int, bbox)))
    return boxes


def compute_staff_height(mask: np.ndarray) -> float:
    mask_bin = (mask > 0).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15))
    merged = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, kernel)
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
    heights = []
    for i in range(1, num_labels):
        _, _, _, h, _ = stats[i]
        if h >= 8:
            heights.append(h)
    if not heights:
        return float(mask.shape[0] * 0.05)
    return float(np.median(heights))


def draw_boxes(img: np.ndarray, boxes: List[Box], color: Tuple[int, int, int], thickness: int = 2) -> None:
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)


def put_text_block(img: np.ndarray, lines: List[str], origin: Tuple[int, int] = (8, 18)) -> None:
    x, y = origin
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA)
        y += 16


def iou(a: Box, b: Box) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / float(area_a + area_b - inter)


def detect_edge_bars(crop: np.ndarray, min_height_ratio: float, edge_margin_ratio: float) -> List[Box]:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    ink = 255 - gray
    _, bin_img = cv2.threshold(ink, 160, 255, cv2.THRESH_BINARY)
    h, w = bin_img.shape
    min_height = int(round(h * min_height_ratio))
    edge_start = int(round(w * (1.0 - edge_margin_ratio)))
    cols = []
    for x in range(edge_start, w):
        if np.count_nonzero(bin_img[:, x]) >= min_height:
            cols.append(x)
    if not cols:
        return []
    # group contiguous columns
    groups = []
    start = cols[0]
    prev = cols[0]
    for x in cols[1:]:
        if x == prev + 1:
            prev = x
        else:
            groups.append((start, prev))
            start = x
            prev = x
    groups.append((start, prev))
    # choose rightmost group
    gx1, gx2 = max(groups, key=lambda g: g[1])
    return [(gx1, 0, gx2 + 1, h)]


def detect_double_bars(crop: np.ndarray, min_height_ratio: float, gap_min: int, gap_max: int) -> List[Box]:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    ink = 255 - gray
    _, bin_img = cv2.threshold(ink, 160, 255, cv2.THRESH_BINARY)
    h, w = bin_img.shape
    min_height = int(round(h * min_height_ratio))
    cols = []
    strengths = []
    for x in range(w):
        count = np.count_nonzero(bin_img[:, x])
        if count >= min_height:
            cols.append(x)
            strengths.append(count)
    if not cols:
        return []
    # group contiguous columns into segments
    segments = []
    start = cols[0]
    prev = cols[0]
    seg_strength = strengths[0]
    for x, s in zip(cols[1:], strengths[1:]):
        if x == prev + 1:
            prev = x
            seg_strength += s
        else:
            segments.append((start, prev, seg_strength))
            start = x
            prev = x
            seg_strength = s
    segments.append((start, prev, seg_strength))
    # find best pair within gap
    best = None
    for i in range(len(segments) - 1):
        a = segments[i]
        b = segments[i + 1]
        gap = b[0] - a[1] - 1
        if gap_min <= gap <= gap_max:
            score = a[2] + b[2]
            if best is None or score > best[0]:
                best = (score, a, b)
    if not best:
        return []
    _, a, b = best
    return [(a[0], 0, a[1] + 1, h), (b[0], 0, b[1] + 1, h)]


def detect_fragments(crop: np.ndarray, min_height_ratio: float) -> List[Box]:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    ink = 255 - gray
    _, bin_img = cv2.threshold(ink, 160, 255, cv2.THRESH_BINARY)
    h, w = bin_img.shape
    min_height = int(round(h * min_height_ratio))
    cols = []
    for x in range(w):
        if np.count_nonzero(bin_img[:, x]) >= min_height:
            cols.append(x)
    if not cols:
        return []
    groups = []
    start = cols[0]
    prev = cols[0]
    for x in cols[1:]:
        if x == prev + 1:
            prev = x
        else:
            groups.append((start, prev))
            start = x
            prev = x
    groups.append((start, prev))
    return [(gx1, 0, gx2 + 1, h) for gx1, gx2 in groups]


def snap_baseline_to_peak(crop: np.ndarray, baseline: List[Box], window: int) -> List[Box]:
    if not baseline:
        return []
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    ink = 255 - gray
    col_sum = ink.sum(axis=0).astype(np.float32)
    h, w = gray.shape[:2]
    snapped = []
    for x1, y1, x2, y2 in baseline:
        cx = int(round((x1 + x2) / 2))
        lo = max(0, cx - window)
        hi = min(w - 1, cx + window)
        if hi <= lo:
            peak = cx
        else:
            peak = int(np.argmax(col_sum[lo:hi + 1]) + lo)
        width = max(1, x2 - x1)
        half = max(1, width // 2)
        snapped.append((peak - half, 0, peak + half, h))
    snapped.sort(key=lambda b: b[0])
    deduped = []
    for b in snapped:
        if not deduped or b[0] - deduped[-1][0] >= 2:
            deduped.append(b)
    return deduped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--staff-mask", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--page-id", type=str, required=True)
    ap.add_argument("--fn-indices", type=str, required=True)
    ap.add_argument("--margin-factor", type=float, default=1.5)
    ap.add_argument("--method", type=str, choices=["edge", "double", "fragment", "snap"], required=True)
    ap.add_argument("--min-height-ratio", type=float, default=0.6)
    ap.add_argument("--edge-margin-ratio", type=float, default=0.2)
    ap.add_argument("--gap-min", type=int, default=2)
    ap.add_argument("--gap-max", type=int, default=6)
    ap.add_argument("--snap-window", type=int, default=8)
    ap.add_argument("--iou-thresh", type=float, default=0.1)
    args = ap.parse_args()

    base = cv2.imread(str(args.base), cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")
    staff = cv2.imread(str(args.staff_mask), cv2.IMREAD_GRAYSCALE)
    if staff is None:
        raise SystemExit(f"Failed to load staff mask: {args.staff_mask}")

    base_h, base_w = base.shape[:2]
    staff_h, staff_w = staff.shape[:2]
    scale_x = base_w / float(staff_w)
    scale_y = base_h / float(staff_h)
    staff_height = compute_staff_height(staff) * scale_y
    margin = int(round(staff_height * args.margin_factor))

    gt_boxes = load_gt_boxes(args.gt)
    pred_boxes = load_pred_boxes(args.pred)

    fn_indices = [int(x) for x in args.fn_indices.split(",") if x.strip()]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = []

    for idx in fn_indices:
        x1, y1, x2, y2 = gt_boxes[idx]
        cx = int(round((x1 + x2) / 2))
        cy = int(round((y1 + y2) / 2))
        crop_x1 = max(0, cx - margin)
        crop_x2 = min(base_w, cx + margin)
        crop_y1 = max(0, cy - margin)
        crop_y2 = min(base_h, cy + margin)

        crop = base[crop_y1:crop_y2, crop_x1:crop_x2].copy()
        gt_local = (x1 - crop_x1, y1 - crop_y1, x2 - crop_x1, y2 - crop_y1)

        baseline_local = []
        for px1, py1, px2, py2 in pred_boxes:
            if px2 < crop_x1 or px1 > crop_x2 or py2 < crop_y1 or py1 > crop_y2:
                continue
            baseline_local.append((px1 - crop_x1, py1 - crop_y1, px2 - crop_x1, py2 - crop_y1))

        if args.method == "edge":
            new_local = detect_edge_bars(crop, args.min_height_ratio, args.edge_margin_ratio)
        elif args.method == "double":
            new_local = detect_double_bars(crop, args.min_height_ratio, args.gap_min, args.gap_max)
        elif args.method == "fragment":
            new_local = detect_fragments(crop, args.min_height_ratio)
        else:
            new_local = snap_baseline_to_peak(crop, baseline_local, args.snap_window)

        # draw overlay
        draw_boxes(crop, [gt_local], (0, 0, 255), 2)
        draw_boxes(crop, baseline_local, (255, 0, 0), 2)  # blue baseline
        draw_boxes(crop, new_local, (0, 255, 0), 2)
        legend = [
            "Red=GT, Green=new pred, Blue=baseline pred",
            f"base: {args.base}",
            f"gt:   {args.gt}",
            f"pred: {args.pred}",
            f"method: {args.method}",
        ]
        put_text_block(crop, legend, origin=(8, 18))

        out_path = args.output_dir / f"{args.page_id}_fn_{idx:03d}_{args.method}_overlay.png"
        cv2.imwrite(str(out_path), crop)

        recovered = any(iou(gt_local, nb) >= args.iou_thresh for nb in new_local)
        summary.append(
            {
                "fn_id": idx,
                "crop": str(out_path),
                "recovered": recovered,
                "num_new": len(new_local),
            }
        )

    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
