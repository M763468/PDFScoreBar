import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

# Import logic
from tools.run_gt_rebuild_hybrid_eval import detect_probe_scan


def process_page(page_config):
    name = page_config["name"]
    image_path = Path(page_config["image"])
    baseline_json_path = Path(page_config["output_sorted"])  # Use sorted GT as baseline

    # Check if files exist
    if not image_path.exists():
        print(f"Skipping {name}: Image not found at {image_path}")
        return
    if not baseline_json_path.exists():
        # Fallback to output_raw if sorted missing, or just raw_boxes
        baseline_json_path = Path(page_config["output_raw"])
        if not baseline_json_path.exists():
            print(f"Skipping {name}: No baseline JSON found at {baseline_json_path}")
            return

    # Load Image
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Skipping {name}: Failed to load image")
        return

    # Dummy mask
    staff_mask = np.zeros(img.shape[:2], dtype=np.uint8)

    # Load Existing Boxes
    existing_boxes = []
    with open(baseline_json_path, "r") as f:
        data = json.load(f)
        for item in data:
            if isinstance(item, list):
                existing_boxes.append(tuple(item))
            elif isinstance(item, dict):
                box = None
                if "bbox" in item:
                    box = item["bbox"]
                elif "barline_location" in item:
                    box = item["barline_location"]
                elif "box" in item:
                    box = item["box"]

                if box and len(box) >= 4:
                    existing_boxes.append(tuple(box))
                else:
                    # print(f"Warning: Skipping item with no valid box in {name}")
                    pass

    if not existing_boxes:
        print(f"Skipping {name}: No existing boxes")
        return

    print(f"Processing {name}...")

    # Run "No Peak" Probe Scan (High recall/Many candidates)
    # mirroring the settings in generate_expanded_candidates.py step 7
    candidates = detect_probe_scan(
        base_img=img,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        # Enable Rescue
        scan_x_peak_rescue=True,
        scan_rightmost_rescue=True,
        divisi_rescue=True,
        scan_x_peak_rescue_mode="topbottom",
        # NO PEAK Thresholds
        probe_width=4,
        ink_threshold=200,
        min_ratio=0.50,
        scan_center_on_peak=True,
        scan_x_peak_ratio_min=0.0,  # ACCEPT ANY PEAK
        scan_rightmost_min_ratio=0.10,
        max_per_band=0,  # No limit
        band_source="row_stats",
    )

    # Merge with existing
    final_set = set(existing_boxes)
    for c in candidates:
        final_set.add(c)

    final_list = sorted(list(final_set))

    # Save output in the same directory as the annotation
    output_dir = baseline_json_path.parent
    output_path = output_dir / "expanded_candidates_nopeak.json"

    with open(output_path, "w") as f:
        json.dump(final_list, f, indent=2)

    print(f"  Saved {len(final_list)} candidates to {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to gt_relabel_gui config json")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        config = json.load(f)

    for page_entry in config.get("pages", []):
        process_page(page_entry)


if __name__ == "__main__":
    main()
