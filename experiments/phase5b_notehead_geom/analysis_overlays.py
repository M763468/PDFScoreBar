#!/usr/bin/env python3
"""
Phase 5b2 analysis overlays and diagnostics (no detector reruns).

Generates:
  - final TP/FP (page_3) or kept/matched FN targets (FN-only pages)
  - rejected by stage (row vs geom)
  - provenance (homr-only / omr-dln-only / both)
  - margin breakdown overlays and tables
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
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
    homr_raw: Path
    omr_raw: Path


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
    preds: Sequence[Box],
    notehead_mask: np.ndarray,
    staff_space_px: float,
    threshold: float,
    endpoint_radius_scale: float,
):
    h, w = notehead_mask.shape[:2]
    kept: List[Box] = []
    rejected: List[Dict[str, object]] = []
    scores: List[Dict[str, object]] = []

    rx = max(1, int(round(staff_space_px * endpoint_radius_scale)))
    ry = max(2, int(round(staff_space_px * endpoint_radius_scale)))

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
            "endpoint_radius_px": {"x": int(rx), "y": int(ry)},
        },
        "scores": scores,
        "rejected": rejected,
    }
    return kept, rejected, debug


def evaluate(preds: Sequence[Box], gt: Sequence[Box]) -> Dict[str, float]:
    result = greedy_barline_match(list(preds), list(gt), iou_threshold=0.5)
    tp = len(result.matches)
    fp = len(result.false_positive_indices)
    fn = len(result.false_negative_indices)
    return {
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "Precision": tp / (tp + fp) if (tp + fp) > 0 else 0.0,
        "Recall": tp / (tp + fn) if (tp + fn) > 0 else 0.0,
    }


def draw_boxes(
    base: np.ndarray, boxes: Sequence[Box], color: Tuple[int, int, int], thickness: int
) -> None:
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(base, (x1, y1), (x2, y2), color, thickness)


def classify_margin(box: Box, width: int, band_px: int) -> str:
    cx = (box[0] + box[2]) / 2
    if cx <= band_px:
        return "left"
    if cx >= width - band_px:
        return "right"
    return "interior"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--union-root", type=Path, required=True)
    parser.add_argument("--analysis-tag", type=str, default=None)
    parser.add_argument("--endpoint-ratio-threshold", type=float, default=0.1)
    parser.add_argument("--endpoint-radius-scale", type=float, default=0.6)
    parser.add_argument("--cluster-max-dist", type=float, default=25.0)
    parser.add_argument("--min-row-count", type=int, default=3)
    parser.add_argument("--tol-top-px", type=float, default=5.0)
    parser.add_argument("--tol-bottom-px", type=float, default=5.0)
    args = parser.parse_args()

    tag = args.analysis_tag or datetime.now().strftime("%Y%m%dT%H%M%S")
    analysis_root = args.run_root / f"analysis_{tag}"
    overlay_root = analysis_root / "overlays"
    overlay_root.mkdir(parents=True, exist_ok=True)

    pages = [
        PageSpec(
            name="page_3",
            image=REPO_ROOT / "data/evaluation/images/page_3.png",
            gt=REPO_ROOT / "data/evaluation/annotations/page_003/boxes_sorted.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_3/page_3_debug_6_notehead.png",
            homr_raw=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_3/page_3_detections.json",
            omr_raw=REPO_ROOT
            / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/page_3/predictions.json",
        ),
        PageSpec(
            name="page_10",
            image=REPO_ROOT / "data/training/images/page_10.png",
            gt=REPO_ROOT / "data/training/annotations/page_010/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_10/page_10_debug_6_notehead.png",
            homr_raw=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_10/page_10_detections.json",
            omr_raw=REPO_ROOT
            / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/page_10/predictions.json",
        ),
        PageSpec(
            name="page_15",
            image=REPO_ROOT / "data/training/images/page_15.png",
            gt=REPO_ROOT / "data/training/annotations/page_015/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_15/page_15_debug_6_notehead.png",
            homr_raw=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_15/page_15_detections.json",
            omr_raw=REPO_ROOT
            / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/page_15/predictions.json",
        ),
        PageSpec(
            name="page_001",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
            gt=REPO_ROOT
            / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_001/page_001_debug_6_notehead.png",
            homr_raw=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_001/page_001_detections.json",
            omr_raw=REPO_ROOT
            / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/page_001/predictions.json",
        ),
        PageSpec(
            name="page_004",
            image=REPO_ROOT / "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
            gt=REPO_ROOT
            / "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json",
            notehead_mask=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_004/page_004_debug_6_notehead.png",
            homr_raw=REPO_ROOT
            / "logs/phase5b_homr_recall/homr_factor_1p0/page_004/page_004_detections.json",
            omr_raw=REPO_ROOT
            / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/page_004/predictions.json",
        ),
    ]

    stage_counts = []
    margin_rows = []

    for page in pages:
        union_path = args.union_root / f"{page.name}_union.json"
        union_preds = load_preds(union_path)
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

        geom_kept, geom_rejected, geom_debug = geom_notehead_ratio_filter(
            row_kept,
            notehead_mask,
            staff_space,
            args.endpoint_ratio_threshold,
            args.endpoint_radius_scale,
        )

        gt_boxes = load_gt(page.gt) if page.gt else []
        match = greedy_barline_match(geom_kept, gt_boxes, iou_threshold=0.5)

        tp_indices = {m.pred_index for m in match.matches}
        fp_indices = set(match.false_positive_indices)
        fn_indices = set(match.false_negative_indices)

        tp_boxes = [geom_kept[i] for i in sorted(tp_indices)]
        fp_boxes = [geom_kept[i] for i in sorted(fp_indices)]
        fn_boxes = [gt_boxes[i] for i in sorted(fn_indices)] if page.gt else []
        matched_fn_boxes = [gt_boxes[m.gt_index] for m in match.matches] if page.gt else []

        # Overlay: final TP/FP or matched/unmatched FN targets
        final_overlay = base_img.copy()
        if page.name == "page_3":
            draw_boxes(final_overlay, tp_boxes, (0, 255, 0), 2)
            draw_boxes(final_overlay, fp_boxes, (0, 0, 255), 2)
        else:
            draw_boxes(final_overlay, geom_kept, (0, 255, 0), 2)
            draw_boxes(final_overlay, fn_boxes, (255, 0, 255), 2)  # unmatched FN targets
            draw_boxes(final_overlay, matched_fn_boxes, (255, 255, 0), 2)  # matched FN targets
        cv2.imwrite(str(overlay_root / f"{page.name}_final_tp_fp.png"), final_overlay)

        # Overlay: rejected by stage
        rejected_overlay = base_img.copy()
        draw_boxes(rejected_overlay, row_rejected, (0, 165, 255), 2)  # orange
        draw_boxes(
            rejected_overlay, [tuple(item["bbox"]) for item in geom_rejected], (0, 0, 255), 2
        )
        cv2.imwrite(str(overlay_root / f"{page.name}_rejected_by_stage.png"), rejected_overlay)

        # Overlay: provenance of final kept
        prov_overlay = base_img.copy()
        for box in geom_kept:
            in_homr = box in homr_preds
            in_omr = box in omr_preds
            if in_homr and in_omr:
                color = (0, 255, 0)
            elif in_homr:
                color = (255, 0, 0)
            elif in_omr:
                color = (0, 255, 255)
            else:
                color = (128, 128, 128)
            draw_boxes(prov_overlay, [box], color, 2)
        cv2.imwrite(str(overlay_root / f"{page.name}_provenance.png"), prov_overlay)

        # Margin classification for unmatched kept
        band_px = max(40, int(0.05 * base_img.shape[1]))
        unmatched = (
            fp_boxes if page.name == "page_3" else [geom_kept[i] for i in sorted(fp_indices)]
        )
        margin_counts = {"left": 0, "right": 0, "interior": 0}
        for box in unmatched:
            margin_counts[classify_margin(box, base_img.shape[1], band_px)] += 1

        margin_rows.append(
            {
                "page": page.name,
                "kept": len(geom_kept),
                "matched": len(tp_boxes) if page.name == "page_3" else len(matched_fn_boxes),
                "unmatched": len(unmatched),
                "left": margin_counts["left"],
                "right": margin_counts["right"],
                "interior": margin_counts["interior"],
                "band_px": band_px,
            }
        )

        margin_overlay = base_img.copy()
        for box in unmatched:
            cls = classify_margin(box, base_img.shape[1], band_px)
            color = (
                (0, 0, 255) if cls == "left" else (0, 128, 255) if cls == "right" else (0, 255, 255)
            )
            draw_boxes(margin_overlay, [box], color, 3)
        cv2.imwrite(str(overlay_root / f"{page.name}_margin_class.png"), margin_overlay)

        stage_counts.append(
            {
                "page": page.name,
                "union_raw": len(union_preds),
                "row_kept": len(row_kept),
                "row_rejected": len(row_rejected),
                "geom_kept": len(geom_kept),
                "geom_rejected": len(geom_rejected),
                "tp": len(tp_boxes) if page.name == "page_3" else len(matched_fn_boxes),
                "fp_or_unmatched": len(fp_boxes) if page.name == "page_3" else len(unmatched),
                "fn": len(fn_boxes) if page.name == "page_3" else len(fn_boxes),
            }
        )

    # Write summaries
    stage_md = [
        "| Page | union_raw | row_kept | row_rejected | geom_kept | geom_rejected | matched | unmatched | fn |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in stage_counts:
        stage_md.append(
            f"| {row['page']} | {row['union_raw']} | {row['row_kept']} | {row['row_rejected']} | "
            f"{row['geom_kept']} | {row['geom_rejected']} | {row['tp']} | {row['fp_or_unmatched']} | {row['fn']} |"
        )
    (analysis_root / "stage_counts.md").write_text("\n".join(stage_md) + "\n")

    margin_md = [
        "| Page | kept | matched | unmatched | left | right | interior | band_px |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in margin_rows:
        margin_md.append(
            f"| {row['page']} | {row['kept']} | {row['matched']} | {row['unmatched']} | "
            f"{row['left']} | {row['right']} | {row['interior']} | {row['band_px']} |"
        )
    (analysis_root / "fp_margin_breakdown.md").write_text("\n".join(margin_md) + "\n")

    # README for overlay semantics
    readme = [
        "# Overlays (Phase5b2 analysis)",
        "",
        "Files:",
        "- `<page>_final_tp_fp.png`: page_3 shows TP (green) vs FP (red). FN-only pages show kept (green),",
        "  matched FN targets (yellow), unmatched FN targets (magenta).",
        "- `<page>_rejected_by_stage.png`: row-rejected (orange), geom-rejected (red).",
        "- `<page>_provenance.png`: homr-only (blue), omr-dln-only (yellow), both (green), unknown (gray).",
        "- `<page>_margin_class.png`: unmatched kept boxes classified by margin (left red, right orange, interior yellow).",
        "",
        "Matching rule:",
        "- IoU=0.5 using `greedy_barline_match` from `src/common/barline_evaluation.py`.",
        "GT sources:",
        "- page_3: full GT `data/evaluation/annotations/page_003/boxes_sorted.json`",
        "- FN-only pages: FN-only GT JSONs in `data/training/annotations/page_010/fn_only.json`, etc.",
    ]
    (overlay_root / "README.md").write_text("\n".join(readme) + "\n")


if __name__ == "__main__":
    main()
