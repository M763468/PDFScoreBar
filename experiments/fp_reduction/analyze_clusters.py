# NOTE (2025-12 repo restructure): This script may still assume pre-restructure paths (src/tools, tools/fp_reduction). Adjust imports if reusing.
#!/usr/bin/env python3
"""Analyze cluster resolution dry-run results."""

import csv
import json
from collections import Counter


def analyze_clusters(metrics_path, clusters_path):
    # Load metrics for Ground Truth
    with open(metrics_path, "r") as f:
        metrics = json.load(f)

    page_metrics = metrics["images"][0]
    tp_indices = set(m["pred_index"] for m in page_metrics["matches"])
    soft_indices = set(m["pred_index"] for m in page_metrics["soft_matches"])

    print(f"Metrics Loaded: {len(tp_indices)} TPs, {len(soft_indices)} Soft Matches.")

    # Load clusters logic
    removed_tps = []
    removed_fps = []
    removed_soft = []

    reasons = Counter()

    with open(clusters_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["pred_index"])
            decision = row["decision"]
            reason = row["reason"]

            if decision == "REMOVE":
                reasons[reason] += 1

                if idx in tp_indices:
                    removed_tps.append((idx, reason))
                elif idx in soft_indices:
                    removed_soft.append((idx, reason))
                else:
                    removed_fps.append((idx, reason))

    print("\n" + "=" * 60)
    print("CLUSTER RESOLUTION DRY RUN RESULTS")
    print("=" * 60)
    print(
        f"Total Candidates Marked REMOVE: {len(removed_tps) + len(removed_fps) + len(removed_soft)}"
    )
    print(f"  - FPs Removed: {len(removed_fps)} (Target: 30)")
    print(f"  - TPs Removed: {len(removed_tps)} (Risk!)")
    print(f"  - Soft Removed: {len(removed_soft)} (Likely duplicates)")

    print("\nRemoval Reasons breakdown:")
    for r, count in reasons.items():
        print(f"  - {r}: {count}")

    print("\n" + "=" * 60)
    print("SAFETY ANALYSIS")
    print("=" * 60)

    if len(removed_tps) == 0:
        print("PASS: No True Positives were removed.")
    else:
        print(f"FAIL: {len(removed_tps)} True Positives would be removed!")
        for idx, reason in removed_tps:
            print(f"  TP #{idx} removed due to {reason}")

    print("\nIMPACT ANALYSIS")
    print(f"Potential FP Reduction: {len(removed_fps)} / 30 ({len(removed_fps) / 30:.1%})")


if __name__ == "__main__":
    analyze_clusters(
        "logs/homr_eval/20251206T_homr_cluster_dryrun/metrics.json",
        "logs/homr_eval/20251206T_homr_cluster_dryrun/page_3/page_3_candidate_clusters.csv",
    )
