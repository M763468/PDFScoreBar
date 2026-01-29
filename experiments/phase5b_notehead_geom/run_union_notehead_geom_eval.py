#!/usr/bin/env python3
"""
Phase 5 evaluation: apply row filter + page-agnostic geom notehead ratio filter
to union(homr, omr-dln) detections. Outputs per-page metrics and overlays.

Defaults:
  - endpoint_ratio_threshold: 0.1
  - endpoint_radius_scale: 0.6
  - row filter: absolute tol_top=5, tol_bottom=5, cluster_max_dist=25, min_row_count=3
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import greedy_barline_match

Box = Tuple[int, int, int, int]


@dataclass
class PageSpec:
    name: str
    image: Path
    gt: Optional[Path]
    notehead_mask: Path


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


def geom_notehead_ratio_filter(
    preds: Sequence[Box],
    notehead_mask: np.ndarray,
    staff_space_px: float,
    threshold: float,
    endpoint_radius_scale: float,
    endpoint_x_radius_scale: Optional[float] = None,
    endpoint_y_radius_scale: Optional[float] = None,
):
    h, w = notehead_mask.shape[:2]
    kept: List[Box] = []
    rejected: List[Dict[str, object]] = []
    scores: List[Dict[str, object]] = []

    x_scale = endpoint_radius_scale if endpoint_x_radius_scale is None else endpoint_x_radius_scale
    y_scale = endpoint_radius_scale if endpoint_y_radius_scale is None else endpoint_y_radius_scale
    rx = max(1, int(round(staff_space_px * x_scale)))
    ry = max(2, int(round(staff_space_px * y_scale)))

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
                "notehead_pixels_top": notehead_pixels_top,
                "notehead_pixels_bottom": notehead_pixels_bottom,
                "area_top": int(top_region.size),
                "area_bottom": int(bot_region.size),
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
                    "endpoint_radius_px": {"x": int(rx), "y": int(ry)},
                }
            )
            continue
        kept.append((x1, y1, x2, y2))

    debug = {
        "config": {
            "mode": "endpoint_ratio_overlap",
            "threshold": threshold,
            "endpoint_radius_scale": endpoint_radius_scale,
            "endpoint_x_radius_scale": endpoint_x_radius_scale,
            "endpoint_y_radius_scale": endpoint_y_radius_scale,
            "endpoint_radius_px": {"x": int(rx), "y": int(ry)},
        },
        "scores": scores,
        "rejected": rejected,
    }
    return kept, debug


def evaluate(preds: Sequence[Box], gt: Sequence[Box]) -> Dict[str, float]:
    result = greedy_barline_match(list(preds), list(gt), iou_threshold=0.5)
    tp = len(result.matches)
    fp = len(result.false_positive_indices)
    fn = len(result.false_negative_indices)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"TP": tp, "FP": fp, "FN": fn, "Precision": precision, "Recall": recall, "F1": f1}


def draw_boxes(
    base: np.ndarray, boxes: Sequence[Box], color: Tuple[int, int, int], thickness: int
) -> None:
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(base, (x1, y1), (x2, y2), color, thickness)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--union-root", type=Path, required=True)
    parser.add_argument("--endpoint-ratio-threshold", type=float, default=0.1)
    parser.add_argument("--endpoint-radius-scale", type=float, default=0.6)
    parser.add_argument("--cluster-max-dist", type=float, default=25.0)
    parser.add_argument("--min-row-count", type=int, default=3)
    parser.add_argument("--tol-top-px", type=float, default=5.0)
    parser.add_argument("--tol-bottom-px", type=float, default=5.0)
    parser.add_argument("--staff-space", type=float, default=None)
    args = parser.parse_args()

    pages = [
        PageSpec(
            name="page_3",
            image=REPO_ROOT / "data/evaluation/images/page_3.png",
            gt=REPO_ROOT / "data/evaluation/annotations/page_003/boxes_sorted.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_3/page_3_debug_6_notehead.png",
        ),
        PageSpec(
            name="page_10",
            image=REPO_ROOT / "data/training/images/page_10.png",
            gt=REPO_ROOT / "data/training/annotations/page_010/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_10/page_10_debug_6_notehead.png",
        ),
        PageSpec(
            name="page_15",
            image=REPO_ROOT / "data/training/images/page_15.png",
            gt=REPO_ROOT / "data/training/annotations/page_015/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_15/page_15_debug_6_notehead.png",
        ),
        PageSpec(
            name="page_001",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
            gt=REPO_ROOT
            / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_001/page_001_debug_6_notehead.png",
        ),
        PageSpec(
            name="page_004",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
            gt=REPO_ROOT
            / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_004/page_004_debug_6_notehead.png",
        ),
    ]

    run_root = args.run_root
    run_root.mkdir(parents=True, exist_ok=True)
    per_page_root = run_root / "per_page"
    overlay_root = run_root / "overlays"
    per_page_root.mkdir(parents=True, exist_ok=True)
    overlay_root.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    fn_total_tp = 0
    fn_total_gt = 0

    for page in pages:
        union_path = args.union_root / f"{page.name}_union.json"
        preds = load_preds(union_path)

        base_img = cv2.imread(str(page.image))
        if base_img is None:
            raise FileNotFoundError(f"Failed to load image: {page.image}")
        notehead_mask = load_notehead_mask(page.notehead_mask, base_img.shape[:2])

        y_centers = np.array([(box[1] + box[3]) / 2 for box in preds])
        rows, _ = cluster_by_y_distance(y_centers, args.cluster_max_dist, args.min_row_count)
        staff_space = (
            args.staff_space if args.staff_space is not None else estimate_staff_space(rows, preds)
        )

        row_filtered = row_filter(
            preds,
            args.cluster_max_dist,
            args.min_row_count,
            args.tol_top_px,
            args.tol_bottom_px,
        )

        geom_kept, geom_debug = geom_notehead_ratio_filter(
            row_filtered,
            notehead_mask,
            staff_space,
            args.endpoint_ratio_threshold,
            args.endpoint_radius_scale,
        )

        rejected = [tuple(map(int, item["bbox"])) for item in geom_debug.get("rejected", [])]

        metrics = None
        gt_boxes = None
        if page.gt:
            gt_boxes = load_gt(page.gt)
            metrics = evaluate(geom_kept, gt_boxes)
            if page.name != "page_3":
                fn_total_tp += metrics["TP"]
                fn_total_gt += metrics["TP"] + metrics["FN"]

        out_dir = per_page_root / page.name
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "kept.json").write_text(json.dumps(geom_kept, indent=2))
        (out_dir / "rejected.json").write_text(json.dumps(rejected, indent=2))
        (out_dir / "geom_debug.json").write_text(json.dumps(geom_debug, indent=2))

        summary = {
            "page": page.name,
            "row_filtered_count": len(row_filtered),
            "geom_kept_count": len(geom_kept),
            "geom_rejected_count": len(rejected),
            "staff_space": staff_space,
            "endpoint_ratio_threshold": args.endpoint_ratio_threshold,
            "endpoint_radius_scale": args.endpoint_radius_scale,
            "metrics": metrics,
        }
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

        overlay = base_img.copy()
        draw_boxes(overlay, geom_kept, (0, 255, 0), 1)
        draw_boxes(overlay, rejected, (0, 0, 255), 2)
        if page.name != "page_3" and gt_boxes:
            draw_boxes(overlay, gt_boxes, (255, 0, 0), 1)
        overlay_path = overlay_root / f"{page.name}_kept_rejected.png"
        cv2.imwrite(str(overlay_path), overlay)

        summary_rows.append(
            {
                "page": page.name,
                "tp": metrics["TP"] if metrics else None,
                "fp": metrics["FP"] if metrics else None,
                "fn": metrics["FN"] if metrics else None,
                "kept": len(geom_kept),
                "rejected": len(rejected),
            }
        )

    summary_table = [
        "| Page | TP | FP | FN | kept | rejected |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in summary_rows:
        summary_table.append(
            f"| {row['page']} | {row['tp']} | {row['fp']} | {row['fn']} | {row['kept']} | {row['rejected']} |"
        )
    if fn_total_gt > 0:
        summary_table.append(
            f"| FN-only total | {fn_total_tp} | n/a | {fn_total_gt - fn_total_tp} | n/a | n/a |"
        )

    (run_root / "summary_table.md").write_text("\n".join(summary_table) + "\n")

    readme = [
        "# Phase5 union notehead geom overlays",
        "",
        "Color key:",
        "- Green: kept detections after row + geom notehead ratio filter",
        "- Red: rejected detections (geom notehead ratio filter)",
        "- Blue: FN-only GT boxes (FN-only pages only)",
        "",
    ]
    readme.append("Files:")
    for page in pages:
        readme.append(f"- {overlay_root}/{page.name}_kept_rejected.png")
    (overlay_root / "README.md").write_text("\n".join(readme) + "\n")


if __name__ == "__main__":
    main()
