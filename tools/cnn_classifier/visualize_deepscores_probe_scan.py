#!/usr/bin/env python3
import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from tools.cnn_classifier.build_cnn_dataset import (
    barline_iou,
    find_components,
    load_palette_index,
)
from tools.run_gt_rebuild_hybrid_eval import detect_probe_scan


def collect_tp_boxes(seg_np: np.ndarray, palette_index: int, min_area: int, min_height: int):
    mask = (seg_np == palette_index).astype(np.uint8) * 255
    comps = find_components(mask)
    tp_boxes = []
    for comp in comps:
        if comp["area"] < min_area:
            continue
        if comp["h"] < min_height:
            continue
        x1, y1, x2, y2 = comp["bbox"]
        tp_boxes.append((int(x1), int(y1), int(x2), int(y2)))
    return tp_boxes


def build_staff_bands_from_palette(
    seg_np: np.ndarray,
    staff_palette_index: int,
    band_gap_mult: float,
    pad_mult: float,
):
    mask = (seg_np == staff_palette_index).astype(np.uint8)
    row_hits = np.where(mask.sum(axis=1) > 0)[0]
    if row_hits.size == 0:
        return []

    # Group contiguous rows into staff lines.
    lines = []
    start = int(row_hits[0])
    prev = int(row_hits[0])
    for y in row_hits[1:]:
        if int(y) - prev <= 1:
            prev = int(y)
            continue
        lines.append((start, prev))
        start = int(y)
        prev = int(y)
    lines.append((start, prev))

    centers = [(y1 + y2) / 2.0 for y1, y2 in lines]
    if len(centers) < 2:
        return []

    diffs = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    median_gap = float(np.median(diffs)) if diffs else 0.0
    if median_gap <= 0:
        return []

    max_gap = median_gap * band_gap_mult
    bands = []
    group = [centers[0]]
    for c in centers[1:]:
        if c - group[-1] <= max_gap:
            group.append(c)
            continue
        bands.append(group)
        group = [c]
    bands.append(group)

    staff_bands = []
    for grp in bands:
        if len(grp) < 3:
            continue
        local_diffs = [grp[i + 1] - grp[i] for i in range(len(grp) - 1)]
        staff_space = float(np.median(local_diffs)) if local_diffs else median_gap
        if staff_space <= 0:
            staff_space = median_gap
        pad = staff_space * pad_mult
        top = int(round(min(grp) - pad))
        bottom = int(round(max(grp) + pad))
        staff_bands.append((top, bottom))
    return staff_bands


def expand_boxes_to_staff_bands(boxes, staff_bands, img_h):
    if not staff_bands:
        return list(boxes)

    expanded = []
    band_centers = [(y1 + y2) / 2.0 for y1, y2 in staff_bands]
    for x1, y1, x2, y2 in boxes:
        cy = (y1 + y2) / 2.0
        best_idx = None
        for idx, (by1, by2) in enumerate(staff_bands):
            if by1 <= cy <= by2:
                best_idx = idx
                break
        if best_idx is None:
            dists = [abs(cy - c) for c in band_centers]
            best_idx = int(np.argmin(dists))
        by1, by2 = staff_bands[best_idx]
        by1 = max(0, by1)
        by2 = min(img_h - 1, by2)
        expanded.append((x1, by1, x2, by2))
    return expanded


def load_staff_boxes_by_filename(ds_root: Path):
    staff_map = {}
    for split_name in ("deepscores_train.json", "deepscores_test.json"):
        json_path = ds_root / split_name
        if not json_path.exists():
            continue
        with json_path.open("r") as f:
            data = json.load(f)
        staff_ids = {
            cid for cid, c in data.get("categories", {}).items() if c.get("name") == "staff"
        }
        if not staff_ids:
            continue
        images = {str(img["id"]): img for img in data.get("images", [])}
        annotations = data.get("annotations", {})
        for img_id, img in images.items():
            ann_ids = img.get("ann_ids", [])
            staff_boxes = []
            for ann_id in ann_ids:
                ann = annotations.get(str(ann_id))
                if not ann:
                    continue
                cat_ids = ann.get("cat_id", [])
                if any(cid in staff_ids for cid in cat_ids):
                    x1, y1, x2, y2 = ann["a_bbox"]
                    staff_boxes.append(
                        (int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)))
                    )
            if staff_boxes:
                staff_map[img["filename"]] = staff_boxes
    return staff_map


def expand_boxes_to_staff_boxes(boxes, staff_boxes, img_h, force: bool):
    if not staff_boxes:
        return list(boxes)
    staff_centers = [(y1 + y2) / 2.0 for _, y1, _, y2 in staff_boxes]
    expanded = []
    for x1, y1, x2, y2 in boxes:
        cy = (y1 + y2) / 2.0
        best_idx = None
        for idx, (_, sy1, _, sy2) in enumerate(staff_boxes):
            if sy1 <= cy <= sy2:
                best_idx = idx
                break
        if best_idx is None:
            dists = [abs(cy - c) for c in staff_centers]
            best_idx = int(np.argmin(dists))
        _, sy1, _, sy2 = staff_boxes[best_idx]
        sy1 = max(0, sy1)
        sy2 = min(img_h - 1, sy2)
        if force:
            expanded.append((x1, sy1, x2, sy2))
        else:
            ny1 = min(y1, sy1)
            ny2 = max(y2, sy2)
            expanded.append((x1, ny1, x2, ny2))
    return expanded


