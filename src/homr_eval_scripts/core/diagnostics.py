"""Evaluation-only cluster decisions, candidate statistics and diagnostic CSVs."""

from __future__ import annotations

import collections
import csv
from pathlib import Path
from typing import List

import cv2
import numpy as np

from src.homr_runtime.filtering import count_staff_crossings
from src.homr_runtime.types import BarlinePrediction


def resolve_clusters_dry_run(
    predictions: List[BarlinePrediction],
    notehead_mask: np.ndarray,
    stem: str,
    output_dir: Path,
    base_gap_threshold: int = 15,
) -> None:
    """
    Dry-run implementation of Cluster Resolution Heuristic.
    Groups barline candidates by proximity and determines which ones WOULD be removed.
    Writes decisions to candidate_clusters.csv.

    Logic:
    1. Group by Staff.
    2. Cluster by horizontal distance (gap <= 15px).
    3. Score each candidate (Strength = Height + Overlap*2).
    4. Resolve:
       - Tight (<4px): Keep Best (Duplicate).
       - Medium (4-15px): Keep Both if Double Barline (Strong+Strong), else Keep Strongest.
    """
    mask_h, mask_w = notehead_mask.shape

    # 1. Group by Staff
    grouped = collections.defaultdict(list)
    for idx, pred in enumerate(predictions):
        key = (pred.system_index, pred.staff_index)
        grouped[key].append((idx, pred))

    cluster_rows = []

    for (sys_idx, staff_idx), items in grouped.items():
        # Sort by x-center
        items.sort(key=lambda item: (item[1].orig_bbox[0] + item[1].orig_bbox[2]) / 2)

        # 2. Form Clusters
        clusters = []
        if not items:
            continue

        current_cluster = [items[0]]

        for i in range(1, len(items)):
            prev = items[i - 1][1]
            curr = items[i][1]

            prev_cx = (prev.orig_bbox[0] + prev.orig_bbox[2]) / 2
            curr_cx = (curr.orig_bbox[0] + curr.orig_bbox[2]) / 2
            gap = curr_cx - prev_cx

            if gap <= base_gap_threshold:
                current_cluster.append(items[i])
            else:
                clusters.append(current_cluster)
                current_cluster = [items[i]]
        clusters.append(current_cluster)

        # 3. Resolve Clusters
        for c_id, cluster in enumerate(clusters):
            # Calculate scores for all in cluster
            scored_cluster = []
            for original_idx, pred in cluster:
                x1, y1, x2, y2 = pred.orig_bbox
                h = y2 - y1

                # Re-calculate overlap (expensive but necessary if not passed)
                # Optimization: Could pass pre-computed stats, but for dry run this is fine.
                y1_c = max(0, min(mask_h, y1))
                y2_c = max(0, min(mask_h, y2))
                x1_c = max(0, min(mask_w, x1))
                x2_c = max(0, min(mask_w, x2))

                if x1_c >= x2_c or y1_c >= y2_c:
                    overlap_area = 0.0
                else:
                    box_window = notehead_mask[y1_c:y2_c, x1_c:x2_c]
                    overlap_area = float(np.count_nonzero(box_window))

                # SCORE FORMULA
                score = float(h) + (overlap_area * 2.0)
                scored_cluster.append(
                    {
                        "pred": pred,
                        "idx": original_idx,
                        "score": score,
                        "height": h,
                        "overlap": overlap_area,
                        "decision": "KEEP",  # Default
                        "reason": "SOLITARY" if len(cluster) == 1 else "BEST",
                    }
                )

            # Resolution Logic
            if len(scored_cluster) > 1:
                # Sort by Score Descending
                scored_cluster.sort(key=lambda x: x["score"], reverse=True)
                primary = scored_cluster[0]
                primary["decision"] = "KEEP"
                primary["reason"] = "BEST"

                prim_cx = (primary["pred"].orig_bbox[0] + primary["pred"].orig_bbox[2]) / 2

                for secondary in scored_cluster[1:]:
                    sec_cx = (secondary["pred"].orig_bbox[0] + secondary["pred"].orig_bbox[2]) / 2
                    dist = abs(sec_cx - prim_cx)

                    if dist < 4.0:
                        # TIGHT CLUSTER -> Duplicate -> Remove Weaker
                        secondary["decision"] = "REMOVE"
                        secondary["reason"] = "DUPLICATE"
                    else:
                        # MEDIUM CLUSTER (4-15px) -> Potential Double Barline
                        # Check Strength Profile
                        # Double Barline Candidates passed Safe Filter, so H>=24 or Ov>=5 if small.
                        # Score Threshold: > 25 (e.g. H=25, Ov=0 OR H=15, Ov=5 -> Score 25)

                        is_strong = secondary["score"] > 25.0
                        primary_is_strong = primary["score"] > 25.0

                        if is_strong and primary_is_strong:
                            secondary["decision"] = "KEEP"
                            secondary["reason"] = "DOUBLE_BARLINE"
                        else:
                            secondary["decision"] = "REMOVE"
                            secondary["reason"] = "WEAK_NEIGHBOR"

            # 4. Log Decisions
            for item in scored_cluster:
                cluster_rows.append(
                    {
                        "image": stem,
                        "pred_index": item["idx"],
                        "cluster_id": c_id,
                        "x_center": (item["pred"].orig_bbox[0] + item["pred"].orig_bbox[2]) / 2,
                        "score": item["score"],
                        "height": item["height"],
                        "overlap": item["overlap"],
                        "decision": item["decision"],
                        "reason": item["reason"],
                    }
                )

    # Save CSV
    csv_path = output_dir / f"{stem}_candidate_clusters.csv"
    if not cluster_rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "image",
            "pred_index",
            "cluster_id",
            "x_center",
            "score",
            "height",
            "overlap",
            "decision",
            "reason",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cluster_rows)


