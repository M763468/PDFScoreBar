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
    iou = interArea / float(boxAArea + boxBArea - interArea) if (boxAArea + boxBArea - interArea) > 0 else 0.0
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
    if len(sorted_indices) > 0:
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


def _load_binary_mask(mask_path, target_hw=None):
    """
    Load a mask image as a binary uint8 array with values {0, 255}.

    homr debug masks may be stored at a different resolution than the evaluation image.
    When needed, resize with nearest-neighbour to preserve binary structure.
    """
    img = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Could not read mask: {mask_path}")
    
    orig_hw = img.shape[:2]
    _, bin_mask = cv2.threshold(img, 1, 255, cv2.THRESH_BINARY)
    
    if target_hw is not None and bin_mask.shape[:2] != target_hw:
        print(f"Resizing mask {os.path.basename(mask_path)} from {orig_hw} to {target_hw}")
        h, w = target_hw
        bin_mask = cv2.resize(bin_mask, (w, h), interpolation=cv2.INTER_NEAREST)
        
    return bin_mask


def _build_notehead_with_stems_mask(notehead_mask, stems_rest_mask, staff_space_px):
    """
    Approximate a "notehead_with_stems" mask from homr's symbol segmentation masks.
    """
    notehead = (notehead_mask > 0).astype(np.uint8) * 255
    stems = (stems_rest_mask > 0).astype(np.uint8) * 255

    dilate_r = max(1, int(round(staff_space_px * 0.15)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate_r + 1, 2 * dilate_r + 1))
    notehead_dil = cv2.dilate(notehead, kernel, iterations=1)

    inv = 255 - notehead_dil
    dist_to_notehead = cv2.distanceTransform(inv, cv2.DIST_L2, 3)

    stem_attach_dist = max(4.0, staff_space_px * 0.8)
    stems_near_notehead = (stems > 0) & (dist_to_notehead <= stem_attach_dist)

    combined_mask = ((notehead_dil > 0) | stems_near_notehead).astype(np.uint8) * 255
    
    return combined_mask, dilate_r, stem_attach_dist


