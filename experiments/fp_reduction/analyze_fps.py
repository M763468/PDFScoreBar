# NOTE (2025-12 repo restructure): This script may still assume pre-restructure paths (src/tools, tools/fp_reduction). Adjust imports if reusing.
#!/usr/bin/env python3
"""Analyze remaining False Positives from the final heuristic run."""

import csv
import json
from collections import defaultdict


def analyze_fps(metrics_path, stats_path, detections_path):
    # Load metrics
    with open(metrics_path, "r") as f:
        metrics = json.load(f)

    page_metrics = metrics["images"][0]

    # Extract indices
    tp_indices = set(m["pred_index"] for m in page_metrics["matches"])
    soft_indices = set(m["pred_index"] for m in page_metrics["soft_matches"])

    total_preds = page_metrics["num_predictions"]
    fp_indices = [i for i in range(total_preds) if i not in tp_indices and i not in soft_indices]

    print(f"Total Predictions: {total_preds}")
    print(f"TPs: {len(tp_indices)}, Soft: {len(soft_indices)}, FPs: {len(fp_indices)}")
    print(f"\nFP Indices: {fp_indices}\n")

    # Load stats
    stats_by_idx = {}
    with open(stats_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["pred_index"])
            stats_by_idx[idx] = {
                "x1": int(row["x1"]),
                "y1": int(row["y1"]),
                "x2": int(row["x2"]),
                "y2": int(row["y2"]),
                "width": int(row["width"]),
                "height": int(row["height"]),
                "dist": float(row["min_dist_to_notehead"]),
                "overlap": float(row["overlap_area"]),
            }

    # Load detections for system/staff info
    with open(detections_path, "r") as f:
        json.load(f)

    # Analyze FPs
    print("=" * 80)
    print("FALSE POSITIVE ANALYSIS")
    print("=" * 80)

    # Safe Filter criteria
    DIST_THRESH = 5.0
    HEIGHT_THRESH = 24
    WIDTH_THRESH = 4
    OVERLAP_THRESH = 5

    categories = defaultdict(list)

    for idx in fp_indices:
        if idx not in stats_by_idx:
            print(f"WARNING: FP {idx} not in stats!")
            continue

        s = stats_by_idx[idx]

        # Determine why it passed the filter
        reasons = []
        if s["dist"] >= DIST_THRESH:
            reasons.append("far_from_notehead")
        if s["height"] >= HEIGHT_THRESH:
            reasons.append("tall")
        if s["width"] >= WIDTH_THRESH:
            reasons.append("wide")
        if s["overlap"] < OVERLAP_THRESH:
            reasons.append("low_overlap")

        category = "+".join(reasons) if reasons else "UNKNOWN"
        categories[category].append(idx)

        print(
            f"FP #{idx:3d}: ({s['x1']:3d},{s['y1']:3d})-({s['x2']:3d},{s['y2']:3d}) "
            f"W={s['width']:2d} H={s['height']:2d} Dist={s['dist']:5.1f} Overlap={s['overlap']:4.1f} "
            f"→ {category}"
        )

    print("\n" + "=" * 80)
    print("CATEGORY SUMMARY")
    print("=" * 80)
    for cat, indices in sorted(categories.items(), key=lambda x: -len(x[1])):
        print(f"{cat:40s}: {len(indices):2d} FPs → {indices[:10]}")

    return categories, stats_by_idx, fp_indices


if __name__ == "__main__":
    metrics_file = "logs/homr_eval/20251206T_homr_heuristic_final/metrics.json"
    stats_file = "logs/homr_eval/20251206T_homr_diagnosis/page_3/page_3_candidate_stats.csv"
    detections_file = "logs/homr_eval/20251206T_homr_heuristic_final/page_3/page_3_detections.json"

    analyze_fps(metrics_file, stats_file, detections_file)
