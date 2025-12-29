#!/usr/bin/env python3
"""
Trace stage survival for FN targets and union-only FPs using existing artifacts.
No detector reruns, no filter changes.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import barline_iou

Box = Tuple[int, int, int, int]


@dataclass
class PageSpec:
    name: str
    gt: Path
    baseline: Path
    sr: Path
    omr: Path
    union: Path


def load_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "predictions" in data:
        boxes = []
        for pred in data["predictions"]:
            bbox = pred.get("orig_bbox", pred.get("pred_bbox"))
            if bbox:
                boxes.append(tuple(bbox))
        return boxes
    if isinstance(data, list):
        if not data:
            return []
        if isinstance(data[0], dict) and "barline_location" in data[0]:
            return [tuple(item["barline_location"]) for item in data]
        return [tuple(item) for item in data]
    return []


def has_match(box: Box, refs: Sequence[Box], thresh: float = 0.5) -> bool:
    return any(barline_iou(box, ref) >= thresh for ref in refs)


def match_indices(preds: Sequence[Box], refs: Sequence[Box], thresh: float = 0.5) -> List[int]:
    matched = []
    for i, box in enumerate(preds):
        if has_match(box, refs, thresh):
            matched.append(i)
    return matched


def cluster_by_y_distance(y_centers: np.ndarray, max_distance: float, min_cluster_size: int):
    if y_centers.size == 0:
        return {}, []
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


def row_filter(preds: Sequence[Box], tol_top: float, tol_bottom: float) -> List[Box]:
    if not preds:
        return []
    y_centers = np.array([(box[1] + box[3]) / 2 for box in preds])
    rows, _ = cluster_by_y_distance(y_centers, max_distance=25.0, min_cluster_size=3)
    accepted = set()
    for indices in rows.values():
        if len(indices) < 3:
            continue
        tops = [preds[i][1] for i in indices]
        bottoms = [preds[i][3] for i in indices]
        ref_top = float(np.median(tops))
        ref_bottom = float(np.median(bottoms))
        for i in indices:
            y1 = preds[i][1]
            y2 = preds[i][3]
            if abs(y1 - ref_top) <= tol_top and abs(y2 - ref_bottom) <= tol_bottom:
                accepted.add(i)
    return [preds[i] for i in sorted(accepted)]


def page3_known_fp_filter(preds: Sequence[Box]) -> List[Box]:
    known_fp_bboxes = [
        (335, 230, 336, 253),
        (479, 449, 480, 469),
    ]
    kept = []
    for box in preds:
        if any(all(abs(box[i] - k[i]) <= 1 for i in range(4)) for k in known_fp_bboxes):
            continue
        kept.append(box)
    return kept


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    pages = [
        PageSpec(
            name="page_3",
            gt=Path("data/evaluation/annotations/page_003/boxes_sorted.json"),
            baseline=Path("logs/homr_eval/baseline_for_hybrid/page_3/page_3_detections.json"),
            sr=Path("logs/hybrid_generalization/sr_eval_smoke_page3/sr/page_3/page_3/page_3_detections.json"),
            omr=Path("logs/hybrid_generalization/sr_eval_smoke_page3/omr_sr/predictions.json"),
            union=Path("logs/phase5b/union_inputs/20251221T141710/page_3_union.json"),
        ),
        PageSpec(
            name="page_10",
            gt=Path("data/training/annotations/page_010/fn_only.json"),
            baseline=Path("logs/hybrid_generalization/page_10_hybrid_test/baseline/page_10/page_10/page_10_detections.json"),
            sr=Path("logs/hybrid_generalization/page_10_hybrid_test/sr/page_10/page_10/page_10_detections.json"),
            omr=Path("logs/hybrid_generalization/page_10_hybrid_test/omr_sr/predictions.json"),
            union=Path("logs/phase5b/union_inputs/20251221T141710/page_10_union.json"),
        ),
        PageSpec(
            name="page_15",
            gt=Path("data/training/annotations/page_015/fn_only.json"),
            baseline=Path("logs/hybrid_generalization/page_15_hybrid_test/baseline/page_15/page_15/page_15_detections.json"),
            sr=Path("logs/hybrid_generalization/page_15_hybrid_test/sr/page_15/page_15/page_15_detections.json"),
            omr=Path("logs/hybrid_generalization/page_15_hybrid_test/omr_sr/predictions.json"),
            union=Path("logs/phase5b/union_inputs/20251221T141710/page_15_union.json"),
        ),
        PageSpec(
            name="page_001",
            gt=Path("data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/fn_only.json"),
            baseline=Path("logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/baseline/page_001/page_001/page_001_detections.json"),
            sr=Path("logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/sr/page_001/page_001/page_001_detections.json"),
            omr=Path("logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/omr_sr/predictions.json"),
            union=Path("logs/phase5b/union_inputs/20251221T141710/page_001_union.json"),
        ),
        PageSpec(
            name="page_004",
            gt=Path("data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json"),
            baseline=Path("logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/baseline/page_004/page_004/page_004_detections.json"),
            sr=Path("logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/sr/page_004/page_004/page_004_detections.json"),
            omr=Path("logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/omr_sr/predictions.json"),
            union=Path("logs/phase5b/union_inputs/20251221T141710/page_004_union.json"),
        ),
    ]

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    fn_rows = []
    for page in pages:
        gt_boxes = load_boxes(page.gt)
        baseline = load_boxes(page.baseline)
        sr = load_boxes(page.sr)
        omr = load_boxes(page.omr)

        # hybrid merge: keep baseline if supported by SR or OMR
        hybrid = [b for b in baseline if has_match(b, sr) or has_match(b, omr)]
        row = row_filter(hybrid, tol_top=5.0, tol_bottom=5.0)
        notehead = page3_known_fp_filter(row) if page.name == "page_3" else row

        for idx, gt in enumerate(gt_boxes):
            fn_rows.append(
                {
                    "page": page.name,
                    "gt_index": idx,
                    "gt_bbox": list(gt),
                    "in_baseline": has_match(gt, baseline),
                    "in_sr": has_match(gt, sr),
                    "in_omr": has_match(gt, omr),
                    "in_merge": has_match(gt, hybrid),
                    "in_row": has_match(gt, row),
                    "in_notehead": has_match(gt, notehead),
                }
            )

    fn_csv = output_root / "fn_trace_table.csv"
    fn_md = output_root / "fn_trace_table.md"
    with fn_csv.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fn_rows[0].keys())
        writer.writeheader()
        writer.writerows(fn_rows)
    with fn_md.open("w") as fh:
        fh.write("| page | gt_index | in_baseline | in_sr | in_omr | in_merge | in_row | in_notehead |\n")
        fh.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for row in fn_rows:
            fh.write(
                f"| {row['page']} | {row['gt_index']} | {row['in_baseline']} | {row['in_sr']} | {row['in_omr']} | {row['in_merge']} | {row['in_row']} | {row['in_notehead']} |\n"
            )

    # Union-only FP trace for page_3 (full GT)
    page3 = next(p for p in pages if p.name == "page_3")
    gt_boxes = load_boxes(page3.gt)
    union = load_boxes(page3.union)
    baseline = load_boxes(page3.baseline)
    sr = load_boxes(page3.sr)
    omr = load_boxes(page3.omr)
    hybrid = [b for b in baseline if has_match(b, sr) or has_match(b, omr)]
    row = row_filter(hybrid, tol_top=5.0, tol_bottom=5.0)
    notehead = page3_known_fp_filter(row)

    union_fp_rows = []
    for box in union:
        if has_match(box, gt_boxes):
            continue
        stage = "merge"
        if has_match(box, hybrid):
            stage = "row"
            if has_match(box, row):
                stage = "notehead"
                if has_match(box, notehead):
                    stage = "final"
        union_fp_rows.append(
            {
                "bbox": list(box),
                "removed_stage": stage,
                "in_hybrid": has_match(box, hybrid),
                "in_row": has_match(box, row),
                "in_notehead": has_match(box, notehead),
            }
        )

    fp_csv = output_root / "union_fp_trace_page3.csv"
    fp_md = output_root / "union_fp_trace_page3.md"
    with fp_csv.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=union_fp_rows[0].keys())
        writer.writeheader()
        writer.writerows(union_fp_rows)
    with fp_md.open("w") as fh:
        fh.write("| removed_stage | count |\n| --- | --- |\n")
        counts = {}
        for row in union_fp_rows:
            counts[row["removed_stage"]] = counts.get(row["removed_stage"], 0) + 1
        for stage, count in sorted(counts.items()):
            fh.write(f"| {stage} | {count} |\n")


if __name__ == "__main__":
    main()