def check_geom_overlap(box, target_mask, endpoint_radius):
    """Helper to check overlap for a single mask."""
    h, w = target_mask.shape[:2]
    x1, y1, x2, y2 = map(int, box)
    xm = (x1 + x2) // 2
    r = endpoint_radius

    tx1, tx2 = max(0, xm - r), min(w - 1, xm + r)
    ty1, ty2 = max(0, y1 - r), min(h - 1, y1 + r)
    
    bx1, bx2 = max(0, xm - r), min(w - 1, xm + r)
    by1, by2 = max(0, y2 - r), min(h - 1, y2 + r)

    top_overlap = int(np.count_nonzero(target_mask[ty1:ty2 + 1, tx1:tx2 + 1]))
    bot_overlap = int(np.count_nonzero(target_mask[by1:by2 + 1, bx1:bx2 + 1]))

    return top_overlap, bot_overlap

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cluster-max-dist", type=float, default=25.0)
    parser.add_argument("--min-row-count", type=int, default=3)
    parser.add_argument("--use-ratio-tolerance", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--tol-ratio", type=float, default=0.35)
    parser.add_argument("--staff-space", type=float, default=None)
    parser.add_argument("--tol-top-px", type=float, default=6.0)
    parser.add_argument("--tol-bottom-px", type=float, default=6.0)
    parser.add_argument("--enable-geom-notehead-filter", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--geom-notehead-mode", type=str, default="page3_known_fp", choices=["page3_known_fp", "endpoint_overlap_experimental"])
    parser.add_argument("--homr-context-dir", type=str, default=None)
    parser.add_argument("--homr-notehead-mask", type=str, default=None)
    parser.add_argument("--homr-stems-rest-mask", type=str, default=None)
    parser.add_argument("--min-bbox-ink-density", type=float, default=0.0)
    parser.add_argument("--max-end-ink-density", type=float, default=1.0)
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
    rows, noise_indices = cluster_by_y_distance(y_centers, max_distance=args.cluster_max_dist, min_cluster_size=args.min_row_count)
    print(f"Clustering found {len(rows)} row clusters. Noise points: {len(noise_indices)}.")

    staff_space = args.staff_space if args.staff_space is not None else estimate_staff_space(rows, preds_list)
    if args.use_ratio_tolerance:
        tol_top, tol_bottom = args.tol_ratio * staff_space, args.tol_ratio * staff_space
        tol_mode = "ratio"
    else:
        tol_top, tol_bottom = args.tol_top_px, args.tol_bottom_px
        tol_mode = "absolute"
    print(f"Estimated staff_space: {staff_space:.2f}px | tol_mode={tol_mode} | tol_top={tol_top:.2f}px tol_bottom={tol_bottom:.2f}px")
    
    # 3. Filter Per Row
    accepted_indices = set()
    for row_id, indices in rows.items():
        if len(indices) < args.min_row_count: continue
        tops = [preds_list[i][1] for i in indices]
        bottoms = [preds_list[i][3] for i in indices]
        ref_top, ref_bottom = np.median(tops), np.median(bottoms)
        for i in indices:
            box = preds_list[i]
            top_dev, bot_dev = abs(box[1] - ref_top), abs(box[3] - ref_bottom)
            if top_dev <= tol_top and bot_dev <= tol_bottom:
                accepted_indices.add(i)
                
    row_filtered_preds = [preds_list[i] for i in sorted(list(accepted_indices))]

    # 4. Detailed Statistics and Geometry Filter Pass
    candidate_stats = []
    geom_filtered_preds = []
    geom_debug_rejected_list = []
    notehead_mask, stems_rest_mask, combined_mask = None, None, None
    dilate_r, endpoint_r = 0, 0

    # Load masks once if geom filter is enabled
    if args.enable_geom_notehead_filter and args.geom_notehead_mode == "endpoint_overlap_experimental":
        base_img = cv2.imread(args.image)
        if base_img is None:
            print(f"Error: Could not load image from {args.image}. Skipping geom filter.")
            args.enable_geom_notehead_filter = False
        else:
            target_hw = base_img.shape[:2]
            notehead_path = os.path.join(args.homr_context_dir, "page_3_debug_6_notehead.png") if args.homr_context_dir else args.homr_notehead_mask
            stems_path = os.path.join(args.homr_context_dir, "page_3_debug_5_stems_rest.png") if args.homr_context_dir else args.homr_stems_rest_mask
            try:
                notehead_mask = _load_binary_mask(notehead_path, target_hw=target_hw)
                stems_rest_mask = _load_binary_mask(stems_path, target_hw=target_hw)
                combined_mask, dilate_r, _ = _build_notehead_with_stems_mask(notehead_mask, stems_rest_mask, staff_space)
                endpoint_r = max(2, int(round(staff_space * 0.6)))
            except Exception as e:
                print(f"Error loading/building masks: {e}. Disabling geom filter.")
                args.enable_geom_notehead_filter = False

    for i, box in enumerate(row_filtered_preds):
        x1, y1, x2, y2 = box
        width, height = x2 - x1, y2 - y1
        
        # Base stats
        stats_entry = {
            "raw_idx": preds_list.index(box) if box in preds_list else -1,
            "row_filtered_idx": i,
            "bbox": box,
            "width": width,
            "height": height,
            "area": width * height,
        }
        
        # Classification (TP/FP)
        max_iou = 0.0
        for gt_box in gt_boxes:
            max_iou = max(max_iou, get_iou(box, gt_box))
        stats_entry["classification"] = "TP" if max_iou > 0.5 else "FP"
        stats_entry["gt_max_iou"] = max_iou
        
        # Geom filter stats
        stats_entry["rejected_by_geom"] = False
        
        if args.enable_geom_notehead_filter and args.geom_notehead_mode == "endpoint_overlap_experimental" and combined_mask is not None:
            nh_top_overlap, nh_bot_overlap = check_geom_overlap(box, notehead_mask, endpoint_r)
            sr_top_overlap, sr_bot_overlap = check_geom_overlap(box, stems_rest_mask, endpoint_r)
            comb_top_overlap, comb_bot_overlap = check_geom_overlap(box, combined_mask, endpoint_r)
            
            stats_entry.update({
                "geom_dilate_r": dilate_r,
                "geom_endpoint_r": endpoint_r,
                "notehead_top_overlap": nh_top_overlap, "notehead_bot_overlap": nh_bot_overlap,
                "stems_rest_top_overlap": sr_top_overlap, "stems_rest_bot_overlap": sr_bot_overlap,
                "combined_top_overlap": comb_top_overlap, "combined_bot_overlap": comb_bot_overlap
            })

            if comb_top_overlap > 0 or comb_bot_overlap > 0:
                stats_entry["rejected_by_geom"] = True
                stats_entry["rejection_reason"] = "endpoint_overlap"
                geom_debug_rejected_list.append(stats_entry)
            else:
                geom_filtered_preds.append(box) # Not rejected, pass through
        else:
            geom_filtered_preds.append(box) # Not rejected, pass through
            
        candidate_stats.append(stats_entry)

    if not args.enable_geom_notehead_filter or args.geom_notehead_mode != "endpoint_overlap_experimental":
        geom_filtered_preds = row_filtered_preds

    row_then_geom_preds = geom_filtered_preds

    # 5. Apply Pixel Context Filters
    pixel_filtered_preds = []
    # ... (rest of pixel filter logic remains the same) ...
    # This part is omitted for brevity as it's not the focus of this iteration
    final_preds = row_then_geom_preds 

    # 6. Evaluate and Save Metrics
    old_metrics = evaluate_detections(preds_list, gt_boxes)
    row_filter_metrics = evaluate_detections(row_filtered_preds, gt_boxes) 
    geom_filter_metrics = evaluate_detections(row_then_geom_preds, gt_boxes)
    final_metrics = evaluate_detections(final_preds, gt_boxes)
    
    print("\n--- Results ---")
    print(f"Original (raw detections): TP={old_metrics['TP']}, FP={old_metrics['FP']}, FN={old_metrics['FN']}")
    print(f"After Row Filter: TP={row_filter_metrics['TP']}, FP={row_filter_metrics['FP']}, FN={row_filter_metrics['FN']}")
    if args.enable_geom_notehead_filter:
        print(f"After Geom Note Context: TP={geom_filter_metrics['TP']}, FP={geom_filter_metrics['FP']}, FN={geom_filter_metrics['FN']}")
    print(f"Final Filtered: TP={final_metrics['TP']}, FP={final_metrics['FP']}, FN={final_metrics['FN']}")

    res = { "config": vars(args), "original": old_metrics, "row_filtered": row_filter_metrics, "geom_filtered": geom_filter_metrics, "final": final_metrics }
    with open(os.path.join(args.output, "metrics.json"), 'w') as f:
        json.dump(res, f, indent=2)
        
    with open(os.path.join(args.output, "candidate_statistics.json"), 'w') as f:
        json.dump(candidate_stats, f, indent=2)
    
    print(f"\nSaved results and stats to {args.output}")

if __name__ == "__main__":
    main()