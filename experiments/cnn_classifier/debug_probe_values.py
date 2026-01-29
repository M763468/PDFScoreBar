import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

# Import helpers
from tools.run_gt_rebuild_hybrid_eval import build_row_stats


# Re-implement simplified scan logic to dump values
def debug_band_scan(
    img: np.ndarray,
    row_stats: list[dict],
    target_band_idx: int,
    output_csv: Path,
):
    # Ultraloose Params
    probe_width = 4
    ink_threshold = 200
    min_ratio = 0.50
    scan_x_peak_ratio_min = 1.2
    scan_center_on_peak = True

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ink = (gray < ink_threshold).astype(np.uint8)
    h, w = ink.shape[:2]

    if target_band_idx >= len(row_stats):
        print(f"Band index {target_band_idx} out of range (0-{len(row_stats) - 1})")
        return

    stat = row_stats[target_band_idx]
    y1 = int(stat["top"])
    y2 = int(stat["bottom"])

    # Matching detect_probe_scan "row_stats" logic
    band_y1 = max(0, y1)
    band_y2 = min(h - 1, y2)
    band_h = max(1, band_y2 - band_y1 + 1)

    width = int(probe_width)
    kernel = np.ones(width, dtype=np.int32)

    scan_band = ink[band_y1 : band_y2 + 1, :]
    col_sums = scan_band.sum(axis=0)
    stripe_sums = np.convolve(col_sums, kernel, mode="same")

    # We want to scan EVERY column in this band and dump metrics
    records = []

    print(f"Scanning Band {target_band_idx}: Y={band_y1}-{band_y2}, H={band_h}")

    # Pre-calculate x-peak dominance for every column
    # detect_probe_scan logic:
    # scan_ratios_full = ...
    # neighbor_median = ...
    scan_ratios_full = stripe_sums / float(band_h * width)

    wsize = max(1, int(15))  # Default scan_x_peak_window

    for x in range(w):
        # 1. Base Ratio
        ratio = scan_ratios_full[x]

        # 2. Peak Ratio (Dominance)
        left = max(0, x - wsize)
        right = min(len(scan_ratios_full) - 1, x + wsize)
        neighbor_vals = [scan_ratios_full[i] for i in range(left, right + 1) if i != x]
        if not neighbor_vals:
            peak_ratio = 0.0
        else:
            med = float(np.median(neighbor_vals))
            peak_ratio = ratio / med if med > 0 else 999.0

        # 3. Decision
        status = "REJECT"
        reject_reason = ""

        if ratio < min_ratio:
            reject_reason += "ratio_low;"

        if peak_ratio < scan_x_peak_ratio_min:
            reject_reason += "peak_low;"

        if not reject_reason:
            status = "ACCEPT"

        records.append(
            {
                "x": x,
                "y1": band_y1,
                "y2": band_y2,
                "ink_ratio": round(ratio, 4),
                "peak_dominance": round(peak_ratio, 4),
                "ink_pixels": int(col_sums[x]),
                "status": status,
                "reject_reason": reject_reason,
            }
        )

    # Write CSV
    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)

    print(f"Wrote {len(records)} columns to {output_csv}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-path", required=True)
    parser.add_argument("--boxes-path", required=True)
    parser.add_argument("--target-band", type=int, required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()

    img = cv2.imread(args.image_path)
    with open(args.boxes_path) as f:
        existing_boxes = json.load(f)
    # Handle list of lists or dicts
    existing_boxes_tuples = []
    for item in existing_boxes:
        if isinstance(item, list):
            existing_boxes_tuples.append(tuple(item))
        elif isinstance(item, dict):
            existing_boxes_tuples.append(tuple(item.get("bbox", [])))

    # Re-build stats to get bands
    row_stats = build_row_stats(existing_boxes_tuples, cluster_max_dist=25.0, min_row_count=3)

    debug_band_scan(img, row_stats, args.target_band, Path(args.output_csv))


if __name__ == "__main__":
    main()
