#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

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


def extract_staff_bands(mask: np.ndarray, min_height: int = 10) -> List[Box]:
    mask_bin = (mask > 0).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15))
    merged = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, kernel)
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
    bands = []
    for i in range(1, num_labels):
        x, y, w, h, _ = stats[i]
        if h < min_height:
            continue
        bands.append((x, y, x + w, y + h))
    bands.sort(key=lambda b: b[1])
    return bands


def find_staff_lines(gray: np.ndarray, band: Box, max_lines: int = 5) -> List[int]:
    x1, y1, x2, y2 = band
    crop = gray[y1:y2, x1:x2]
    if crop.size == 0:
        return []
    ink = 255 - crop
    row_sum = ink.sum(axis=1)
    rows = list(range(len(row_sum)))
    # select top peaks with min separation
    min_sep = max(2, int(round((y2 - y1) / 6)))
    candidates = sorted(rows, key=lambda r: row_sum[r], reverse=True)
    picked = []
    for r in candidates:
        if all(abs(r - p) >= min_sep for p in picked):
            picked.append(r)
        if len(picked) >= max_lines:
            break
    picked.sort()
    return [y1 + r for r in picked]


def longest_run(vec: np.ndarray) -> int:
    max_run = 0
    run = 0
    for v in vec:
        if v:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return max_run


def compute_scores(gray: np.ndarray, band: Box, staff_lines: List[int], step: int) -> List[Dict]:
    x1, y1, x2, y2 = band
    crop = gray[y1:y2, x1:x2]
    if crop.size == 0:
        return []
    ink = (255 - crop)
    _, bin_img = cv2.threshold(ink, 160, 255, cv2.THRESH_BINARY)
    h, w = bin_img.shape
    results = []
    line_rows = [r - y1 for r in staff_lines if y1 <= r < y2]
    for xi in range(0, w, step):
        col = bin_img[:, xi] > 0
        ink_ratio = float(np.count_nonzero(col)) / float(h)
        cont = float(longest_run(col)) / float(h)
        crossings = 0
        crossing_rows = []
        for r in line_rows:
            if col[r]:
                crossings += 1
                crossing_rows.append(r)
        if len(crossing_rows) >= 2:
            diffs = np.diff(crossing_rows)
            crossing_uniformity = float(np.var(diffs)) if len(diffs) > 0 else 0.0
        else:
            crossing_uniformity = 999.0
        results.append(
            {
                "x": int(x1 + xi),
                "ink_ratio": ink_ratio,
                "continuity": cont,
                "staff_line_crossings": crossings,
                "crossing_uniformity": crossing_uniformity,
            }
        )
    return results


def rank_probes(probes: List[Dict], topk: int) -> List[Dict]:
    # prioritize staff crossings, then continuity, then ink_ratio, then uniformity
    probes_sorted = sorted(
        probes,
        key=lambda p: (
            p["staff_line_crossings"],
            p["continuity"],
            p["ink_ratio"],
            -p["crossing_uniformity"],
        ),
        reverse=True,
    )
    return probes_sorted[:topk]


def draw_boxes(img: np.ndarray, boxes: List[Box], color: Tuple[int, int, int], thickness: int = 2) -> None:
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)


def put_text_block(img: np.ndarray, lines: List[str], origin=(8, 18)) -> None:
    x, y = origin
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA)
        y += 16


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--staff-mask", type=Path, required=True)
    ap.add_argument("--gt", type=Path, required=False)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--page-id", type=str, required=True)
    ap.add_argument("--probe-step", type=int, default=2)
    ap.add_argument("--topk", type=int, default=10)
    args = ap.parse_args()

    base = cv2.imread(str(args.base), cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")
    staff = cv2.imread(str(args.staff_mask), cv2.IMREAD_GRAYSCALE)
    if staff is None:
        raise SystemExit(f"Failed to load staff mask: {args.staff_mask}")

    if staff.shape[:2] != base.shape[:2]:
        staff = cv2.resize(staff, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_NEAREST)

    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    bands = extract_staff_bands(staff)
    gt_boxes = load_gt_boxes(args.gt) if args.gt else []

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    band_results = []
    overlay = base.copy()
    # draw all probes in yellow and staff bounds in blue
    for band_idx, band in enumerate(bands):
        x1, y1, x2, y2 = band
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 0, 0), 1)
        staff_lines = find_staff_lines(gray, band)
        probes = compute_scores(gray, band, staff_lines, args.probe_step)
        topk = rank_probes(probes, args.topk)
        for p in probes:
            x = p["x"]
            cv2.line(overlay, (x, y1), (x, y2), (0, 255, 255), 1)
        band_results.append(
            {
                "band_index": int(band_idx),
                "band_box": [int(v) for v in band],
                "staff_lines": [int(v) for v in staff_lines],
                "topk": [
                    {
                        "x": int(p["x"]),
                        "ink_ratio": float(p["ink_ratio"]),
                        "continuity": float(p["continuity"]),
                        "staff_line_crossings": int(p["staff_line_crossings"]),
                        "crossing_uniformity": float(p["crossing_uniformity"]),
                    }
                    for p in topk
                ],
            }
        )

    if gt_boxes:
        draw_boxes(overlay, gt_boxes, (0, 0, 255), 2)

    legend = [
        "Red=GT, Yellow=all probes, Blue=staff bounds",
        f"base: {args.base}",
        f"staff: {args.staff_mask}",
        f"gt: {args.gt if args.gt else 'none'}",
    ]
    put_text_block(overlay, legend, origin=(8, 18))
    overlay_path = out_dir / f"{args.page_id}_probe_overlay.png"
    cv2.imwrite(str(overlay_path), overlay)

    (out_dir / f"{args.page_id}_probe_scores.json").write_text(json.dumps(band_results, indent=2))


if __name__ == "__main__":
    main()
