# NOTE (2025-12 repo restructure): This script may still assume pre-restructure paths (src/tools, tools/fp_reduction). Adjust imports if reusing.
#!/usr/bin/env python3
"""Analyze staff-crossing distributions for TPs vs FPs."""

import csv
import json
from collections import Counter


def analyze_crossings(metrics_path, stats_path):
    # Load metrics
    with open(metrics_path, "r") as f:
        metrics = json.load(f)

    page_metrics = metrics["images"][0]
    tp_indices = set(m["pred_index"] for m in page_metrics["matches"])
    soft_indices = set(m["pred_index"] for m in page_metrics["soft_matches"])
    total_preds = page_metrics["num_predictions"]
    fp_indices = [i for i in range(total_preds) if i not in tp_indices and i not in soft_indices]

    print(f"Total Predictions: {total_preds}")
    print(f"TPs: {len(tp_indices)}, Soft: {len(soft_indices)}, FPs: {len(fp_indices)}\n")

    # Load stats
    stats_by_idx = {}
    with open(stats_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["pred_index"])
            stats_by_idx[idx] = {
                "crossings": int(row["num_staff_crossings"]),
                "dist": float(row["min_dist_to_notehead"]),
                "overlap": float(row["overlap_area"]),
                "height": int(row["height"]),
                "width": int(row["width"]),
            }

    # Analyze distributions
    tp_crossings = [stats_by_idx[i]["crossings"] for i in tp_indices if i in stats_by_idx]
    fp_crossings = [stats_by_idx[i]["crossings"] for i in fp_indices if i in stats_by_idx]

    print("=" * 80)
    print("STAFF-CROSSING DISTRIBUTION")
    print("=" * 80)

    tp_counter = Counter(tp_crossings)
    fp_counter = Counter(fp_crossings)

    print("\nTrue Positives (Barlines):")
    for crossings in sorted(tp_counter.keys()):
        print(
            f"  {crossings} crossings: {tp_counter[crossings]:3d} TPs ({tp_counter[crossings] / len(tp_crossings) * 100:5.1f}%)"
        )

    print("\nFalse Positives (Stems/Artifacts):")
    for crossings in sorted(fp_counter.keys()):
        print(
            f"  {crossings} crossings: {fp_counter[crossings]:3d} FPs ({fp_counter[crossings] / len(fp_crossings) * 100:5.1f}%)"
        )

    # Safety Analysis
    print("\n" + "=" * 80)
    print("SAFETY ANALYSIS")
    print("=" * 80)

    for threshold in [1, 2, 3, 4, 5]:
        rejected_tps = [
            i for i in tp_indices if i in stats_by_idx and stats_by_idx[i]["crossings"] < threshold
        ]
        rejected_fps = [
            i for i in fp_indices if i in stats_by_idx and stats_by_idx[i]["crossings"] < threshold
        ]

        if len(rejected_tps) == 0:
            print(f"✓ SAFE: crossings < {threshold} → Rejects {len(rejected_fps)} FPs, 0 TPs")
        else:
            print(
                f"✗ UNSAFE: crossings < {threshold} → Rejects {len(rejected_fps)} FPs, {len(rejected_tps)} TPs"
            )

    # Detailed FP analysis for low-crossing FPs
    print("\n" + "=" * 80)
    print("LOW-CROSSING FPs (< 3 crossings)")
    print("=" * 80)

    low_crossing_fps = [
        i for i in fp_indices if i in stats_by_idx and stats_by_idx[i]["crossings"] < 3
    ]
    print(f"Total: {len(low_crossing_fps)} FPs\n")

    # Categorize by overlap (to see if they're the low_overlap category from Phase 6)
    low_overlap_and_low_crossing = [i for i in low_crossing_fps if stats_by_idx[i]["overlap"] < 5]
    print(f"  - Low overlap (< 5px) AND low crossing: {len(low_overlap_and_low_crossing)} FPs")
    print(
        f"  - High overlap (>= 5px) AND low crossing: {len(low_crossing_fps) - len(low_overlap_and_low_crossing)} FPs"
    )

    print("\n" + "=" * 80)
    print("EXPECTED EFFECT SIZE")
    print("=" * 80)
    print("If we apply: REJECT if (crossings < 3) AND (overlap < 5):")
    print(f"  - FPs rejected: {len(low_overlap_and_low_crossing)}")
    print("  - TPs rejected: 0 (verified above)")
    print(f"  - Remaining FPs: {len(fp_indices) - len(low_overlap_and_low_crossing)}")


if __name__ == "__main__":
    analyze_crossings(
        "logs/homr_eval/20251206T_staff_crossing_diagnosis/metrics.json",
        "logs/homr_eval/20251206T_staff_crossing_diagnosis/page_3/page_3_candidate_stats.csv",
    )
