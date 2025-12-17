
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

def analyze_bbox_pixel_context(image, bbox):
    """
    Analyzes pixel context of a given bounding box in the image.
    Returns calculated metrics like mean ink density, top/bottom ink density.
    """
    x1, y1, x2, y2 = map(int, bbox)
    
    pad = 10 # Context padding
    h_img, w_img = image.shape[:2]
    cx1 = max(0, x1 - pad)
    cy1 = max(0, y1 - pad)
    cx2 = min(w_img, x2 + pad)
    cy2 = min(h_img, y2 + pad)
    
    crop = image[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        return {"bin_mean": 0.0, "top_ink_density": 0.0, "bottom_ink_density": 0.0}

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Bbox's mean ink density (only the actual bbox area, not the padded crop)
    bbox_in_crop_x1 = x1 - cx1
    bbox_in_crop_y1 = y1 - cy1
    bbox_in_crop_x2 = x2 - cx1
    bbox_in_crop_y2 = y2 - cy1

    # Ensure bbox coordinates are within crop bounds
    bbox_in_crop_x1 = max(0, bbox_in_crop_x1)
    bbox_in_crop_y1 = max(0, bbox_in_crop_y1)
    bbox_in_crop_x2 = min(crop.shape[1], bbox_in_crop_x2)
    bbox_in_crop_y2 = min(crop.shape[0], bbox_in_crop_y2)

    bbox_binary_region = binary[bbox_in_crop_y1:bbox_in_crop_y2, bbox_in_crop_x1:bbox_in_crop_x2]
    bin_mean_ink_density = np.sum(bbox_binary_region) / (255.0 * bbox_binary_region.size) if bbox_binary_region.size > 0 else 0.0

    # Ink Density at Top/Bottom Corners (Blob detection heuristic)
    corner_size = 3 # 3x3 pixel square
    
    def get_corner_ink_density(bin_img, corner_x, corner_y, size):
        x_start = max(0, corner_x)
        y_start = max(0, corner_y)
        x_end = min(bin_img.shape[1], corner_x + size)
        y_end = min(bin_img.shape[0], corner_y + size)
        
        if x_end <= x_start or y_end <= y_start:
            return 0.0
        
        corner_region = bin_img[y_start:y_end, x_start:x_end]
        return np.sum(corner_region) / (255.0 * corner_region.size) if corner_region.size > 0 else 0.0

    top_left_density = get_corner_ink_density(binary, x1 - cx1, y1 - cy1, corner_size)
    top_right_density = get_corner_ink_density(binary, x2 - cx1 - corner_size, y1 - cy1, corner_size)
    bottom_left_density = get_corner_ink_density(binary, x1 - cx1, y2 - cy1 - corner_size, corner_size)
    bottom_right_density = get_corner_ink_density(binary, x2 - cx1 - corner_size, y2 - cy1 - corner_size, corner_size)

    top_ink_density = (top_left_density + top_right_density) / 2.0
    bottom_ink_density = (bottom_left_density + bottom_right_density) / 2.0
    
    return {
        "bin_mean": float(bin_mean_ink_density),
        "top_ink_density": float(top_ink_density),
        "bottom_ink_density": float(bottom_ink_density)
    }

def get_iou(boxA, boxB):
    """
    Calculates Intersection over Union for two bounding boxes.
    Assumes box format [x1, y1, x2, y2].
    """
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    iou = interArea / float(boxAArea + boxBArea - interArea)
    return iou

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

def estimate_staff_space(rows, preds_list):
    """
    Estimate staff space from row spacing.

    Uses median vertical distance between consecutive row medians and divides by 5.
    This mirrors the logic used in `tolerance_sweep.py`.
    """
    if len(rows) < 2:
        return 20.0  # Fallback

    row_medians = []
    for row_id in sorted(rows.keys()):
        indices = rows[row_id]
        y_centers = [(preds_list[i][1] + preds_list[i][3]) / 2 for i in indices]
        row_medians.append(float(np.median(y_centers)))

    gaps = [row_medians[i + 1] - row_medians[i] for i in range(len(row_medians) - 1)]
    median_gap = float(np.median(gaps)) if gaps else 100.0
    return median_gap / 5.0

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cluster-max-dist", type=float, default=25.0)
    parser.add_argument("--min-row-count", type=int, default=3)

    # Tolerance configuration:
    # Default: ratio-based tolerance with ratio 0.35 (recommended 0.3-0.4).
    parser.add_argument("--use-ratio-tolerance", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--tol-ratio", type=float, default=0.35)
    parser.add_argument("--staff-space", type=float, default=None)
    parser.add_argument("--tol-top-px", type=float, default=6.0)
    parser.add_argument("--tol-bottom-px", type=float, default=6.0)
    # New pixel-based filter arguments
    parser.add_argument("--min-bbox-ink-density", type=float, default=0.0, help="Minimum mean ink density (0-1) for a bbox to be considered valid.")
    parser.add_argument("--max-end-ink-density", type=float, default=1.0, help="Maximum ink density (0-1) at top/bottom corners for a bbox to be considered a pure barline (to filter noteheads).")
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
        max_distance=args.cluster_max_dist,
        min_cluster_size=args.min_row_count,
    )
    
    print(f"Clustering found {len(rows)} row clusters. Noise points: {len(noise_indices)}.")

    staff_space = args.staff_space if args.staff_space is not None else estimate_staff_space(rows, preds_list)
    if args.use_ratio_tolerance:
        tol_top = args.tol_ratio * staff_space
        tol_bottom = args.tol_ratio * staff_space
        tol_mode = "ratio"
    else:
        tol_top = args.tol_top_px
        tol_bottom = args.tol_bottom_px
        tol_mode = "absolute"

    print(f"Estimated staff_space: {staff_space:.2f}px | tol_mode={tol_mode} | tol_top={tol_top:.2f}px tol_bottom={tol_bottom:.2f}px")
    
    # 3. Filter Per Row
    accepted_indices = set()
    # img_vis for row filter viz is not used if pixel filters are active, so commenting out
    # img_vis = cv2.imread(args.image) 
    
    for row_id, indices in rows.items():
        if len(indices) < args.min_row_count:
            continue
            
        # Collect coords
        tops = [preds_list[i][1] for i in indices]
        bottoms = [preds_list[i][3] for i in indices]
        
        # Calculate Reference (Median)
        ref_top = np.median(tops)
        ref_bottom = np.median(bottoms)
        
        for i in indices:
            box = preds_list[i]
            x1, y1, x2, y2 = map(int, box)
            
            # Check Consistency
            top_dev = abs(y1 - ref_top)
            bot_dev = abs(y2 - ref_bottom)
            
            if top_dev <= tol_top and bot_dev <= tol_bottom:
                accepted_indices.add(i)
                
    # 4. Filter Per Row - populate row_filtered_preds
    row_filtered_preds = [preds_list[i] for i in sorted(list(accepted_indices))]
    
    # 5. Apply Pixel Context Filters
    pixel_filtered_preds = []
    filtered_by_min_ink_density = 0
    filtered_by_max_end_ink_density = 0
    
    # Load image for pixel analysis
    img = cv2.imread(args.image)
    if img is None:
        print(f"Error: Could not load image from {args.image} for pixel context analysis. Skipping pixel filters.")
        pixel_filtered_preds = row_filtered_preds # Skip pixel filters if image not loaded
    else:
        print(f"\nApplying pixel context filters ({len(row_filtered_preds)} candidates from row filtering)...")
        
        for pred_bbox in row_filtered_preds:
            context_metrics = analyze_bbox_pixel_context(img, pred_bbox)
            
            bin_mean = context_metrics["bin_mean"]
            top_ink = context_metrics["top_ink_density"]
            bottom_ink = context_metrics["bottom_ink_density"]
            
            pass_min_ink_density = (bin_mean >= args.min_bbox_ink_density)
            pass_max_end_ink_density = not (top_ink > args.max_end_ink_density or bottom_ink > args.max_end_ink_density)
            
            # Actual filtering logic
            if not pass_min_ink_density:
                filtered_by_min_ink_density += 1
                continue
            
            if not pass_max_end_ink_density:
                filtered_by_max_end_ink_density += 1
                continue
            
            pixel_filtered_preds.append(pred_bbox)

    final_preds = pixel_filtered_preds
    
    old_metrics = evaluate_detections(preds_list, gt_boxes)
    # The row_filtered_preds are the ones after step 3 in my mental model
    row_filter_metrics = evaluate_detections(row_filtered_preds, gt_boxes) 
    # new_metrics should be the final_preds
    new_metrics = evaluate_detections(final_preds, gt_boxes)
    
    print("\n--- Results ---")
    print(f"Original (raw detections): TP={old_metrics['TP']}, FP={old_metrics['FP']}, FN={old_metrics['FN']}")
    print(f"After Row Filter: TP={row_filter_metrics['TP']}, FP={row_filter_metrics['FP']}, FN={row_filter_metrics['FN']}")
    print(f"Final Filtered (Pixel Context): TP={new_metrics['TP']}, FP={new_metrics['FP']}, FN={new_metrics['FN']}")
    
    # Save metrics
    res = {
        "config": {
            "CLUSTER_MAX_DIST": args.cluster_max_dist,
            "MIN_ROW_COUNT": args.min_row_count,
            "USE_RATIO_TOLERANCE": args.use_ratio_tolerance,
            "TOLERANCE_RATIO": args.tol_ratio,
            "STAFF_SPACE_PX": staff_space,
            "TOL_TOP_PX": tol_top,
            "TOL_BOTTOM_PX": tol_bottom,
            "MIN_BBOX_INK_DENSITY": args.min_bbox_ink_density,
            "MAX_END_INK_DENSITY": args.max_end_ink_density,
        },
        "original": old_metrics,
        "row_filtered": row_filter_metrics, # New entry
        "filtered": new_metrics, # This is now after pixel filters
        "filtered_counts": { # New entry
            "by_min_ink_density": filtered_by_min_ink_density,
            "by_max_end_ink_density": filtered_by_max_end_ink_density,
        },
        "rows_found": len(rows),
        "noise_count": len(noise_indices)
    }
    with open(os.path.join(args.output, "metrics.json"), 'w') as f:
        json.dump(res, f, indent=2)
    
    print(f"\nSaved results to {args.output}")

if __name__ == "__main__":
    main()
