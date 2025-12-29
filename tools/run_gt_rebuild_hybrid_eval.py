#!/usr/bin/env python3
"""
Re-evaluate hybrid (homr + omr-dln union) with row + geom notehead filter
against rebuilt GT. Produces metrics + overlays with TP/FP/FN.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import cv2
import numpy as np
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import greedy_barline_match

Box = Tuple[int, int, int, int]
Color = Tuple[int, int, int]

TP_COLOR: Color = (0, 255, 0)
FP_COLOR: Color = (0, 0, 255)
FN_COLOR: Color = (255, 0, 255)


@dataclass
class PageSpec:
    name: str
    image: Path
    gt: Path
    notehead_mask: Path
    staff_mask: Path
    staff_mask_alt: Path
    union_preds: Path


def load_preds(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    raw = data["predictions"] if isinstance(data, dict) and "predictions" in data else data
    preds: List[Box] = []
    for item in raw:
        if isinstance(item, list):
            preds.append(tuple(map(int, item)))
        elif isinstance(item, dict):
            bbox = item.get("orig_bbox", item.get("bbox", item.get("pred_bbox")))
            if bbox:
                preds.append(tuple(map(int, bbox)))
    return preds


def load_gt(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, list) and data and "barline_location" in data[0]:
        return [tuple(map(int, x["barline_location"])) for x in data]
    return [tuple(map(int, x)) for x in data]


def cluster_by_y_distance(y_centers: np.ndarray, max_distance: float, min_cluster_size: int):
    sorted_indices = np.argsort(y_centers)
    sorted_y = y_centers[sorted_indices]
    clusters: List[List[int]] = []
    current_cluster = [int(sorted_indices[0])]
    for i in range(1, len(sorted_y)):
        if sorted_y[i] - sorted_y[i - 1] <= max_distance:
            current_cluster.append(int(sorted_indices[i]))
        else:
            clusters.append(current_cluster)
            current_cluster = [int(sorted_indices[i])]
    clusters.append(current_cluster)

    valid_clusters: Dict[int, List[int]] = {}
    noise: List[int] = []
    cluster_id = 0
    for cluster in clusters:
        if len(cluster) >= min_cluster_size:
            valid_clusters[cluster_id] = cluster
            cluster_id += 1
        else:
            noise.extend(cluster)
    return valid_clusters, noise


def estimate_staff_space(rows: Dict[int, List[int]], preds_list: Sequence[Box]) -> float:
    if len(rows) < 2:
        return 20.0
    row_medians = []
    for row_id in sorted(rows.keys()):
        indices = rows[row_id]
        y_centers = [(preds_list[i][1] + preds_list[i][3]) / 2 for i in indices]
        row_medians.append(float(np.median(y_centers)))
    gaps = [row_medians[i + 1] - row_medians[i] for i in range(len(row_medians) - 1)]
    median_gap = float(np.median(gaps)) if gaps else 100.0
    return median_gap / 5.0


def row_filter(
    preds: Sequence[Box],
    cluster_max_dist: float,
    min_row_count: int,
    tol_top: float,
    tol_bottom: float,
) -> List[Box]:
    y_centers = np.array([(box[1] + box[3]) / 2 for box in preds])
    rows, _ = cluster_by_y_distance(y_centers, cluster_max_dist, min_row_count)
    accepted_indices = set()
    for _, indices in rows.items():
        if len(indices) < min_row_count:
            continue
        tops = [preds[i][1] for i in indices]
        bottoms = [preds[i][3] for i in indices]
        ref_top = float(np.median(tops))
        ref_bottom = float(np.median(bottoms))
        for i in indices:
            x1, y1, x2, y2 = map(int, preds[i])
            if abs(y1 - ref_top) <= tol_top and abs(y2 - ref_bottom) <= tol_bottom:
                accepted_indices.add(i)
    return [preds[i] for i in sorted(accepted_indices)]


def load_notehead_mask(path: Path, target_hw: Tuple[int, int]) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Failed to load notehead mask: {path}")
    _, bin_mask = cv2.threshold(img, 1, 255, cv2.THRESH_BINARY)
    if bin_mask.shape[:2] != target_hw:
        h, w = target_hw
        bin_mask = cv2.resize(bin_mask, (w, h), interpolation=cv2.INTER_NEAREST)
    return bin_mask


def load_staff_mask(path: Path, target_hw: Tuple[int, int]) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Failed to load staff mask: {path}")
    _, bin_mask = cv2.threshold(img, 1, 255, cv2.THRESH_BINARY)
    if bin_mask.shape[:2] != target_hw:
        h, w = target_hw
        bin_mask = cv2.resize(bin_mask, (w, h), interpolation=cv2.INTER_NEAREST)
    return bin_mask


def staff_bands_from_mask(mask: np.ndarray) -> List[Tuple[int, int]]:
    rows = np.where(mask.sum(axis=1) > 0)[0]
    if rows.size == 0:
        return []
    bands: List[Tuple[int, int]] = []
    start = rows[0]
    prev = rows[0]
    for y in rows[1:]:
        if y == prev + 1:
            prev = y
            continue
        bands.append((int(start), int(prev)))
        start = y
        prev = y
    bands.append((int(start), int(prev)))
    return bands


def detect_end_barlines(
    base_img: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: Sequence[Box],
    *,
    search_width: int = 40,
    min_height_ratio: float = 0.6,
    right_clear_width: int = 10,
    right_clear_ratio: float = 0.08,
    x_merge_tol: int = 4,
    debug_path: Path | None = None,
) -> List[Box]:
    gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = (ink > 0).astype(np.uint8)

    h, w = ink.shape[:2]
    bands = staff_bands_from_mask(staff_mask)
    if not bands:
        return []

    def has_existing(x_center: float, y1: int, y2: int) -> bool:
        for bx1, by1, bx2, by2 in existing_boxes:
            cy = (by1 + by2) / 2.0
            if cy < y1 or cy > y2:
                continue
            cx = (bx1 + bx2) / 2.0
            if abs(cx - x_center) <= x_merge_tol:
                return True
        return False

    candidates: List[Box] = []
    debug_records = []
    x_start = max(0, w - search_width)
    for y1, y2 in bands:
        band_h = max(1, y2 - y1 + 1)
        band_ink = ink[y1 : y2 + 1, x_start:w]
        col_sums = band_ink.sum(axis=0)
        min_ink = int(round(band_h * min_height_ratio))
        valid_cols = np.where(col_sums >= min_ink)[0]
        if valid_cols.size == 0:
            debug_records.append(
                {
                    "band": [y1, y2],
                    "status": "no_valid_cols",
                    "min_ink": min_ink,
                }
            )
            continue
        col = int(valid_cols[-1]) + x_start
        x_center = float(col)
        if has_existing(x_center, y1, y2):
            debug_records.append(
                {
                    "band": [y1, y2],
                    "status": "existing",
                    "col": col,
                    "min_ink": min_ink,
                }
            )
            continue
        right_x1 = min(w, col + 2)
        right_x2 = min(w, col + 2 + right_clear_width)
        if right_x1 < right_x2:
            right_window = ink[y1 : y2 + 1, right_x1:right_x2]
            right_ratio = float(right_window.mean()) if right_window.size else 0.0
            if right_ratio > right_clear_ratio:
                debug_records.append(
                    {
                        "band": [y1, y2],
                        "status": "right_blocked",
                        "col": col,
                        "right_ratio": right_ratio,
                    }
                )
                continue
        debug_records.append(
            {
                "band": [y1, y2],
                "status": "accepted",
                "col": col,
            }
        )
        candidates.append((max(0, col - 1), y1, min(w - 1, col + 1), y2))

    if debug_path is not None:
        overlay = base_img.copy()
        mask_overlay = overlay.copy()
        # Staff bands (cyan)
        for y1, y2 in bands:
            cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
        overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
        # Right search window (yellow)
        cv2.rectangle(overlay, (x_start, 0), (w - 1, h - 1), (0, 255, 255), 1)
        # Candidate columns
        for rec in debug_records:
            col = rec.get("col")
            if col is None:
                continue
            color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
            cv2.line(overlay, (col, 0), (col, h - 1), color, 1)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_path), overlay)
        debug_json = debug_path.with_suffix(".json")
        debug_json.write_text(
            json.dumps(
                {
                    "params": {
                        "search_width": search_width,
                        "min_height_ratio": min_height_ratio,
                        "right_clear_width": right_clear_width,
                        "right_clear_ratio": right_clear_ratio,
                        "x_merge_tol": x_merge_tol,
                    },
                    "bands": bands,
                    "records": debug_records,
                },
                indent=2,
            )
        )
    return candidates


def geom_notehead_ratio_filter(
    preds: Sequence[Box],
    notehead_mask: np.ndarray,
    staff_space_px: float,
    threshold: float,
    endpoint_x_scale: float,
    endpoint_y_scale: float,
):
    h, w = notehead_mask.shape[:2]
    kept: List[Box] = []
    rejected: List[Dict[str, object]] = []
    scores: List[Dict[str, object]] = []

    rx = max(1, int(round(staff_space_px * endpoint_x_scale)))
    ry = max(2, int(round(staff_space_px * endpoint_y_scale)))

    for i, box in enumerate(preds):
        x1, y1, x2, y2 = map(int, box)
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w - 1, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h - 1, y2))

        xm = (x1 + x2) // 2

        tx1, tx2 = max(0, xm - rx), min(w, xm + rx + 1)
        ty1, ty2 = max(0, y1 - ry), min(h, y1 + ry + 1)
        bx1, bx2 = max(0, xm - rx), min(w, xm + rx + 1)
        by1, by2 = max(0, y2 - ry), min(h, y2 + ry + 1)

        top_region = notehead_mask[ty1:ty2, tx1:tx2]
        bot_region = notehead_mask[by1:by2, bx1:bx2]

        notehead_pixels_top = int(np.count_nonzero(top_region))
        notehead_pixels_bottom = int(np.count_nonzero(bot_region))
        total_area = int(top_region.size + bot_region.size)
        total_notehead = notehead_pixels_top + notehead_pixels_bottom
        overlap_ratio = 0.0 if total_area == 0 else total_notehead / total_area

        scores.append(
            {
                "index": i,
                "bbox": [x1, y1, x2, y2],
                "endpoint_overlap_ratio": float(overlap_ratio),
                "endpoint_radius_px": {"x": int(rx), "y": int(ry)},
            }
        )

        if overlap_ratio > threshold:
            rejected.append(
                {
                    "index": i,
                    "bbox": [x1, y1, x2, y2],
                    "reason": "endpoint_ratio_overlap",
                    "overlap_ratio": float(overlap_ratio),
                    "threshold": threshold,
                }
            )
            continue
        kept.append((x1, y1, x2, y2))

    debug = {
        "config": {
            "mode": "endpoint_ratio_overlap",
            "threshold": threshold,
            "endpoint_x_radius_scale": endpoint_x_scale,
            "endpoint_y_radius_scale": endpoint_y_scale,
            "endpoint_radius_px": {"x": int(rx), "y": int(ry)},
        },
        "scores": scores,
        "rejected": rejected,
    }
    return kept, debug


def draw_boxes(base: np.ndarray, boxes: Sequence[Box], color: Tuple[int, int, int], thickness: int, label: str):
    for idx, (x1, y1, x2, y2) in enumerate(boxes):
        cv2.rectangle(base, (x1, y1), (x2, y2), color, thickness)
        cv2.putText(
            base,
            f"{label}{idx}",
            (x1, max(12, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )


def save_crops(base: np.ndarray, boxes: Sequence[Box], out_dir: Path, prefix: str, pad: int = 12) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    h, w = base.shape[:2]
    for idx, (x1, y1, x2, y2) in enumerate(boxes):
        cx1 = max(0, x1 - pad)
        cy1 = max(0, y1 - pad)
        cx2 = min(w, x2 + pad)
        cy2 = min(h, y2 + pad)
        crop = base[cy1:cy2, cx1:cx2]
        out_path = out_dir / f"{prefix}{idx}.png"
        cv2.imwrite(str(out_path), crop)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--union-root", type=Path, required=True)
    parser.add_argument("--endpoint-ratio-threshold", type=float, default=0.04)
    parser.add_argument("--endpoint-x-scale", type=float, default=0.12)
    parser.add_argument("--endpoint-y-scale", type=float, default=0.8)
    parser.add_argument("--cluster-max-dist", type=float, default=25.0)
    parser.add_argument("--min-row-count", type=int, default=3)
    parser.add_argument("--tol-top-px", type=float, default=5.0)
    parser.add_argument("--tol-bottom-px", type=float, default=5.0)
    parser.add_argument("--enable-end-barline-recovery", action="store_true")
    parser.add_argument("--endbar-search-width", type=int, default=40)
    parser.add_argument("--endbar-min-height-ratio", type=float, default=0.6)
    parser.add_argument("--endbar-right-clear-width", type=int, default=10)
    parser.add_argument("--endbar-right-clear-ratio", type=float, default=0.08)
    parser.add_argument("--endbar-staff-mask-mode", choices=["staff", "staffs"], default="staff")
    parser.add_argument("--endbar-debug", action="store_true")
    args = parser.parse_args()

    pages = [
        PageSpec(
            name="page_001",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_001_boxes_sorted.json",
            notehead_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_6_notehead.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_3_staff.png",
            staff_mask_alt=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001_debug_15_staffs.png",
            union_preds=args.union_root / "page_001_hybrid_preds.json",
        ),
        PageSpec(
            name="page_004",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_004_boxes_sorted.json",
            notehead_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_6_notehead.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_3_staff.png",
            staff_mask_alt=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_15_staffs.png",
            union_preds=args.union_root / "page_004_hybrid_preds.json",
        ),
        PageSpec(
            name="page_10",
            image=REPO_ROOT / "data/training/images/page_10.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_10_boxes_sorted.json",
            notehead_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_6_notehead.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_3_staff.png",
            staff_mask_alt=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_15_staffs.png",
            union_preds=args.union_root / "page_10_hybrid_preds.json",
        ),
        PageSpec(
            name="page_15",
            image=REPO_ROOT / "data/training/images/page_15.png",
            gt=REPO_ROOT / "logs/phase6_detector_miss/gt_rebuild/page_15_boxes_sorted.json",
            notehead_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_6_notehead.png",
            staff_mask=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_3_staff.png",
            staff_mask_alt=REPO_ROOT / "logs/homr_eval/20251229T_gt_rebuild_eval/page_15/page_15_debug_15_staffs.png",
            union_preds=args.union_root / "page_15_hybrid_preds.json",
        ),
    ]

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    overlays_root = output_root / "overlays"
    overlays_root.mkdir(parents=True, exist_ok=True)
    per_page_root = output_root / "per_page"
    per_page_root.mkdir(parents=True, exist_ok=True)

    summary_rows = []

    for page in pages:
        preds = load_preds(page.union_preds)
        base_img = cv2.imread(str(page.image))
        if base_img is None:
            raise FileNotFoundError(f"Failed to load image: {page.image}")
        notehead_mask = load_notehead_mask(page.notehead_mask, base_img.shape[:2])
        gt_boxes = load_gt(page.gt)

        y_centers = np.array([(box[1] + box[3]) / 2 for box in preds])
        rows, _ = cluster_by_y_distance(y_centers, args.cluster_max_dist, args.min_row_count)
        staff_space = estimate_staff_space(rows, preds)

        row_filtered = row_filter(
            preds,
            args.cluster_max_dist,
            args.min_row_count,
            args.tol_top_px,
            args.tol_bottom_px,
        )

        out_dir = per_page_root / page.name
        out_dir.mkdir(parents=True, exist_ok=True)

        geom_kept, geom_debug = geom_notehead_ratio_filter(
            row_filtered,
            notehead_mask,
            staff_space,
            args.endpoint_ratio_threshold,
            args.endpoint_x_scale,
            args.endpoint_y_scale,
        )
        added_end = []
        if args.enable_end_barline_recovery:
            staff_mask_path = page.staff_mask if args.endbar_staff_mask_mode == "staff" else page.staff_mask_alt
            staff_mask = load_staff_mask(staff_mask_path, base_img.shape[:2])
            debug_path = None
            if args.endbar_debug:
                debug_path = out_dir / "endbar_debug.png"
            added_end = detect_end_barlines(
                base_img,
                staff_mask,
                geom_kept,
                search_width=args.endbar_search_width,
                min_height_ratio=args.endbar_min_height_ratio,
                right_clear_width=args.endbar_right_clear_width,
                right_clear_ratio=args.endbar_right_clear_ratio,
                debug_path=debug_path,
            )
            if added_end:
                geom_kept = geom_kept + added_end

        match = greedy_barline_match(list(geom_kept), list(gt_boxes), iou_threshold=0.5)
        tp = len(match.matches)
        fp = len(match.false_positive_indices)
        fn = len(match.false_negative_indices)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        (out_dir / "row_filtered.json").write_text(json.dumps(row_filtered, indent=2))
        (out_dir / "geom_kept.json").write_text(json.dumps(geom_kept, indent=2))
        (out_dir / "geom_debug.json").write_text(json.dumps(geom_debug, indent=2))
        if added_end:
            (out_dir / "end_recovered.json").write_text(json.dumps(added_end, indent=2))
        (out_dir / "metrics.json").write_text(
            json.dumps(
                {
                    "TP": tp,
                    "FP": fp,
                    "FN": fn,
                    "Precision": precision,
                    "Recall": recall,
                    "F1": f1,
                },
                indent=2,
            )
        )

        overlay = base_img.copy()
        tp_indices = {m.pred_index for m in match.matches}
        tp_boxes = [geom_kept[i] for i in sorted(tp_indices)]
        fp_boxes = [geom_kept[i] for i in sorted(match.false_positive_indices)]
        fn_boxes = [gt_boxes[i] for i in sorted(match.false_negative_indices)]
        draw_boxes(overlay, tp_boxes, TP_COLOR, 2, "TP#")
        draw_boxes(overlay, fp_boxes, FP_COLOR, 2, "FP#")
        draw_boxes(overlay, fn_boxes, FN_COLOR, 2, "FN#")
        overlay_path = overlays_root / f"{page.name}_tp_fp_fn.png"
        cv2.imwrite(str(overlay_path), overlay)
        save_crops(base_img, fp_boxes, out_dir / "fp_crops", "FP_")

        summary_rows.append(
            {
                "page": page.name,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "kept": len(geom_kept),
                "row_kept": len(row_filtered),
            }
        )

    summary_table = [
        "| Page | TP | FP | FN | row_kept | geom_kept |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in summary_rows:
        summary_table.append(
            f"| {row['page']} | {row['tp']} | {row['fp']} | {row['fn']} | {row['row_kept']} | {row['kept']} |"
        )
    (output_root / "summary_table.md").write_text("\n".join(summary_table) + "\n")


if __name__ == "__main__":
    main()
