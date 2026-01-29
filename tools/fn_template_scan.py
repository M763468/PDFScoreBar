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


def load_template_heights(path: Path) -> List[int]:
    return json.loads(path.read_text())


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


def put_text_block(img, lines, origin=(8, 18)):
    x, y = origin
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA)
        y += 16


def draw_box(img, box, color, thickness=2):
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--staff-mask", type=Path, required=True)
    ap.add_argument("--template-heights", type=Path, required=True)
    ap.add_argument("--page-id", type=str, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--margin-factor", type=float, default=1.5)
    ap.add_argument("--search-mult", type=float, default=2.0)
    ap.add_argument("--topk", type=int, default=5)
    args = ap.parse_args()

    base = cv2.imread(str(args.base), cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")
    staff = cv2.imread(str(args.staff_mask), cv2.IMREAD_GRAYSCALE)
    if staff is None:
        raise SystemExit(f"Failed to load staff mask: {args.staff_mask}")

    staff_h = compute_staff_height(staff)
    margin = int(round(staff_h * args.margin_factor))
    search_half = int(round(staff_h * args.search_mult))

    gt_boxes = load_gt_boxes(args.gt)
    heights = load_template_heights(args.template_heights)
    template_len = int(np.median(heights)) if heights else int(round(staff_h))

    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    ink = (255 - gray).astype(np.float32)

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

        gt_local = (x1 - crop_x1, y1 - crop_y1, x2 - crop_x1, y2 - crop_y1)

        # scanning window in full image coordinates
        scan_left = max(0, cx - search_half)
        scan_right = min(base.shape[1] - 1, cx + search_half)
        # place template centered at GT y with template_len
        half_len = template_len // 2
        line_y1 = max(0, cy - half_len)
        line_y2 = min(base.shape[0], cy + half_len)

        scores = []
        for x in range(scan_left, scan_right + 1):
            col = ink[line_y1:line_y2, x]
            if col.size == 0:
                score = 0.0
            else:
                score = float(np.mean(col > 30))
            scores.append((score, x))

        scores.sort(reverse=True, key=lambda t: t[0])
        topk = scores[: args.topk]

        # draw template line (blue)
        template_x = cx - crop_x1
        temp_y1 = line_y1 - crop_y1
        temp_y2 = line_y2 - crop_y1
        cv2.line(crop, (template_x, temp_y1), (template_x, temp_y2), (255, 0, 0), 2)

        # draw GT box (red)
        draw_box(crop, gt_local, (0, 0, 255), 2)

        # draw top-5 probes (yellow) and top-1 (green)
        for rank, (_, x) in enumerate(topk):
            lx = x - crop_x1
            color = (0, 255, 0) if rank == 0 else (0, 255, 255)
            cv2.line(crop, (lx, temp_y1), (lx, temp_y2), color, 2)

        legend = [
            "Red=GT, Green=top-1 probe, Yellow=top-5 probes, Blue=template",
            f"base: {args.base}",
            f"gt:   {args.gt}",
            f"template_heights: {args.template_heights}",
        ]
        put_text_block(crop, legend, origin=(8, 18))

        out_path = args.output_dir / f"{args.page_id}_fn_{idx:03d}_scan_overlay.png"
        cv2.imwrite(str(out_path), crop)

        summary.append(
            {
                "fn_id": idx,
                "overlay": str(out_path),
                "top_scores": topk,
                "template_len": template_len,
            }
        )

    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
