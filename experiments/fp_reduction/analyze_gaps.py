# NOTE (2025-12 repo restructure): This script may still assume pre-restructure paths (src/tools, tools/fp_reduction). Adjust imports if reusing.
#!/usr/bin/env python3
"""Analyze gap distributions for TPs vs FPs."""

import csv
import json


def analyze_gaps(metrics_path, gaps_path):
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

    # Load gaps
    gaps_by_idx = {}
    with open(gaps_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["pred_index"])
            gaps_by_idx[idx] = {
                "prev": float(row["gap_to_prev"]),
                "next": float(row["gap_to_next"]),
                "width": float(row["width"]),
                "height": float(row["height"]),
                "sys": int(row["system_index"]),
                "staff": int(row["staff_index"]),
            }

    # Analyze
    tp_min_gaps = []
    fp_min_gaps = []

    for idx in tp_indices:
        if idx not in gaps_by_idx:
            continue
        g = gaps_by_idx[idx]
        dists = []
        if g["prev"] > 0:
            dists.append(g["prev"])
        if g["next"] > 0:
            dists.append(g["next"])

        if dists:
            tp_min_gaps.append((min(dists), idx))
        else:
            tp_min_gaps.append((9999.0, idx))  # Isolated in staff

    for idx in fp_indices:
        if idx not in gaps_by_idx:
            continue
        g = gaps_by_idx[idx]
        dists = []
        if g["prev"] > 0:
            dists.append(g["prev"])
        if g["next"] > 0:
            dists.append(g["next"])

        if dists:
            fp_min_gaps.append((min(dists), idx))
        else:
            fp_min_gaps.append((9999.0, idx))

    # Sort
    tp_min_gaps.sort()
    fp_min_gaps.sort()

    print("=" * 80)
    print("TP Gap Analysis (Valid Measures)")
    print("=" * 80)
    print(f"Min TP Gap: {tp_min_gaps[0][0]:.1f} px (Idx {tp_min_gaps[0][1]})")

    print("\nTPs with gap < 15px:")
    for dist, idx in tp_min_gaps:
        if dist < 15:
            print(f"  TP #{idx}: {dist:.1f} px")
        else:
            break

    print("\n" + "=" * 80)
    print("FP Gap Analysis (Clutter)")
    print("=" * 80)
    print(f"Min FP Gap: {fp_min_gaps[0][0]:.1f} px")

    print("\nFPs with gap < 15px:")
    count = 0
    for dist, idx in fp_min_gaps:
        if dist < 15:
            print(f"  FP #{idx}: {dist:.1f} px")
            count += 1
        else:
            break
    print(f"Total FPs < 15px: {count}")

    # Safety Check
    print("\n" + "=" * 80)
    print("SAFETY THRESHOLD ANALYSIS")
    print("=" * 80)

    for thresh in [2, 5, 8, 10, 12, 15, 20]:
        tps_rejected = [i for d, i in tp_min_gaps if d < thresh]
        fps_rejected = [i for d, i in fp_min_gaps if d < thresh]

        status = "UNSAFE" if tps_rejected else "SAFE"
        print(
            f"Threshold < {thresh:2d} px: Rejects {len(fps_rejected):2d} FPs, {len(tps_rejected):2d} TPs --> {status}"
        )


if __name__ == "__main__":
    analyze_gaps(
        "logs/homr_eval/20251206T_homr_gap_diagnosis/metrics.json",
        "logs/homr_eval/20251206T_homr_gap_diagnosis/page_3/page_3_candidate_gaps.csv",
    )
