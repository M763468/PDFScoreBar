
import json
import numpy as np
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats-json", required=True, help="Path to candidate_statistics.json")
    args = parser.parse_args()

    with open(args.stats_json, 'r') as f:
        stats_data = json.load(f)

    # Partition data
    tp_kept = [d for d in stats_data if d["classification"] == "TP" and not d["rejected_by_geom"]]
    tp_rejected = [d for d in stats_data if d["classification"] == "TP" and d["rejected_by_geom"]]
    fp_kept = [d for d in stats_data if d["classification"] == "FP" and not d["rejected_by_geom"]]
    fp_rejected = [d for d in stats_data if d["classification"] == "FP" and d["rejected_by_geom"]]
    
    # Also get all FPs that were passed to the geom filter
    all_fp_before_geom = [d for d in stats_data if d["classification"] == "FP"]

    groups = {
        "TP (Kept)": tp_kept,
        "TP (Rejected -> FN)": tp_rejected,
        "FP (Kept)": fp_kept,
        "FP (Rejected)": fp_rejected,
        "FP (All Pre-Geom)": all_fp_before_geom
    }
    
    metrics = ["width", "height", "area", "notehead_top_overlap", "notehead_bot_overlap", "stems_rest_top_overlap", "stems_rest_bot_overlap", "combined_top_overlap", "combined_bot_overlap"]
    quantiles = [0, 10, 25, 50, 75, 90, 100]

    print("--- Descriptive Statistics for Candidate BBoxes ---")

    for group_name, group_data in groups.items():
        if not group_data:
            print(f"\n--- {group_name} (count=0) ---")
            continue
            
        print(f"\n--- {group_name} (count={len(group_data)}) ---")
        
        header = f"| {'Metric':<25} |" + " ".join([f"p{q:<3} |" for q in quantiles])
        print(header)
        print("|" + "-" * (len(header) - 2) + "|")

        for metric in metrics:
            # Check if metric exists for this group (geom metrics only exist for rejected)
            if not all(metric in d for d in group_data):
                continue

            values = [d.get(metric, 0) for d in group_data]
            percentiles = np.percentile(values, quantiles)
            
            row_str = f"| {metric:<25} |"
            for p_val in percentiles:
                row_str += f" {p_val:<5.1f} |"
            print(row_str)

if __name__ == "__main__":
    main()
