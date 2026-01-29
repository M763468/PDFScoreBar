import argparse
import json
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import cv2
import numpy as np

# Define Box type
Box = Tuple[float, float, float, float]  # x1, y1, x2, y2


def cluster_by_y_distance(
    y_centers: np.ndarray,
    max_dist: float,
    min_row_count: int,
) -> Tuple[Dict[int, List[int]], List[int]]:
    if y_centers.size == 0:
        return {}, []

    # Simple clustering: exact 1D clustering
    sorted_indices = np.argsort(y_centers)
    sorted_ys = y_centers[sorted_indices]

    clusters: Dict[int, List[int]] = {}
    current_cluster: List[int] = []
    cluster_id = 0

    for i, y in enumerate(sorted_ys):
        if not current_cluster:
            current_cluster.append(int(sorted_indices[i]))  # int cast for json serializable
            continue

        prev_y = y_centers[current_cluster[-1]]
        if y - prev_y <= max_dist:
            current_cluster.append(int(sorted_indices[i]))
        else:
            if len(current_cluster) >= min_row_count:
                clusters[cluster_id] = current_cluster
                cluster_id += 1
            current_cluster = [int(sorted_indices[i])]

    if len(current_cluster) >= min_row_count:
        clusters[cluster_id] = current_cluster

    return clusters, []


def build_row_stats(
    preds: Sequence[Box],
    cluster_max_dist: float,
    min_row_count: int,
) -> List[Dict[str, float]]:
    if not preds:
        return []
    y_centers = np.array([(box[1] + box[3]) / 2 for box in preds])
    # Re-implement simple clustering logic or import if complex (using simple here for independence)
    rows, _ = cluster_by_y_distance(y_centers, cluster_max_dist, min_row_count)

    stats: List[Dict[str, float]] = []
    for indices in rows.values():
        if len(indices) < min_row_count:
            continue
        tops = [preds[i][1] for i in indices]
        bottoms = [preds[i][3] for i in indices]
        centers = [y_centers[i] for i in indices]
        stats.append(
            {
                "center": float(np.median(centers)),
                "top": float(np.median(tops)),
                "bottom": float(np.median(bottoms)),
            }
        )
    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-path", required=True)
    parser.add_argument("--boxes-path", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    img_path = Path(args.image_path)
    boxes_path = Path(args.boxes_path)

    if not img_path.exists():
        print(f"Image not found: {img_path}")
        return
    if not boxes_path.exists():
        print(f"Boxes not found: {boxes_path}")
        return

    img = cv2.imread(str(img_path))
    if img is None:
        print("Failed to load image")
        return
    h, w = img.shape[:2]

    with open(boxes_path) as f:
        existing_boxes = json.load(f)

    # Convert [[x1,y1,x2,y2], ...] to list of tuples
    boxes_tuples = [(b[0], b[1], b[2], b[3]) for b in existing_boxes]

    # Parameters matching generate_expanded_candidates.py / detect_probe_scan defaults
    # band_cluster_max_dist: float = 25.0,
    # band_min_row_count: int = 3,

    row_stats = build_row_stats(boxes_tuples, cluster_max_dist=25.0, min_row_count=3)

    bands = [
        (int(stat["top"]), int(stat["bottom"]))
        for stat in row_stats
        if stat["bottom"] >= stat["top"]
    ]

    print(f"Found {len(bands)} bands from {len(existing_boxes)} existing boxes.")

    overlay = img.copy()

    # Draw existing boxes faintly
    for b in boxes_tuples:
        x1, y1, x2, y2 = map(int, b)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (200, 200, 200), 1)

    # Draw Bands
    alpha = 0.3
    for i, (y1, y2) in enumerate(bands):
        # Draw translucent band
        sub_img = overlay[y1 : y2 + 1, 0:w]
        color_rect = np.zeros_like(sub_img)
        color_rect[:] = (0, 255, 255)  # Yellow bands
        res = cv2.addWeighted(sub_img, 1 - alpha, color_rect, alpha, 0)
        overlay[y1 : y2 + 1, 0:w] = res

        # Draw borders
        cv2.line(overlay, (0, y1), (w - 1, y1), (0, 0, 255), 2)
        cv2.line(overlay, (0, y2), (w - 1, y2), (0, 0, 255), 2)

        cv2.putText(
            overlay,
            f"Band {i}: {y2 - y1}px",
            (10, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            1,
        )

    cv2.imwrite(args.output_path, overlay)
    print(f"Saved visualization to {args.output_path}")


if __name__ == "__main__":
    main()