def collect_fp_boxes(candidates, tp_boxes, iou_threshold: float):
    fp_boxes = []
    for cand in candidates:
        is_match = False
        for tp in tp_boxes:
            if barline_iou(tp, cand) >= iou_threshold:
                is_match = True
                break
        if not is_match:
            fp_boxes.append(cand)
    return fp_boxes


def count_short_boxes(boxes, staff_boxes, ratio: float):
    if not staff_boxes:
        return 0
    staff_centers = [(y1 + y2) / 2.0 for _, y1, _, y2 in staff_boxes]
    staff_heights = [max(1, y2 - y1 + 1) for _, y1, _, y2 in staff_boxes]
    short_count = 0
    for x1, y1, x2, y2 in boxes:
        cy = (y1 + y2) / 2.0
        dists = [abs(cy - c) for c in staff_centers]
        band_idx = int(np.argmin(dists))
        band_h = staff_heights[band_idx]
        if (y2 - y1 + 1) < band_h * ratio:
            short_count += 1
    return short_count


def draw_overlay(base_img, tp_boxes, fp_boxes, short_tp_boxes=None, staff_boxes=None):
    vis = base_img.copy()
    short_tp = set(short_tp_boxes or [])
    for x1, y1, x2, y2 in staff_boxes or []:
        cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 0, 0), 1)
    for x1, y1, x2, y2 in tp_boxes:
        color = (255, 0, 255) if (x1, y1, x2, y2) in short_tp else (0, 200, 0)
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
    for x1, y1, x2, y2 in fp_boxes:
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 0, 255), 2)
    label = f"TP={len(tp_boxes)} FP={len(fp_boxes)}"
    cv2.putText(
        vis,
        label,
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        vis,
        label,
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return vis


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deepscores-root",
        default="/mnt/d/datasets/DeepScoresV2/ds2_dense",
        help="DeepScores V2 Dense root.",
    )
    parser.add_argument(
        "--output-dir",
        default="logs/cnn_classifier/deepscores_probe_scan_vis",
    )
    parser.add_argument("--sample-count", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--palette-index", type=int, default=3)
    parser.add_argument("--min-area", type=int, default=10)
    parser.add_argument("--min-height", type=int, default=5)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--staff-palette-index", type=int, default=165)
    parser.add_argument("--staff-band-gap-mult", type=float, default=2.5)
    parser.add_argument("--staff-band-pad-mult", type=float, default=0.5)
    parser.add_argument("--short-tp-ratio", type=float, default=0.6)
    parser.add_argument(
        "--staff-source",
        choices=["annotations", "segmentation", "none"],
        default="annotations",
        help="Staff band source for vertical expansion.",
    )
    parser.add_argument(
        "--draw-staff-boxes",
        action="store_true",
        help="Overlay staff bounding boxes in blue when available.",
    )
    parser.add_argument(
        "--force-staff-box-height",
        action="store_true",
        help="Force TP/FP boxes to staff bbox height when using annotation staff source.",
    )
    parser.add_argument(
        "--log-short-stats",
        action="store_true",
        help="Log short-box counts before/after staff expansion.",
    )
    parser.add_argument(
        "--no-expand-to-staff-bands",
        action="store_true",
        help="Keep TP/FP boxes as-is without staff-band expansion.",
    )

    parser.add_argument("--probe-width", type=int, default=4)
    parser.add_argument("--ink-threshold", type=int, default=200)
    parser.add_argument("--min-ratio", type=float, default=0.50)
    parser.add_argument("--scan-x-peak-ratio-min", type=float, default=0.0)
    parser.add_argument("--scan-rightmost-min-ratio", type=float, default=0.10)
    parser.add_argument("--max-per-band", type=int, default=0)
    args = parser.parse_args()

    ds_root = Path(args.deepscores_root)
    seg_root = ds_root / "segmentation"
    img_root = ds_root / "images"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    seg_files = sorted(seg_root.glob("*_seg.png"))
    if not seg_files:
        print(f"No segmentation files found under {seg_root}")
        return

    staff_boxes_by_name = {}
    if args.staff_source == "annotations":
        staff_boxes_by_name = load_staff_boxes_by_filename(ds_root)

    rng = random.Random(args.seed)
    sample_count = min(args.sample_count, len(seg_files))
    samples = rng.sample(seg_files, sample_count)

    for seg_path in samples:
        image_name = seg_path.name.replace("_seg.png", ".png")
        image_path = img_root / image_name
        if not image_path.exists():
            print(f"Image not found: {image_path}")
            continue

        img = cv2.imread(str(image_path))
        if img is None:
            print(f"Failed to load image: {image_path}")
            continue

        seg_np = load_palette_index(seg_path)
        tp_boxes = collect_tp_boxes(
            seg_np,
            palette_index=args.palette_index,
            min_area=args.min_area,
            min_height=args.min_height,
        )
        if not tp_boxes:
            print(f"Skipping {image_name}: no TP boxes after filters.")
            continue

        staff_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        candidates = detect_probe_scan(
            base_img=img,
            staff_mask=staff_mask,
            existing_boxes=tp_boxes,
            band_source="row_stats",
            scan_x_peak_rescue=True,
            scan_rightmost_rescue=True,
            divisi_rescue=True,
            scan_x_peak_rescue_mode="topbottom",
            probe_width=args.probe_width,
            ink_threshold=args.ink_threshold,
            min_ratio=args.min_ratio,
            scan_center_on_peak=True,
            scan_x_peak_ratio_min=args.scan_x_peak_ratio_min,
            scan_rightmost_min_ratio=args.scan_rightmost_min_ratio,
            max_per_band=args.max_per_band,
        )

        staff_bands = []
        staff_boxes = []
        if args.staff_source == "annotations":
            staff_boxes = staff_boxes_by_name.get(image_name, [])
        elif args.staff_source == "segmentation":
            staff_bands = build_staff_bands_from_palette(
                seg_np,
                staff_palette_index=args.staff_palette_index,
                band_gap_mult=args.staff_band_gap_mult,
                pad_mult=args.staff_band_pad_mult,
            )

        short_tp_boxes = []
        if staff_boxes:
            staff_centers = [(y1 + y2) / 2.0 for _, y1, _, y2 in staff_boxes]
            staff_heights = [max(1, y2 - y1 + 1) for _, y1, _, y2 in staff_boxes]
            for box in tp_boxes:
                _, y1, _, y2 = box
                cy = (y1 + y2) / 2.0
                dists = [abs(cy - c) for c in staff_centers]
                band_idx = int(np.argmin(dists))
                band_h = staff_heights[band_idx]
                if (y2 - y1 + 1) < band_h * args.short_tp_ratio:
                    short_tp_boxes.append(box)
        elif staff_bands:
            band_centers = [(y1 + y2) / 2.0 for y1, y2 in staff_bands]
            band_heights = [max(1, y2 - y1 + 1) for y1, y2 in staff_bands]
            for box in tp_boxes:
                _, y1, _, y2 = box
                cy = (y1 + y2) / 2.0
                dists = [abs(cy - c) for c in band_centers]
                band_idx = int(np.argmin(dists))
                band_h = band_heights[band_idx]
                if (y2 - y1 + 1) < band_h * args.short_tp_ratio:
                    short_tp_boxes.append(box)

        if args.log_short_stats and staff_boxes:
            tp_short = count_short_boxes(tp_boxes, staff_boxes, args.short_tp_ratio)
            cand_short = count_short_boxes(candidates, staff_boxes, args.short_tp_ratio)
            print(
                f"{image_name}: short(TP)={tp_short}/{len(tp_boxes)} "
                f"short(Cand)={cand_short}/{len(candidates)} (ratio<{args.short_tp_ratio})"
            )

        if not args.no_expand_to_staff_bands:
            if staff_boxes:
                tp_boxes = expand_boxes_to_staff_boxes(
                    tp_boxes,
                    staff_boxes,
                    img.shape[0],
                    force=args.force_staff_box_height,
                )
                candidates = expand_boxes_to_staff_boxes(
                    candidates,
                    staff_boxes,
                    img.shape[0],
                    force=args.force_staff_box_height,
                )
            elif staff_bands:
                tp_boxes = expand_boxes_to_staff_bands(
                    tp_boxes,
                    staff_bands,
                    img.shape[0],
                )
                candidates = expand_boxes_to_staff_bands(
                    candidates,
                    staff_bands,
                    img.shape[0],
                )

        fp_boxes = collect_fp_boxes(
            candidates,
            tp_boxes,
            iou_threshold=args.iou_threshold,
        )

        if args.log_short_stats and staff_boxes:
            tp_short = count_short_boxes(tp_boxes, staff_boxes, args.short_tp_ratio)
            cand_short = count_short_boxes(candidates, staff_boxes, args.short_tp_ratio)
            fp_short = count_short_boxes(fp_boxes, staff_boxes, args.short_tp_ratio)
            print(
                f"{image_name}: short(TP)={tp_short}/{len(tp_boxes)} "
                f"short(Cand)={cand_short}/{len(candidates)} "
                f"short(FP)={fp_short}/{len(fp_boxes)} after_expand={not args.no_expand_to_staff_bands}"
            )

        overlay_staff = staff_boxes if args.draw_staff_boxes else None
        vis = draw_overlay(
            img,
            tp_boxes,
            fp_boxes,
            short_tp_boxes=short_tp_boxes,
            staff_boxes=overlay_staff,
        )
        save_path = output_dir / f"vis_probe_{image_name}"
        cv2.imwrite(str(save_path), vis)
        print(f"Saved {save_path} (TP={len(tp_boxes)} FP={len(fp_boxes)})")


if __name__ == "__main__":
    main()
