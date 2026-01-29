# NOTE (2025-12 repo restructure): This script may still assume pre-restructure paths (src/tools, tools/fp_reduction). Adjust imports if reusing.

import csv
import json
import sys

import numpy as np


def analyze(metrics_path, stats_path):
    with open(metrics_path, "r") as f:
        metrics = json.load(f)

    # Extract TP and FP indices for page_3 (assuming single image run or finding page_3)
    # The JSON structure has "images": [ ... ]
    page_metrics = next(m for m in metrics["images"] if "page_3" in m["image"])

    tp_indices = set(m["pred_index"] for m in page_metrics["matches"])
    fp_indices = (
        set(page_metrics["false_positives_indices"])
        if "false_positives_indices" in page_metrics
        else set()
    )
    # If key missing (it was "false_positive_indices" in python but typically dumped), let's check matches.
    # Actually metrics.json structure: "matches" has `pred_index`.
    # FPs are those not in matches?
    # Actually `homr_evaluator.py` writes `false_positive_indices` into `extra` or implicitly...
    # Wait, the tool output for metrics.json showed `false_positives` count but not the list in the summary.
    # BUT `matches` list is there. Any index in CSV not in `matches` (and not soft match) is FP.

    matched_indices = set(m["pred_index"] for m in page_metrics["matches"])
    soft_matched_indices = set(m["pred_index"] for m in page_metrics["soft_matches"])

    print(f"TP Count: {len(matched_indices)}")
    print(f"Soft Match Count: {len(soft_matched_indices)}")

    tp_stats = []
    fp_stats = []
    soft_stats = []

    with open(stats_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["pred_index"])
            dist = float(row["min_dist_to_notehead"])
            width = float(row["width"])
            height = float(row["height"])
            overlap = float(row["overlap_area"])

            item = {"idx": idx, "dist": dist, "width": width, "height": height, "overlap": overlap}

            if idx in matched_indices:
                tp_stats.append(item)
            elif idx in soft_matched_indices:
                soft_stats.append(item)
            else:
                fp_stats.append(item)

    print(f"Loaded {len(tp_stats)} TPs, {len(soft_stats)} Softs, {len(fp_stats)} FPs from CSV.")

    # Analysis: Proximity
    THRESH_DIST = 5.0

    tp_close = [x for x in tp_stats if x["dist"] < THRESH_DIST]
    fp_close = [x for x in fp_stats if x["dist"] < THRESH_DIST]

    print(f"\n--- Proximity Analysis (Dist < {THRESH_DIST}px) ---")
    print(
        f"TPs close to notehead: {len(tp_close)} / {len(tp_stats)} ({len(tp_close) / len(tp_stats) * 100:.1f}%)"
    )
    print(
        f"FPs close to notehead: {len(fp_close)} / {len(fp_stats)} ({len(fp_close) / len(fp_stats) * 100:.1f}%)"
    )

    print("\n--- Feature Distribution for Close Candidates ---")

    def print_dist(name, items, key):
        if not items:
            print(f"{name}: No items")
            return
        vals = [x[key] for x in items]
        print(f"{name} {key}: min={min(vals):.1f}, max={max(vals):.1f}, mean={np.mean(vals):.1f}")
        # Percentiles
        p = np.percentile(vals, [0, 25, 50, 75, 100])
        print(f"  Quartiles: {p}")

    print_dist("TP (Close)", tp_close, "height")
    print_dist("FP (Close)", fp_close, "height")
    print_dist("TP (Close)", tp_close, "width")
    print_dist("FP (Close)", fp_close, "width")
    print_dist("TP (Close)", tp_close, "overlap")
    print_dist("FP (Close)", fp_close, "overlap")

    # Designing Safety Filter
    # We want to Reject if (Close) AND (width < W_thresh) AND (height < H_thresh) AND (overlap > O_thresh)

    print("\n--- Proposed Filter Simulation ---")

    # Try different thresholds
    for h_thresh in [20, 22, 24, 25, 26, 28, 30]:
        for w_thresh in [2, 3, 4, 5]:
            for o_thresh in [0, 1, 5, 10]:
                # Rule: REJECT if dist < 5 AND height < h_thresh AND width < w_thresh AND overlap >= o_thresh
                rejected_tps = [
                    x
                    for x in tp_close
                    if x["height"] < h_thresh and x["width"] < w_thresh and x["overlap"] >= o_thresh
                ]
                rejected_fps = [
                    x
                    for x in fp_close
                    if x["height"] < h_thresh and x["width"] < w_thresh and x["overlap"] >= o_thresh
                ]

                if len(rejected_tps) == 0 and len(rejected_fps) > 0:
                    print(
                        f"SAFE FILTER: H < {h_thresh} AND W < {w_thresh} AND Overlap >= {o_thresh} -> Rejects {len(rejected_fps)} FPs"
                    )


if __name__ == "__main__":
    if len(sys.argv) > 2:
        metrics_file = sys.argv[1]
        stats_file = sys.argv[2]
    else:
        # Default paths (relative to repo root)
        metrics_file = "logs/homr_eval/20251206T_homr_diagnosis/metrics.json"
        stats_file = "logs/homr_eval/20251206T_homr_diagnosis/page_3/page_3_candidate_stats.csv"

    analyze(metrics_file, stats_file)
