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


def draw_box(img: np.ndarray, box: Box, color: Tuple[int, int, int], thickness: int = 2) -> None:
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)


def put_text_block(img: np.ndarray, lines: List[str], origin=(8, 18)) -> None:
    x, y = origin
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA)
        y += 16


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--probe-scores", type=Path, required=True)
    ap.add_argument("--staff-mask", type=Path, required=True)
    ap.add_argument("--page-id", type=str, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--margin-factor", type=float, default=1.5)
    ap.add_argument("--gt-window", type=int, default=3)
    args = ap.parse_args()

    base = cv2.imread(str(args.base), cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")
    staff = cv2.imread(str(args.staff_mask), cv2.IMREAD_GRAYSCALE)
    if staff is None:
        raise SystemExit(f"Failed to load staff mask: {args.staff_mask}")
    if staff.shape[:2] != base.shape[:2]:
        staff = cv2.resize(staff, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_NEAREST)

    gt_boxes = load_gt_boxes(args.gt)
    probe_data = json.loads(args.probe_scores.read_text())

    # compute staff height from mask
    mask_bin = (staff > 0).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15))
    merged = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, kernel)
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
    heights = [stats[i][3] for i in range(1, num_labels) if stats[i][3] >= 8]
    staff_h = float(np.median(heights)) if heights else float(base.shape[0] * 0.05)
    margin = int(round(staff_h * args.margin_factor))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = []

    for idx, (x1, y1, x2, y2) in enumerate(gt_boxes):
        cx = int(round((x1 + x2) / 2))
        cy = int(round((y1 + y2) / 2))
        crop_x1 = max(0, cx - margin)
        crop_x2 = min(base.shape[1], cx + margin)
        crop_y1 = max(0, cy - margin)
        crop_y2 = min(base.shape[0], cy + margin)
        crop = base[crop_y1:crop_y2, crop_x1:crop_x2].copy()

        # find band with max overlap
        best_band = None
        best_overlap = 0
        for band_entry in probe_data:
            bx1, by1, bx2, by2 = band_entry["band_box"]
            overlap = max(0, min(y2, by2) - max(y1, by1))
            if overlap > best_overlap:
                best_overlap = overlap
                best_band = band_entry

        if best_band is None:
            continue

        bx1, by1, bx2, by2 = best_band["band_box"]
        # draw staff bounds (blue)
        draw_box(crop, (bx1 - crop_x1, by1 - crop_y1, bx2 - crop_x1, by2 - crop_y1), (255, 0, 0), 2)
        # draw GT (red)
        draw_box(crop, (x1 - crop_x1, y1 - crop_y1, x2 - crop_x1, y2 - crop_y1), (0, 0, 255), 2)

        topk = best_band["topk"][: args.topk]
        # draw probes
        top1 = topk[0] if topk else None
        for p in topk:
            px = int(p["x"])
            lx = px - crop_x1
            color = (0, 255, 0) if top1 and p["x"] == top1["x"] else (0, 255, 255)
            cv2.line(crop, (lx, by1 - crop_y1), (lx, by2 - crop_y1), color, 2)

        legend = [
            "Red=GT, Green=top-1 probe, Yellow=top-K probes, Blue=staff bounds",
            f"base: {args.base}",
            f"gt: {args.gt}",
            f"scores: {args.probe_scores}",
        ]
        put_text_block(crop, legend, origin=(8, 18))

        out_path = args.output_dir / f"{args.page_id}_fn_{idx:03d}_probe_overlay.png"
        cv2.imwrite(str(out_path), crop)

        # check if any top-K probe near GT x
        near = False
        for p in topk:
            if abs(p["x"] - cx) <= args.gt_window:
                near = True
                break
        summary.append(
            {"fn_id": idx, "overlay": str(out_path), "probe_near_gt": near, "topk": topk}
        )

    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
