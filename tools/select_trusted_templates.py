#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]


def load_boxes(path: Path) -> List[Box]:
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


def load_gt_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    boxes = []
    for item in data:
        bbox = item.get("barline_location")
        if bbox and len(bbox) == 4:
            boxes.append(tuple(map(int, bbox)))
    return boxes


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


def draw_boxes(img, boxes, color, thickness=2):
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)


def put_text_block(img, lines, origin=(8, 18)):
    x, y = origin
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA)
        y += 16


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--staff-mask", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--page-id", type=str, required=True)
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--iou-thresh", type=float, default=0.1)
    args = ap.parse_args()

    base = cv2.imread(str(args.base), cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")
    staff = cv2.imread(str(args.staff_mask), cv2.IMREAD_GRAYSCALE)
    if staff is None:
        raise SystemExit(f"Failed to load staff mask: {args.staff_mask}")

    staff_h = compute_staff_height(staff)
    margin = int(round(staff_h * 1.0))

    gt_boxes = load_gt_boxes(args.gt)
    pred_boxes = load_boxes(args.pred)

    tps = []
    if gt_boxes:
        for p in pred_boxes:
            best_iou = 0.0
            best_gt = None
            for g in gt_boxes:
                val = iou(p, g)
                if val > best_iou:
                    best_iou = val
                    best_gt = g
            if best_iou >= args.iou_thresh and best_gt is not None:
                tps.append((best_iou, p, best_gt))
    else:
        # fallback: choose tallest predictions as templates when GT is unavailable (FN-only)
        for p in pred_boxes:
            tps.append((0.0, p, p))

    tps.sort(key=lambda t: (t[1][3] - t[1][1]), reverse=True)
    tps = tps[: args.count]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    heights = []

    for idx, (_, pred, gt) in enumerate(tps):
        x1, y1, x2, y2 = pred
        cx = int(round((x1 + x2) / 2))
        cy = int(round((y1 + y2) / 2))
        crop_x1 = max(0, cx - margin)
        crop_x2 = min(base.shape[1], cx + margin)
        crop_y1 = max(0, cy - margin)
        crop_y2 = min(base.shape[0], cy + margin)

        crop = base[crop_y1:crop_y2, crop_x1:crop_x2].copy()
        gt_local = (gt[0] - crop_x1, gt[1] - crop_y1, gt[2] - crop_x1, gt[3] - crop_y1)
        pred_local = (pred[0] - crop_x1, pred[1] - crop_y1, pred[2] - crop_x1, pred[3] - crop_y1)

        # template line in blue
        line_x = int(round((pred_local[0] + pred_local[2]) / 2))
        line_y1 = pred_local[1]
        line_y2 = pred_local[3]
        cv2.line(crop, (line_x, line_y1), (line_x, line_y2), (255, 0, 0), 2)

        draw_boxes(crop, [gt_local], (0, 0, 255), 2)
        draw_boxes(crop, [pred_local], (0, 255, 0), 2)
        legend = [
            "Red=GT, Green=trusted pred, Blue=template line",
            f"base: {args.base}",
            f"gt:   {args.gt}",
            f"pred: {args.pred}",
        ]
        put_text_block(crop, legend, origin=(8, 18))

        out_path = args.output_dir / f"{args.page_id}_template_{idx:02d}.png"
        cv2.imwrite(str(out_path), crop)
        heights.append(pred[3] - pred[1])

    (args.output_dir / "template_heights.json").write_text(json.dumps(heights, indent=2))


if __name__ == "__main__":
    main()
