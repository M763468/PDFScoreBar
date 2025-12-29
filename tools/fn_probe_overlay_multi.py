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


def draw_box(img: np.ndarray, box: Box, color: Tuple[int, int, int], thickness: int = 2) -> None:
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)


def put_text_block(img: np.ndarray, lines: List[str], origin=(8, 18)) -> None:
    x, y = origin
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA)
        y += 16


def load_probe_scores(root: Path, page_id: str) -> List[Dict]:
    entries = []
    for score_path in root.rglob(f"{page_id}_*_probe_scores.json"):
        variant = score_path.stem.replace(f"{page_id}_", "").replace("_probe_scores", "")
        data = json.loads(score_path.read_text())
        entries.append({"variant": variant, "path": score_path, "bands": data})
    return entries


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--staff-mask", type=Path, required=True)
    ap.add_argument("--probe-root", type=Path, required=True)
    ap.add_argument("--page-id", type=str, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--gt-window", type=int, default=3)
    ap.add_argument("--margin-factor", type=float, default=1.5)
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
    probe_sets = load_probe_scores(args.probe_root, args.page_id)

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

        all_candidates = []
        best_match = None

        for probe_set in probe_sets:
            variant = probe_set["variant"]
            for band_entry in probe_set["bands"]:
                bx1, by1, bx2, by2 = band_entry["band_box"]
                overlap = max(0, min(y2, by2) - max(y1, by1))
                if overlap <= 0:
                    continue
                for p in band_entry["topk"]:
                    cand = {
                        "variant": variant,
                        "x": int(p["x"]),
                        "y1": int(p["y1"]),
                        "y2": int(p["y2"]),
                        "length": int(p["length"]),
                        "score": float(p["score"]),
                    }
                    all_candidates.append(cand)
                    if abs(cand["x"] - cx) <= args.gt_window:
                        if best_match is None or cand["score"] > best_match["score"]:
                            best_match = cand

        # draw staff bounds (blue)
        draw_box(crop, (0, 0, crop.shape[1] - 1, crop.shape[0] - 1), (255, 0, 0), 1)
        # draw GT (red)
        draw_box(crop, (x1 - crop_x1, y1 - crop_y1, x2 - crop_x1, y2 - crop_y1), (0, 0, 255), 2)

        # draw other probes (yellow)
        topk = sorted(all_candidates, key=lambda c: c["score"], reverse=True)[: args.topk]
        for c in topk:
            lx = c["x"] - crop_x1
            y1c = c["y1"] - crop_y1
            y2c = c["y2"] - crop_y1
            cv2.line(crop, (lx, y1c), (lx, y2c), (0, 255, 255), 2)

        # draw best match (green)
        if best_match is not None:
            lx = best_match["x"] - crop_x1
            y1c = best_match["y1"] - crop_y1
            y2c = best_match["y2"] - crop_y1
            cv2.line(crop, (lx, y1c), (lx, y2c), (0, 255, 0), 3)

        legend = [
            "Red=GT, Green=best probe near GT, Yellow=top probes, Blue=staff bounds",
            f"base: {args.base}",
            f"gt: {args.gt}",
            f"probe_root: {args.probe_root}",
        ]
        put_text_block(crop, legend, origin=(8, 18))

        out_path = args.output_dir / f"{args.page_id}_fn_{idx:03d}_probe_multi_overlay.png"
        cv2.imwrite(str(out_path), crop)

        summary.append(
            {
                "fn_id": idx,
                "overlay": str(out_path),
                "probe_near_gt": best_match is not None,
                "best_match": best_match,
                "topk_count": len(topk),
            }
        )

    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
