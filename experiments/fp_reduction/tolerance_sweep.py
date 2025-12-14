#!/usr/bin/env python3
"""
Tolerance Sweep for Phase 3 Staff Consistency Filter

Systematically tests different tolerance values to find optimal FP reduction
while preserving TPs.
"""

import argparse
import json
import os
import cv2
import numpy as np
import sys
from itertools import product

sys.path.insert(0, '/workspace')

try:
    from experiments.fp_reduction.unified_metric import evaluate_detections
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from unified_metric import evaluate_detections

def cluster_by_y_distance(y_centers, max_distance=25, min_cluster_size=3):
    """Simple clustering by Y-distance"""
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
    Returns median vertical distance between consecutive rows.
    """
    if len(rows) < 2:
        return 20.0  # Default fallback
    
    # Get median Y for each row
    row_medians = []
    for row_id in sorted(rows.keys()):
        indices = rows[row_id]
        y_centers = [(preds_list[i][1] + preds_list[i][3])/2 for i in indices]
        row_medians.append(np.median(y_centers))
    
    # Calculate gaps between consecutive rows
    gaps = [row_medians[i+1] - row_medians[i] for i in range(len(row_medians)-1)]
    
    # Staff space is typically ~1/4 to 1/5 of row spacing
    # For simplicity, use row_gap / 5 as estimate
    median_gap = np.median(gaps)
    estimated_space = median_gap / 5.0
    
    return estimated_space

def apply_filter(preds_list, rows, noise_indices, tol_top, tol_bottom):
    """Apply consistency filter with given tolerances"""
    accepted_indices = set()
    
    for row_id, indices in rows.items():
        if len(indices) < 3:
            continue
            
        tops = [preds_list[i][1] for i in indices]
        bottoms = [preds_list[i][3] for i in indices]
        
        ref_top = np.median(tops)
        ref_bottom = np.median(bottoms)
        
        for i in indices:
            box = preds_list[i]
            top_dev = abs(box[1] - ref_top)
            bot_dev = abs(box[3] - ref_bottom)
            
            if top_dev <= tol_top and bot_dev <= tol_bottom:
                accepted_indices.add(i)
    
    return accepted_indices

def create_debug_overlay(preds_list, rows, accepted_indices, noise_indices, 
                         image_path, output_path, tol_top, tol_bottom):
    """Create debug visualization"""
    img = cv2.imread(image_path)
    
    for row_id, indices in rows.items():
        if len(indices) < 3:
            continue
            
        tops = [preds_list[i][1] for i in indices]
        bottoms = [preds_list[i][3] for i in indices]
        x_coords = [(preds_list[i][0] + preds_list[i][2])/2 for i in indices]
        
        ref_top = np.median(tops)
        ref_bottom = np.median(bottoms)
        min_x = min(x_coords) - 50
        max_x = max(x_coords) + 50
        
        # Yellow guide lines
        cv2.line(img, (int(min_x), int(ref_top)), (int(max_x), int(ref_top)), (0, 255, 255), 2)
        cv2.line(img, (int(min_x), int(ref_bottom)), (int(max_x), int(ref_bottom)), (0, 255, 255), 2)
        cv2.putText(img, f"R{row_id}", (int(min_x), int(ref_top)-5), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    
    # Draw barlines
    for i in range(len(preds_list)):
        x1, y1, x2, y2 = map(int, preds_list[i])
        if i in accepted_indices:
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)  # Green = kept
        else:
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)  # Red = rejected
    
    # Add tolerance info
    cv2.putText(img, f"Tol: top={tol_top:.1f}px, bot={tol_bottom:.1f}px", 
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    
    cv2.imwrite(output_path, img)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    
    os.makedirs(args.output, exist_ok=True)
    
    # Load data
    with open(args.json) as f:
        data = json.load(f)
    raw = data["predictions"] if isinstance(data, dict) and "predictions" in data else data
    preds_list = []
    for item in raw:
        if isinstance(item, list):
            preds_list.append(item)
        elif isinstance(item, dict):
            preds_list.append(item.get("orig_bbox", item.get("bbox", item.get("pred_bbox"))))
    
    with open(args.gt) as f:
        data = json.load(f)
    if isinstance(data, list) and len(data) > 0 and "barline_location" in data[0]:
        gt_boxes = [x["barline_location"] for x in data]
    else:
        gt_boxes = data
    
    print(f"Loaded {len(preds_list)} barlines, {len(gt_boxes)} GT.")
    
    # Cluster once (fixed parameters)
    y_centers = np.array([(box[1] + box[3]) / 2 for box in preds_list])
    rows, noise_indices = cluster_by_y_distance(y_centers, max_distance=25, min_cluster_size=3)
    
    print(f"Found {len(rows)} rows, {len(noise_indices)} noise points.")
    
    # Estimate staff space
    staff_space = estimate_staff_space(rows, preds_list)
    print(f"Estimated staff space: {staff_space:.2f}px")
    
    # Define sweep parameters
    absolute_tolerances = [3, 5, 7, 10, 12, 15]
    ratio_tolerances = [0.1, 0.2, 0.3, 0.4]
    
    results = []
    
    # Sweep 1: Absolute pixel tolerances
    print("\n=== Absolute Tolerance Sweep ===")
    for tol in absolute_tolerances:
        accepted = apply_filter(preds_list, rows, noise_indices, tol, tol)
        accepted_preds = [preds_list[i] for i in sorted(list(accepted))]
        
        metrics = evaluate_detections(accepted_preds, gt_boxes)
        
        results.append({
            'mode': 'absolute',
            'tol_top_px': tol,
            'tol_bottom_px': tol,
            'tol_ratio': None,
            'TP': metrics['TP'],
            'FP': metrics['FP'],
            'FN': metrics['FN'],
            'Precision': metrics['Precision'],
            'Recall': metrics['Recall'],
            'F1': metrics['F1']
        })
        
        print(f"  Tol={tol}px: TP={metrics['TP']}, FP={metrics['FP']}, FN={metrics['FN']}, "
              f"P={metrics['Precision']:.3f}, R={metrics['Recall']:.3f}")
    
    # Sweep 2: Ratio-based tolerances
    print("\n=== Ratio-Based Tolerance Sweep ===")
    for ratio in ratio_tolerances:
        tol_px = ratio * staff_space
        accepted = apply_filter(preds_list, rows, noise_indices, tol_px, tol_px)
        accepted_preds = [preds_list[i] for i in sorted(list(accepted))]
        
        metrics = evaluate_detections(accepted_preds, gt_boxes)
        
        results.append({
            'mode': 'ratio',
            'tol_top_px': tol_px,
            'tol_bottom_px': tol_px,
            'tol_ratio': ratio,
            'TP': metrics['TP'],
            'FP': metrics['FP'],
            'FN': metrics['FN'],
            'Precision': metrics['Precision'],
            'Recall': metrics['Recall'],
            'F1': metrics['F1']
        })
        
        print(f"  Ratio={ratio} ({tol_px:.1f}px): TP={metrics['TP']}, FP={metrics['FP']}, "
              f"FN={metrics['FN']}, P={metrics['Precision']:.3f}, R={metrics['Recall']:.3f}")
    
    # Save results as CSV
    csv_path = os.path.join(args.output, "metrics_sweep.csv")
    with open(csv_path, 'w') as f:
        f.write("mode,tol_top_px,tol_bottom_px,tol_ratio,TP,FP,FN,Precision,Recall,F1\n")
        for r in results:
            ratio_str = f"{r['tol_ratio']}" if r['tol_ratio'] is not None else ""
            f.write(f"{r['mode']},{r['tol_top_px']:.2f},{r['tol_bottom_px']:.2f},"
                   f"{ratio_str},{r['TP']},{r['FP']},{r['FN']},"
                   f"{r['Precision']:.4f},{r['Recall']:.4f},{r['F1']:.4f}\n")
    
    # Save as markdown table
    md_path = os.path.join(args.output, "metrics_sweep.md")
    with open(md_path, 'w') as f:
        f.write("# Tolerance Sweep Results\n\n")
        f.write(f"**Estimated Staff Space**: {staff_space:.2f}px\n\n")
        f.write("## Absolute Tolerance Sweep\n\n")
        f.write("| Tolerance (px) | TP | FP | FN | Precision | Recall | F1 |\n")
        f.write("|----------------|----|----|----|-----------| -------|----|\n")
        for r in results:
            if r['mode'] == 'absolute':
                f.write(f"| {r['tol_top_px']:.0f} | {r['TP']} | {r['FP']} | {r['FN']} | "
                       f"{r['Precision']:.3f} | {r['Recall']:.3f} | {r['F1']:.3f} |\n")
        
        f.write("\n## Ratio-Based Tolerance Sweep\n\n")
        f.write("| Ratio | Tolerance (px) | TP | FP | FN | Precision | Recall | F1 |\n")
        f.write("|-------|----------------|----|----|----|-----------| -------|----|\n")
        for r in results:
            if r['mode'] == 'ratio':
                f.write(f"| {r['tol_ratio']:.1f} | {r['tol_top_px']:.1f} | {r['TP']} | {r['FP']} | "
                       f"{r['FN']} | {r['Precision']:.3f} | {r['Recall']:.3f} | {r['F1']:.3f} |\n")
    
    # Find best candidates (lowest FP with no recall drop, or minimal TP loss)
    baseline_tp = 152
    candidates = []
    
    for r in results:
        tp_loss = baseline_tp - r['TP']
        if tp_loss <= 5:  # Allow up to 5 TP loss
            candidates.append((r, r['FP'], tp_loss))
    
    # Sort by FP (ascending), then by TP loss (ascending)
    candidates.sort(key=lambda x: (x[1], x[2]))
    top_3 = candidates[:3]
    
    print(f"\n=== Generating Debug Overlays for Top 3 Candidates ===")
    for idx, (r, fp, tp_loss) in enumerate(top_3):
        tol_top = r['tol_top_px']
        tol_bottom = r['tol_bottom_px']
        
        accepted = apply_filter(preds_list, rows, noise_indices, tol_top, tol_bottom)
        
        if r['mode'] == 'absolute':
            filename = f"debug_abs_tol{int(tol_top)}.jpg"
        else:
            filename = f"debug_ratio{r['tol_ratio']:.1f}_tol{tol_top:.1f}px.jpg"
        
        output_path = os.path.join(args.output, filename)
        create_debug_overlay(preds_list, rows, accepted, noise_indices, 
                           args.image, output_path, tol_top, tol_bottom)
        
        print(f"  {idx+1}. {filename}: TP={r['TP']}, FP={r['FP']}, FN={r['FN']}")
    
    print(f"\nResults saved to {args.output}")

if __name__ == "__main__":
    main()
