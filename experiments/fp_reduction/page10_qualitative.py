#!/usr/bin/env python3
"""
Qualitative Page 10 Generalization Check (No GT)

Applies row-based consistency filter to Page 10 hybrid detections
without quantitative evaluation (no ground truth available).
"""

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, "/workspace")


def cluster_by_y_distance(y_centers, max_distance=25, min_cluster_size=3):
    """Simple clustering by Y-distance"""
    sorted_indices = np.argsort(y_centers)
    sorted_y = y_centers[sorted_indices]

    clusters = []
    current_cluster = [sorted_indices[0]]

    for i in range(1, len(sorted_y)):
        if sorted_y[i] - sorted_y[i - 1] <= max_distance:
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
    """Estimate staff space from row spacing"""
    if len(rows) < 2:
        return 20.0

    row_medians = []
    for row_id in sorted(rows.keys()):
        indices = rows[row_id]
        y_centers = [(preds_list[i][1] + preds_list[i][3]) / 2 for i in indices]
        row_medians.append(np.median(y_centers))

    gaps = [row_medians[i + 1] - row_medians[i] for i in range(len(row_medians) - 1)]
    median_gap = np.median(gaps)
    estimated_space = median_gap / 5.0

    return estimated_space


def apply_filter(preds_list, rows, noise_indices, tol_top, tol_bottom):
    """Apply consistency filter"""
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


def create_debug_overlay(
    preds_list, rows, accepted_indices, noise_indices, image_path, output_path, tol_top, tol_bottom
):
    """Create debug visualization"""
    img = cv2.imread(image_path)

    for row_id, indices in rows.items():
        if len(indices) < 3:
            continue

        tops = [preds_list[i][1] for i in indices]
        bottoms = [preds_list[i][3] for i in indices]
        x_coords = [(preds_list[i][0] + preds_list[i][2]) / 2 for i in indices]

        ref_top = np.median(tops)
        ref_bottom = np.median(bottoms)
        min_x = min(x_coords) - 50
        max_x = max(x_coords) + 50

        # Yellow guide lines
        cv2.line(img, (int(min_x), int(ref_top)), (int(max_x), int(ref_top)), (0, 255, 255), 2)
        cv2.line(
            img, (int(min_x), int(ref_bottom)), (int(max_x), int(ref_bottom)), (0, 255, 255), 2
        )
        cv2.putText(
            img,
            f"R{row_id}",
            (int(min_x), int(ref_top) - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            1,
        )

    # Draw barlines
    for i in range(len(preds_list)):
        x1, y1, x2, y2 = map(int, preds_list[i])
        if i in accepted_indices:
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)  # Green = kept
        else:
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)  # Red = rejected

    # Add info
    cv2.putText(
        img,
        f"Tol: {tol_top:.1f}px | Kept: {len(accepted_indices)}/{len(preds_list)}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
    )

    cv2.imwrite(output_path, img)