def resolve_tight_duplicates_dry_run(
    predictions: List[BarlinePrediction],
    notehead_mask: np.ndarray,
    stem: str,
    output_dir: Path,
) -> None:
    """
    Phase 12: Tight Duplicate Merging (Dry Run).
    Groups candidates on same staff with gap <= 3px AND Vertical IoU >= 0.5.
    Keeps the Strongest. Output to tight_duplicates_candidates.csv.
    """
    mask_h, mask_w = notehead_mask.shape

    # 1. Group by Staff
    grouped = collections.defaultdict(list)
    for idx, pred in enumerate(predictions):
        key = (pred.system_index, pred.staff_index)
        grouped[key].append((idx, pred))

    rows = []

    for (sys_idx, staff_idx), items in grouped.items():
        # Sort by x-center
        items.sort(key=lambda item: (item[1].orig_bbox[0] + item[1].orig_bbox[2]) / 2)

        # 2. Form Clusters (Gap <= 3px)
        clusters = []
        if not items:
            continue

        current_cluster = [items[0]]

        for i in range(1, len(items)):
            prev = items[i - 1][1]
            curr = items[i][1]

            prev_cx = (prev.orig_bbox[0] + prev.orig_bbox[2]) / 2
            curr_cx = (curr.orig_bbox[0] + curr.orig_bbox[2]) / 2
            gap = curr_cx - prev_cx

            if gap <= 3.0:
                current_cluster.append(items[i])
            else:
                clusters.append(current_cluster)
                current_cluster = [items[i]]
        clusters.append(current_cluster)

        # 3. Resolve & Filter by Vertical IoU
        for c_id, cluster in enumerate(clusters):
            if len(cluster) == 1:
                # Log Solitary
                item = cluster[0]
                rows.append(
                    {
                        "image": stem,
                        "pred_index": item[0],
                        "cluster_id": c_id,
                        "x_center": (item[1].orig_bbox[0] + item[1].orig_bbox[2]) / 2,
                        "decision": "KEEP",
                        "reason": "SOLITARY",
                    }
                )
                continue

            # Check vertical overlaps in cluster pairwise or group-wise
            # Simplification: In a tight cluster <3px, we assume transitivity if sorted
            # Verify adjacent pairs have Y-IoU >= 0.5. If not, split cluster?
            # For simplicity: Keep the whole cluster together, but only mark removal if IoU holds.
            # Actually, standard logic: Find Best in cluster. Remove others ONLY IF they overlap vertically with Best.

            # Score first
            scored_cluster = []
            for original_idx, pred in cluster:
                x1, y1, x2, y2 = pred.orig_bbox
                h = y2 - y1
                # Overlap
                y1_c = max(0, min(mask_h, y1))
                y2_c = max(0, min(mask_h, y2))
                x1_c = max(0, min(mask_w, x1))
                x2_c = max(0, min(mask_w, x2))
                if x1_c >= x2_c or y1_c >= y2_c:
                    overlap_area = 0.0
                else:
                    box_window = notehead_mask[y1_c:y2_c, x1_c:x2_c]
                    overlap_area = float(np.count_nonzero(box_window))

                score = float(h) + (overlap_area * 2.0)
                scored_cluster.append(
                    {"pred": pred, "idx": original_idx, "score": score, "y_span": (y1, y2)}
                )

            # Sort by Score Descending
            scored_cluster.sort(key=lambda x: x["score"], reverse=True)
            primary = scored_cluster[0]

            # Log Primary
            rows.append(
                {
                    "image": stem,
                    "pred_index": primary["idx"],
                    "cluster_id": c_id,
                    "x_center": (primary["pred"].orig_bbox[0] + primary["pred"].orig_bbox[2]) / 2,
                    "decision": "KEEP",
                    "reason": "BEST",
                }
            )

            # Check others
            py1, py2 = primary["y_span"]

            for secondary in scored_cluster[1:]:
                sy1, sy2 = secondary["y_span"]

                # Vertical IoU
                inter_y1 = max(py1, sy1)
                inter_y2 = min(py2, sy2)
                inter_h = max(0, inter_y2 - inter_y1)

                union_h = (py2 - py1) + (sy2 - sy1) - inter_h
                iou_y = inter_h / union_h if union_h > 0 else 0.0

                if iou_y >= 0.5:
                    decision = "REMOVE"
                    reason = "DUPLICATE"
                else:
                    decision = "KEEP"
                    reason = "NO_OVERLAP"

                rows.append(
                    {
                        "image": stem,
                        "pred_index": secondary["idx"],
                        "cluster_id": c_id,
                        "x_center": (
                            secondary["pred"].orig_bbox[0] + secondary["pred"].orig_bbox[2]
                        )
                        / 2,
                        "decision": decision,
                        "reason": reason,
                    }
                )

    csv_path = output_dir / f"{stem}_tight_duplicates_candidates.csv"
    if not rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = ["image", "pred_index", "cluster_id", "x_center", "decision", "reason"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_measure_grid_candidates(
    predictions: List[BarlinePrediction],
    notehead_mask: np.ndarray,
    stem: str,
    output_dir: Path,
) -> None:
    """
    Phase 13: Export data for Measure Grid Consistency (DP) validation.
    Saves candidate stats + score + gaps to measure_grid_candidates.csv.
    """
    mask_h, mask_w = notehead_mask.shape

    # Group by Staff
    grouped = collections.defaultdict(list)
    for idx, pred in enumerate(predictions):
        key = (pred.system_index, pred.staff_index)
        grouped[key].append((idx, pred))

    rows = []

    for (sys_idx, staff_idx), items in grouped.items():
        # Sort by x-center
        items.sort(key=lambda item: (item[1].orig_bbox[0] + item[1].orig_bbox[2]) / 2)

        for original_idx, pred in items:
            x1, y1, x2, y2 = pred.orig_bbox
            h = y2 - y1

            # Recalculate overlap for scoring
            y1_c = max(0, min(mask_h, y1))
            y2_c = max(0, min(mask_h, y2))
            x1_c = max(0, min(mask_w, x1))
            x2_c = max(0, min(mask_w, x2))

            if x1_c >= x2_c or y1_c >= y2_c:
                overlap_area = 0.0
            else:
                box_window = notehead_mask[y1_c:y2_c, x1_c:x2_c]
                overlap_area = float(np.count_nonzero(box_window))

            # Score
            score = float(h) + (overlap_area * 2.0)

            rows.append(
                {
                    "image": stem,
                    "pred_index": original_idx,
                    "system_index": sys_idx,
                    "staff_index": staff_idx,
                    "x_center": (x1 + x2) / 2,
                    "width": x2 - x1,
                    "height": h,
                    "overlap": overlap_area,
                    "score": score,
                }
            )

    csv_path = output_dir / f"{stem}_measure_grid_candidates.csv"
    if not rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "image",
            "pred_index",
            "system_index",
            "staff_index",
            "x_center",
            "width",
            "height",
            "overlap",
            "score",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def compute_candidate_stats(
    predictions: List[BarlinePrediction],
    notehead_mask: np.ndarray,
    staff_mask: np.ndarray,
    stem: str,
    output_dir: Path,
) -> None:
    """
    Computes and saves statistics for each candidate barline to a CSV file.
    Stats include: width, height, distance to nearest notehead, intersection w/ notehead,
    and number of staff line crossings.
    """
    mask_h, mask_w = notehead_mask.shape
    stats_rows = []

    # Pre-compute distance transform for fast distance queries
    # dist_map[y, x] = distance to nearest zero pixel.
    # So we invert the mask: noteheads are 1 (non-zero), background 0.
    # We want distance to nearest Notehead (non-zero).
    # Invert: noteheads=0, background=1.
    # cv2.distanceTransform calculates distance to nearest ZERO pixel.
    # So we want noteheads to be 0.
    inverted_mask = cv2.bitwise_not(notehead_mask)
    dist_map = cv2.distanceTransform(inverted_mask, cv2.DIST_L2, 5)

    for idx, pred in enumerate(predictions):
        x1, y1, x2, y2 = pred.orig_bbox
        w = x2 - x1
        h = y2 - y1
        (x1 + x2) // 2
        (y1 + y2) // 2

        # Clamp to mask bounds
        c_y1 = max(0, min(mask_h - 1, y1))
        c_y2 = max(0, min(mask_h - 1, y2))
        c_x1 = max(0, min(mask_w - 1, x1))
        c_x2 = max(0, min(mask_w - 1, x2))

        if c_y1 >= c_y2 or c_x1 >= c_x2:
            min_dist = 9999.0
            overlap_area = 0
        else:
            # 1. Distance to nearest notehead
            # Extract distance map region
            dist_region = dist_map[c_y1:c_y2, c_x1:c_x2]
            min_dist = float(np.min(dist_region))

            # 2. Intersection (direct overlap)
            # Mask region is > 0 where noteheads are.
            mask_region = notehead_mask[c_y1:c_y2, c_x1:c_x2]
            overlap_count = np.count_nonzero(mask_region)
            overlap_area = float(overlap_count)

        # Count staff crossings
        num_crossings = count_staff_crossings(pred.orig_bbox, staff_mask)

        stats_rows.append(
            {
                "image": stem,
                "pred_index": idx,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width": w,
                "height": h,
                "min_dist_to_notehead": min_dist,
                "overlap_area": overlap_area,
                "num_staff_crossings": num_crossings,
            }
        )

    csv_path = output_dir / f"{stem}_candidate_stats.csv"
    if not stats_rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=stats_rows[0].keys())
        writer.writeheader()
        writer.writerows(stats_rows)


