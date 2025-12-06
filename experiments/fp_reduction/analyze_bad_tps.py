# NOTE (2025-12 repo restructure): This script may still assume pre-restructure paths (src/tools, tools/fp_reduction). Adjust imports if reusing.
#!/usr/bin/env python3
"""Analyze TPs rejected by Heuristic 2."""

import json
import csv
import sys

def analyze_bad_tps(metrics_path, stats_path):
    # Load metrics (from diagnosis run or baseline, just need TP indices)
    with open(metrics_path, 'r') as f:
        metrics = json.load(f)
    
    page_metrics = metrics["images"][0]
    tp_indices = set(m["pred_index"] for m in page_metrics["matches"])
    
    # Load stats
    bad_tps = []
    
    with open(stats_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["pred_index"])
            if idx not in tp_indices:
                continue
                
            dist = float(row["min_dist_to_notehead"])
            overlap = float(row["overlap_area"])
            crossings = int(row["num_staff_crossings"])
            
            # The rejection logic was:
            # Proximal (Dist < 5) AND Overlap < 5 AND Crossings < 3
            
            if dist < 5.0 and overlap < 5.0 and crossings < 3:
                bad_tps.append({
                    "idx": idx,
                    "dist": dist,
                    "overlap": overlap,
                    "crossings": crossings,
                    "height": int(row["height"]),
                    "width": int(row["width"])
                })
    
    print(f"Found {len(bad_tps)} TPs that satisfy Rejection Criteria:")
    for tp in bad_tps:
        print(f"TP #{tp['idx']:3d}: Dist={tp['dist']:.1f} Overlap={tp['overlap']:.1f} Crossings={tp['crossings']} H={tp['height']}")

    print("\nConclusion: TPs often have low overlap AND low crossings.")

if __name__ == "__main__":
    analyze_bad_tps(
        "logs/homr_eval/20251206T_staff_crossing_diagnosis/metrics.json",
        "logs/homr_eval/20251206T_staff_crossing_diagnosis/page_3/page_3_candidate_stats.csv"
    )
