#!/usr/bin/env python3
"""Offline validation of Measure Grid Consistency (DP) Heuristic."""

import csv
import sys
import collections
import json
from pathlib import Path

import argparse

# Heuristic Parameters (Defaults)
DEFAULT_W_MIN = 15
DEFAULT_PENALTY_SMALL = -1000.0 # for gap < 4
DEFAULT_PENALTY_MID = -1000.0 # for 10 < gap < w_min
SCORE_DOUBLE_BARLINE = 0.0

def load_metrics(metrics_path, stem):
    """Load ground truth indices."""
    with open(metrics_path, 'r') as f:
        data = json.load(f)
    
    # Assuming page_3 is the first image or matches by name if needed
    # For this task, we know it's page_3
    for img in data["images"]:
        # If we could check filename, do so. Here assume 0.
        tp_indices = set(m["pred_index"] for m in img["matches"])
        soft_indices = set(m["pred_index"] for m in img["soft_matches"])
        return tp_indices, soft_indices
    return set(), set()

    return set(), set()

def compute_gap_stats(data, indices, label):
    """Compute and print gap stats for a subset of candidates."""
    grouped = collections.defaultdict(list)
    for row in data:
        if row["pred_index"] in indices:
            grouped[row["staff_index"]].append(row)
            
    all_gaps = []
    for staff_idx, items in grouped.items():
        items.sort(key=lambda x: x["x_center"])
        for i in range(1, len(items)):
            gap = items[i]["x_center"] - items[i-1]["x_center"]
            all_gaps.append(gap)
            
    if not all_gaps:
        print(f"No {label} gaps found.")
        return
        
    print("\n" + "-"*40)
    print(f"{label} GAP STATISTICS")
    print("-"*40)
    print(f"Count: {len(all_gaps)}")
    print(f"Min: {min(all_gaps):.2f}")
    print(f"Max: {max(all_gaps):.2f}")
    
    ag = sorted(all_gaps)
    mid = len(ag) // 2
    median = (ag[mid] + ag[~mid]) / 2
    mean = sum(ag) / len(ag)
    p10 = ag[int(len(ag) * 0.1)]
    
    print(f"Median: {median:.2f}")
    print(f"Mean: {mean:.2f}")
    print(f"10th Percentile: {p10:.2f}")
    
    # Check specific ranges
    small = len([g for g in all_gaps if g < 4])
    mid_range = len([g for g in all_gaps if 4 <= g <= 15])
    large = len([g for g in all_gaps if g > 15])
    print(f"Range <4: {small} ({small/len(all_gaps):.1%})")
    print(f"Range 4-15: {mid_range} ({mid_range/len(all_gaps):.1%})")
    print(f"Range >15: {large} ({large/len(all_gaps):.1%})")


def solve_dp(candidates, w_min, penalty_small, penalty_mid):
    """
    Find optimal subsequence of candidates.
    candidates: list of dicts (x_center, score, index, ...) sorted by x.
    
    DP[i] = max score ending at i
    Parent[i] = index of predecessor
    """
    n = len(candidates)
    if n == 0:
        return []

    dp = [-float('inf')] * n
    parent = [-1] * n
    
    # Initialization
    # Any node can be a start node (concepts of left-margin gap?)
    # For now, base score is just NodeScore.
    for i in range(n):
        dp[i] = candidates[i]["score"]

    # DP
    for i in range(n):
        for j in range(i):
            gap = candidates[i]["x_center"] - candidates[j]["x_center"]
            
            edge_score = 0.0
            
            if gap < 4:
                # Duplicate range
                edge_score = penalty_small
            elif 4 <= gap <= 10:
                # Double Barline (Allowed)
                edge_score = SCORE_DOUBLE_BARLINE
            elif 10 < gap < w_min:
                # Intermediate (Mid) range
                edge_score = penalty_mid
            else:
                 # Valid Measure
                 edge_score = 0.0
            
            # Transition
            if dp[j] + edge_score + candidates[i]["score"] > dp[i]:
                dp[i] = dp[j] + edge_score + candidates[i]["score"]
                parent[i] = j
                
    # Find max ending
    if not dp:
        return []
        
    best_score = -float('inf')
    best_end_idx = -1
    
    for i in range(n):
        if dp[i] > best_score:
            best_score = dp[i]
            best_end_idx = i
            
    # Backtrack
    path = []
    curr = best_end_idx
    while curr != -1:
        path.append(candidates[curr]["pred_index"])
        curr = parent[curr]
        
    return set(path)