def compute_and_save_gap_stats(
    predictions: List[BarlinePrediction],
    stem: str,
    output_dir: Path,
) -> None:
    """
    Computes horizontal gaps between adjacent barlines on the same staff/system
    and saves to CSV.
    """
    # Group by staff/system
    # Structure: { (system_idx, staff_idx): [ (pred_idx, pred_obj), ... ] }
    grouped = collections.defaultdict(list)
    for idx, pred in enumerate(predictions):
        key = (pred.system_index, pred.staff_index)
        grouped[key].append((idx, pred))

    rows = []

    for (sys_idx, staff_idx), items in grouped.items():
        # Sort by x-center
        items.sort(key=lambda item: (item[1].orig_bbox[0] + item[1].orig_bbox[2]) / 2)

        for i, (original_idx, pred) in enumerate(items):
            x1, y1, x2, y2 = pred.orig_bbox
            cx = (x1 + x2) / 2

            # Gap to prev
            if i > 0:
                prev_pred = items[i - 1][1]
                prev_cx = (prev_pred.orig_bbox[0] + prev_pred.orig_bbox[2]) / 2
                gap_to_prev = cx - prev_cx
            else:
                gap_to_prev = -1.0  # Sentinel for "First in staff"

            # Gap to next
            if i < len(items) - 1:
                next_pred = items[i + 1][1]
                next_cx = (next_pred.orig_bbox[0] + next_pred.orig_bbox[2]) / 2
                gap_to_next = next_cx - cx
            else:
                gap_to_next = -1.0  # Sentinel for "Last in staff"

            rows.append(
                {
                    "image": stem,
                    "pred_index": original_idx,
                    "system_index": sys_idx,
                    "staff_index": staff_idx,
                    "x_center": cx,
                    "gap_to_prev": gap_to_prev,
                    "gap_to_next": gap_to_next,
                    "width": x2 - x1,
                    "height": y2 - y1,
                }
            )

    csv_path = output_dir / f"{stem}_candidate_gaps.csv"
    if not rows:
        return

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "image",
            "pred_index",
            "system_index",
            "staff_index",
            "x_center",
            "gap_to_prev",
            "gap_to_next",
            "width",
            "height",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
