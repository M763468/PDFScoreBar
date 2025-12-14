
# Script: analyze_staff_consistency.py
# Purpose: Filter false positive barlines using DBSCAN clustering (Row-Based).
# Environment: 'homr_eval_gpu' container.

import argparse
import json
import os
import cv2
import numpy as np
import sys

# Ensure workspace root is in path
sys.path.insert(0, '/workspace')

try:
    from experiments.fp_reduction.unified_metric import evaluate_detections
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from unified_metric import evaluate_detections

def cluster_by_y_distance(y_centers, max_distance=25, min_cluster_size=3):
    """
    Simple clustering: group points within max_distance of each other.
    Returns dict of {cluster_id: [indices]}, and list of noise indices.
    """
    # Sort by Y
    sorted_indices = np.argsort(y_centers)
    sorted_y = y_centers[sorted_indices]
    
    clusters = []
    current_cluster = [sorted_indices[0]]
    
    for i in range(1, len(sorted_y)):
        if sorted_y[i] - sorted_y[i-1] <= max_distance:
            current_cluster.append(sorted_indices[i])
        else:
            clusters.append(current_cluster)
            current_cluster = [sorted_indices[i]]
    clusters.append(current_cluster)
    
    # Filter by size and separate noise
    valid_clusters = {}
    noise = []
    cluster_id = 0
    
    for cluster in clusters:
        if len(cluster) >= min_cluster_size:
            valid_clusters[cluster_id] = cluster
            cluster_id += 1
        else:
            noise.extend(cluster)
    
    return valid_clusters, noise

# --- CONFIGURATION (Tunable Constants) ---
CONFIG = {
    "CLUSTER_MAX_DIST": 25,  # Max Y-distance between barlines in same row (pixels)
    "TOL_TOP_PX": 15,        # Max deviation from row median top
    "TOL_BOTTOM_PX": 15,     # Max deviation from row median bottom
    "MIN_ROW_COUNT": 3,      # Min barlines to consider a valid row
}

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()

def load_json(path):
    with open(path, 'r') as f:
        data = json.load(f)
    raw = data["predictions"] if isinstance(data, dict) and "predictions" in data else data
    preds = []
    for item in raw:
        if isinstance(item, list): 
            preds.append(item)
        elif isinstance(item, dict): 
            preds.append(item.get("orig_bbox", item.get("bbox", item.get("pred_bbox"))))
    return preds

def load_gt(path):
    with open(path, 'r') as f:
        data = json.load(f)
    if isinstance(data, list) and len(data) > 0 and "barline_location" in data[0]:
        return [x["barline_location"] for x in data]
    return data

def main():
    args = parse_args()
    os.makedirs(args.output, exist_ok=True)
    
    # 1. Load Data
    preds_list = load_json(args.json)
    gt_boxes = load_gt(args.gt)
    print(f"Loaded {len(preds_list)} barlines, {len(gt_boxes)} GT.")

    # 2. Cluster Barlines by Y-position
    y_centers = np.array([(box[1] + box[3]) / 2 for box in preds_list])
    
    rows, noise_indices = cluster_by_y_distance(
        y_centers, 
        max_distance=CONFIG["CLUSTER_MAX_DIST"], 
        min_cluster_size=CONFIG["MIN_ROW_COUNT"]
    )
    
    print(f"Clustering found {len(rows)} row clusters. Noise points: {len(noise_indices)}.")
    
    # 3. Filter Per Row
    accepted_indices = set()
    img_vis = cv2.imread(args.image)
    
    for row_id, indices in rows.items():
        if len(indices) < CONFIG["MIN_ROW_COUNT"]:
            continue
            
        # Collect coords
        tops = [preds_list[i][1] for i in indices]
        bottoms = [preds_list[i][3] for i in indices]
        x_coords = [(preds_list[i][0] + preds_list[i][2])/2 for i in indices]
        
        # Calculate Reference (Median)
        ref_top = np.median(tops)
        ref_bottom = np.median(bottoms)
        min_x = min(x_coords) - 50
        max_x = max(x_coords) + 50
        
        # Visualize Row Guidelines (Yellow)
        cv2.line(img_vis, (int(min_x), int(ref_top)), (int(max_x), int(ref_top)), (0, 255, 255), 2)
        cv2.line(img_vis, (int(min_x), int(ref_bottom)), (int(max_x), int(ref_bottom)), (0, 255, 255), 2)
        cv2.putText(img_vis, f"Row {row_id}", (int(min_x), int(ref_top)-5), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        for i in indices:
            box = preds_list[i]
            x1, y1, x2, y2 = map(int, box)
            
            # Check Consistency
            top_dev = abs(y1 - ref_top)
            bot_dev = abs(y2 - ref_bottom)
            
            if top_dev <= CONFIG["TOL_TOP_PX"] and bot_dev <= CONFIG["TOL_BOTTOM_PX"]:
                accepted_indices.add(i)
                cv2.rectangle(img_vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
            else:
                cv2.rectangle(img_vis, (x1, y1), (x2, y2), (0, 0, 255), 2)
                
    # Draw noise/unassigned as Red
    for i in noise_indices:
        x1, y1, x2, y2 = map(int, preds_list[i])
        cv2.rectangle(img_vis, (x1, y1), (x2, y2), (0, 0, 255), 2)

    # 4. Evaluate
    accepted_preds = [preds_list[i] for i in sorted(list(accepted_indices))]
    
    old_metrics = evaluate_detections(preds_list, gt_boxes)
    new_metrics = evaluate_detections(accepted_preds, gt_boxes)
    
    print("\n--- Results ---")
    print(f"Original: TP={old_metrics['TP']}, FP={old_metrics['FP']}, FN={old_metrics['FN']}")
    print(f"Filtered: TP={new_metrics['TP']}, FP={new_metrics['FP']}, FN={new_metrics['FN']}")
    
    cv2.imwrite(os.path.join(args.output, "row_filter_debug.jpg"), img_vis)
    
    # Save metrics
    res = {
        "config": CONFIG,
        "original": old_metrics,
        "filtered": new_metrics,
        "rows_found": len(rows),
        "noise_count": len(noise_indices)
    }
    with open(os.path.join(args.output, "metrics.json"), 'w') as f:
        json.dump(res, f, indent=2)
    
    print(f"\nSaved results to {args.output}")

if __name__ == "__main__":
    main()