def main():
    # Fixed paths for Page 10
    json_path = "/workspace/logs/hybrid_generalization/page_10_hybrid_test/omr_sr/predictions.json"
    image_path = "/workspace/data/training/images/page_10.png"
    output_dir = "/workspace/logs/phase3_staff_consistency/20251215_page10_qualitative"

    os.makedirs(output_dir, exist_ok=True)

    # Load data
    with open(json_path) as f:
        preds_list_1x = json.load(f)

    # USER FEEDBACK: Coordinates are 1x, but need to be overlaid on the original image.
    # The previous debug run showed the image is 4x the coordinate scale.
    # Therefore, we must scale the coordinates UP by 4 to match the image.
    scale_factor = 4.0
    preds_list = [[coord * scale_factor for coord in box] for box in preds_list_1x]

    print(f"Loaded {len(preds_list_1x)} barlines from Page 10 hybrid detections.")
    print(f"Scaling coordinates by x{scale_factor} to match original image size for visualization.")
    print("NOTE: Qualitative check only - no GT evaluation")

    # Cluster
    y_centers = np.array([(box[1] + box[3]) / 2 for box in preds_list])
    rows, noise_indices = cluster_by_y_distance(y_centers, max_distance=25, min_cluster_size=3)

    print(f"Found {len(rows)} rows, {len(noise_indices)} noise points.")

    # Estimate staff space
    staff_space = estimate_staff_space(rows, preds_list)
    print(f"Estimated staff space: {staff_space:.2f}px")

    # Test multiple configurations
    configs = [
        ("abs_5px", 5, 5),
        ("abs_7px", 7, 7),
        ("ratio_0.3", 0.3 * staff_space, 0.3 * staff_space),
        ("ratio_0.4", 0.4 * staff_space, 0.4 * staff_space),
    ]

    results = []

    for name, tol_top, tol_bottom in configs:
        accepted = apply_filter(preds_list, rows, noise_indices, tol_top, tol_bottom)

        kept = len(accepted)
        rejected = len(preds_list) - kept

        results.append(
            {
                "config": name,
                "tol_top": tol_top,
                "tol_bottom": tol_bottom,
                "kept": kept,
                "rejected": rejected,
                "kept_pct": 100 * kept / len(preds_list),
            }
        )

        print(
            f"  {name}: Kept {kept}/{len(preds_list)} ({100 * kept / len(preds_list):.1f}%), Rejected {rejected}"
        )

        # Generate overlay for ratio configs
        if name.startswith("ratio"):
            output_path = os.path.join(output_dir, f"debug_{name}.jpg")
            create_debug_overlay(
                preds_list,
                rows,
                accepted,
                noise_indices,
                image_path,
                output_path,
                tol_top,
                tol_bottom,
            )

    # Save summary
    summary = {
        "page": "page_10",
        "input_count": len(preds_list),
        "rows_found": len(rows),
        "noise_count": len(noise_indices),
        "staff_space_px": staff_space,
        "note": "Qualitative check only - no GT evaluation",
        "configurations": results,
    }

    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # Create markdown report
    with open(os.path.join(output_dir, "qualitative_report.md"), "w") as f:
        f.write("# Page 10 Qualitative Generalization Check\n\n")
        f.write("**Date**: 2025-12-15 (Updated)\n")
        f.write("**Type**: Qualitative only (no GT evaluation)\n\n")
        f.write("## Input\n\n")
        f.write(f"- **Detections**: {len(preds_list)} barlines\n")
        f.write(
            "- **Source**: `logs/hybrid_generalization/page_10_hybrid_test/omr_sr/predictions.json`\n\n"
        )
        f.write("## Fix Applied\n\n")
        f.write(
            "Based on user feedback and analysis, the input coordinates were found to be 1x while the source image was 4x. The script was modified to scale the input coordinates by 4.0 before performing clustering, filtering, and visualization to ensure the overlay matches the image scale.\n\n"
        )
        f.write("## Clustering Results\n\n")
        f.write(f"- **Rows found**: {len(rows)}\n")
        f.write(f"- **Noise points**: {len(noise_indices)}\n")
        f.write(f"- **Estimated staff space**: {staff_space:.2f}px (at 4x scale)\n\n")
        f.write("## Filter Results\n\n")
        f.write("| Configuration | Tolerance | Kept | Rejected | Kept % |\n")
        f.write("|---------------|-----------|------|----------|--------|\n")
        for r in results:
            f.write(
                f"| {r['config']} | {r['tol_top']:.1f}px | {r['kept']} | {r['rejected']} | {r['kept_pct']:.1f}% |\n"
            )
        f.write("\n## Observations\n\n")
        f.write(
            "- With the coordinates scaled up by 4x, the debug overlays should now match the original image.\n"
        )
        f.write("- The filter logic now operates on the upscaled coordinates.\n\n")
        f.write("## Debug Overlays\n\n")
        f.write("- `debug_ratio_0.3.jpg` - Ratio 0.3 configuration\n")
        f.write("- `debug_ratio_0.4.jpg` - Ratio 0.4 configuration\n")

    print(f"\nResults saved to {output_dir}")


if __name__ == "__main__":
    main()
