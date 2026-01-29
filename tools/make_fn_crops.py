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


def draw_boxes(
    img: np.ndarray, boxes: List[Box], color: Tuple[int, int, int], thickness: int = 2
) -> None:
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)


def overlay_mask_blue(img: np.ndarray, mask: np.ndarray, alpha: float = 0.3) -> np.ndarray:
    if mask.ndim == 2:
        mask_color = np.zeros_like(img)
        mask_color[:, :, 0] = mask
    else:
        mask_color = mask
    blended = cv2.addWeighted(img, 1.0, mask_color, alpha, 0.0)
    return blended


def put_text_block(img: np.ndarray, lines: List[str], origin: Tuple[int, int] = (8, 18)) -> None:
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
    ap.add_argument("--margin-factor", type=float, default=1.5)
    args = ap.parse_args()

    base = cv2.imread(str(args.base), cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")
    staff = cv2.imread(str(args.staff_mask), cv2.IMREAD_GRAYSCALE)
    if staff is None:
        raise SystemExit(f"Failed to load staff mask: {args.staff_mask}")

    base_h, base_w = base.shape[:2]
    staff_h, staff_w = staff.shape[:2]
    base_w / float(staff_w)
    scale_y = base_h / float(staff_h)
    staff_height = compute_staff_height(staff) * scale_y
    margin = int(round(staff_height * args.margin_factor))

    gt_boxes = load_gt_boxes(args.gt)
    pred_boxes = load_pred_boxes(args.pred)

    staff_resized = cv2.resize(staff, (base_w, base_h), interpolation=cv2.INTER_NEAREST)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for idx, (x1, y1, x2, y2) in enumerate(gt_boxes):
        cx = int(round((x1 + x2) / 2))
        cy = int(round((y1 + y2) / 2))
        crop_x1 = max(0, cx - margin)
        crop_x2 = min(base_w, cx + margin)
        crop_y1 = max(0, cy - margin)
        crop_y2 = min(base_h, cy + margin)

        crop = base[crop_y1:crop_y2, crop_x1:crop_x2].copy()
        mask_crop = staff_resized[crop_y1:crop_y2, crop_x1:crop_x2]
        if mask_crop.size:
            crop = overlay_mask_blue(crop, mask_crop, alpha=0.25)

        # draw GT box
        gt_local = [(x1 - crop_x1, y1 - crop_y1, x2 - crop_x1, y2 - crop_y1)]
        draw_boxes(crop, gt_local, (0, 0, 255), 2)

        # draw pred boxes that intersect crop
        pred_local = []
        for px1, py1, px2, py2 in pred_boxes:
            if px2 < crop_x1 or px1 > crop_x2 or py2 < crop_y1 or py1 > crop_y2:
                continue
            pred_local.append((px1 - crop_x1, py1 - crop_y1, px2 - crop_x1, py2 - crop_y1))
        draw_boxes(crop, pred_local, (0, 255, 0), 2)

        legend = [
            "Red=GT barline, Green=pred, Blue=staff mask",
            f"base: {args.base}",
            f"gt:   {args.gt}",
            f"pred: {args.pred}",
            f"staff:{args.staff_mask}",
        ]
        put_text_block(crop, legend, origin=(8, 18))

        out_path = args.output_dir / f"{args.page_id}_fn_{idx:03d}_crop_overlay.png"
        cv2.imwrite(str(out_path), crop)


if __name__ == "__main__":
    main()