def analyze_measure_grid(csv_path, metrics_path, w_min, penalty_small, penalty_mid, stem="page_3"):
    # Load Candidates
    data = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["score"] = float(row["score"])
            row["x_center"] = float(row["x_center"])
            row["pred_index"] = int(row["pred_index"])
            row["staff_index"] = int(row["staff_index"])
            data.append(row)
            
    # Load Metrics
    tp_indices, soft_indices = load_metrics(metrics_path, stem)
    print(f"Loaded Metrics: {len(tp_indices)} TPs, {len(soft_indices)} Softs.")
    
    # Analysis 1: TP Gaps
    compute_gap_stats(data, tp_indices, "TP (Ground Truth)")
    
    # Analysis 2: FP Gaps (FP to nearest neighbor?)
    # Just compute gaps of ALL candidates to see the overall density
    compute_gap_stats(data, set(d["pred_index"] for d in data), "ALL CANDIDATES")
    
    # Group by Staff
    grouped = collections.defaultdict(list)
    for row in data:
        grouped[row["staff_index"]].append(row)
        
    kept_indices = set()
    
    # Run DP per Staff
    for staff_idx, candidates in grouped.items():
        candidates.sort(key=lambda x: x["x_center"])
        staff_kept = solve_dp(candidates, w_min, penalty_small, penalty_mid)
        kept_indices.update(staff_kept)
        
    # Analysis
    total_candidates = len(data)
    kept_count = len(kept_indices)
    rejected_count = total_candidates - kept_count
    
    tp_kept = len(tp_indices.intersection(kept_indices))
    tp_rejected = len(tp_indices) - tp_kept
    
    soft_kept = len(soft_indices.intersection(kept_indices))
    soft_rejected = len(soft_indices) - soft_kept
    
    # FPs = All - TPs - Softs
    all_indices = set(d["pred_index"] for d in data)
    fp_indices = all_indices - tp_indices - soft_indices
    fp_kept = len(fp_indices.intersection(kept_indices))
    fp_rejected = len(fp_indices) - fp_kept
    
    print("\n" + "="*60)
    print(f"MEASURE GRID DIAGNOSIS")
    print(f"W_MIN={w_min}, P_SMALL={penalty_small}, P_MID={penalty_mid}")
    print("="*60)
    print(f"Total Candidates: {total_candidates}")
    print(f"KEPT: {kept_count}")
    print(f"REJECTED: {rejected_count}")
    
    print("\nBreakdown:")
    print(f"  TPs: {tp_kept} Kept / {tp_rejected} Rejected (Target: 0 Rejected)")
    print(f"  FPs: {fp_kept} Kept / {fp_rejected} Rejected (Target: Max Rejected)")
    print(f"  Soft: {soft_kept} Kept / {soft_rejected} Rejected")

    print("\nSafety Check:")
    if tp_rejected == 0:
        print("PASS: No True Positives were rejected.")
    else:
        print(f"FAIL: {tp_rejected} True Positives rejected.")
        
    print("\nEffectiveness:")
    print(f"FP Reduction: {fp_rejected} / {len(fp_indices)} ({fp_rejected/len(fp_indices):.1%})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--w-min", type=float, default=DEFAULT_W_MIN, help="Min measure width")
    parser.add_argument("--penalty-small", type=float, default=DEFAULT_PENALTY_SMALL, help="Penalty for gap < 4")
    parser.add_argument("--penalty-mid", type=float, default=DEFAULT_PENALTY_MID, help="Penalty for 10 < gap < w_min")
    args = parser.parse_args()

    analyze_measure_grid(
        "logs/homr_eval/20251206T_homr_measure_grid_diagnosis/page_3/page_3_measure_grid_candidates.csv",
        "logs/homr_eval/20251206T_homr_measure_grid_diagnosis/metrics.json",
        args.w_min,
        args.penalty_small,
        args.penalty_mid
    )
