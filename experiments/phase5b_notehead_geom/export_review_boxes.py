#!/usr/bin/env python3
"""
Export review box sets from existing union inputs (no detector reruns).
Writes per-page JSON with box categories + provenance, and a manifest.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

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
    gt: Path
    notehead_mask: Path
    homr_raw: Path
    omr_raw: Path
    overlay: Path


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


def estimate_staff_space(rows: Dict[int, List[int]], preds_list: List[Box]) -> float:
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
    preds: List[Box],
    cluster_max_dist: float,
    min_row_count: int,
    tol_top: float,
    tol_bottom: float,
) -> Tuple[List[Box], List[Box]]:
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
    kept = [preds[i] for i in sorted(accepted_indices)]
    rejected = [preds[i] for i in range(len(preds)) if i not in accepted_indices]
    return kept, rejected


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
    preds: List[Box],
    notehead_mask: np.ndarray,
    staff_space_px: float,
    threshold: float,
    endpoint_radius_scale: float,
) -> Tuple[List[Box], List[Box]]:
    h, w = notehead_mask.shape[:2]
    kept: List[Box] = []
    rejected: List[Box] = []
    rx = max(1, int(round(staff_space_px * endpoint_radius_scale)))
    ry = max(2, int(round(staff_space_px * endpoint_radius_scale)))
    for box in preds:
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
        total_area = int(top_region.size + bot_region.size)
        total_notehead = int(np.count_nonzero(top_region) + np.count_nonzero(bot_region))
        overlap_ratio = 0.0 if total_area == 0 else total_notehead / total_area
        if overlap_ratio > threshold:
            rejected.append((x1, y1, x2, y2))
        else:
            kept.append((x1, y1, x2, y2))
    return kept, rejected


def provenance_map(box: Box, homr: set[Box], omr: set[Box]) -> str:
    in_homr = box in homr
    in_omr = box in omr
    if in_homr and in_omr:
        return "both"
    if in_homr:
        return "homr_only"
    if in_omr:
        return "omr_only"
    return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--union-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--overlay-root", type=Path, required=True)
    parser.add_argument("--endpoint-ratio-threshold", type=float, default=0.1)
    parser.add_argument("--endpoint-radius-scale", type=float, default=0.6)
    parser.add_argument("--cluster-max-dist", type=float, default=25.0)
    parser.add_argument("--min-row-count", type=int, default=3)
    parser.add_argument("--tol-top-px", type=float, default=5.0)
    parser.add_argument("--tol-bottom-px", type=float, default=5.0)
    args = parser.parse_args()

    out_root = args.output_root
    out_root.mkdir(parents=True, exist_ok=True)

    pages = [
        PageSpec(
            name="page_3",
            image=REPO_ROOT / "data/evaluation/images/page_3.png",
            gt=REPO_ROOT / "data/evaluation/annotations/page_003/boxes_sorted.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_3/page_3_debug_6_notehead.png",
            homr_raw=REPO_ROOT / "logs/phase5b_homr_recall/homr_factor_1p0/page_3/page_3_detections.json",
            omr_raw=REPO_ROOT
            / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/page_3/predictions.json",
            overlay=args.overlay_root / "page_3_final_matched_vs_unmatched.png",
        ),
        PageSpec(
            name="page_10",
            image=REPO_ROOT / "data/training/images/page_10.png",
            gt=REPO_ROOT / "data/training/annotations/page_010/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_10/page_10_debug_6_notehead.png",
            homr_raw=REPO_ROOT / "logs/phase5b_homr_recall/homr_factor_1p0/page_10/page_10_detections.json",
            omr_raw=REPO_ROOT
            / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/page_10/predictions.json",
            overlay=args.overlay_root / "page_10_final_matched_vs_unmatched.png",
        ),
        PageSpec(
            name="page_15",
            image=REPO_ROOT / "data/training/images/page_15.png",
            gt=REPO_ROOT / "data/training/annotations/page_015/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_15/page_15_debug_6_notehead.png",
            homr_raw=REPO_ROOT / "logs/phase5b_homr_recall/homr_factor_1p0/page_15/page_15_detections.json",
            omr_raw=REPO_ROOT
            / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/page_15/predictions.json",
            overlay=args.overlay_root / "page_15_final_matched_vs_unmatched.png",
        ),
        PageSpec(
            name="page_001",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
            gt=REPO_ROOT
            / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_001/page_001_debug_6_notehead.png",
            homr_raw=REPO_ROOT / "logs/phase5b_homr_recall/homr_factor_1p0/page_001/page_001_detections.json",
            omr_raw=REPO_ROOT
            / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/page_001/predictions.json",
            overlay=args.overlay_root / "page_001_final_matched_vs_unmatched.png",
        ),
        PageSpec(
            name="page_004",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
            gt=REPO_ROOT
            / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_004/page_004_debug_6_notehead.png",
            homr_raw=REPO_ROOT / "logs/phase5b_homr_recall/homr_factor_1p0/page_004/page_004_detections.json",
            omr_raw=REPO_ROOT
            / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/page_004/predictions.json",
            overlay=args.overlay_root / "page_004_final_matched_vs_unmatched.png",
        ),
    ]

    manifest = {"pages": []}
    for page in pages:
        union_preds = load_preds(args.union_root / f"{page.name}_union.json")
        homr_preds = set(load_preds(page.homr_raw))
        omr_preds = set(load_preds(page.omr_raw))

        base_img = cv2.imread(str(page.image))
        if base_img is None:
            raise FileNotFoundError(f"Failed to load image: {page.image}")
        notehead_mask = load_notehead_mask(page.notehead_mask, base_img.shape[:2])

        rows, _ = cluster_by_y_distance(
            np.array([(b[1] + b[3]) / 2 for b in union_preds]),
            args.cluster_max_dist,
            args.min_row_count,
        )
        staff_space = estimate_staff_space(rows, union_preds)
        row_kept, row_rejected = row_filter(
            union_preds,
            args.cluster_max_dist,
            args.min_row_count,
            args.tol_top_px,
            args.tol_bottom_px,
        )
        geom_kept, geom_rejected = geom_notehead_ratio_filter(
            row_kept,
            notehead_mask,
            staff_space,
            args.endpoint_ratio_threshold,
            args.endpoint_radius_scale,
        )

        gt_boxes = load_gt(page.gt)
        match = greedy_barline_match(geom_kept, gt_boxes, iou_threshold=0.5)
        tp_indices = {m.pred_index for m in match.matches}
        fp_indices = set(match.false_positive_indices)
        fn_indices = set(match.false_negative_indices)

        entries = []
        for idx, box in enumerate(geom_kept):
            entries.append(
                {
                    "id": f"kept_{idx}",
                    "bbox": list(box),
                    "category": "final_matched" if idx in tp_indices else "final_unmatched",
                    "provenance": provenance_map(box, homr_preds, omr_preds),
                }
            )
        for idx, box in enumerate(row_rejected):
            entries.append(
                {
                    "id": f"row_rejected_{idx}",
                    "bbox": list(box),
                    "category": "rejected_row",
                    "provenance": provenance_map(box, homr_preds, omr_preds),
                }
            )
        for idx, box in enumerate(geom_rejected):
            entries.append(
                {
                    "id": f"geom_rejected_{idx}",
                    "bbox": list(box),
                    "category": "rejected_geom",
                    "provenance": provenance_map(box, homr_preds, omr_preds),
                }
            )
        for idx in fn_indices:
            entries.append(
                {
                    "id": f"fn_target_{idx}",
                    "bbox": list(gt_boxes[idx]),
                    "category": "fn_target_unmatched",
                    "provenance": "gt",
                }
            )

        page_file = out_root / f"{page.name}_boxes.json"
        page_file.write_text(json.dumps(entries, indent=2))

        manifest["pages"].append(
            {
                "name": page.name,
                "image": str(page.image.relative_to(REPO_ROOT)),
                "overlay": str(page.overlay),
                "boxes": str(page_file),
            }
        )

    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
